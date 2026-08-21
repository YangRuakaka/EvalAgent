from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
TECH_EVAL_DIR = SCRIPT_DIR.parent
ROOT = TECH_EVAL_DIR.parent
BACKEND_DIR = ROOT / "backend"
DEFAULT_INPUT_DIR = ROOT / "browser_agent_runs_webharbor_v13_pilot"
DEFAULT_CASES_FILE = TECH_EVAL_DIR / "webharbor_v13_judge_base_criteria.json"
DEFAULT_OUTPUT_DIR = TECH_EVAL_DIR / "results" / "grounded_judge_webharbor_v13"

GROUNDED_EVIDENCE_POLICY = (
    "Evidence policy: Judge only criterion-specific choice behavior visible in the "
    "trajectory. PASS requires concrete evidence of the relevant comparison attribute, "
    "the selected option, and a material link between that attribute and the selection. "
    "A mere mention of the attribute is insufficient. Do not use task completion, "
    "success/failure status, or ordinary browsing actions as supporting or opposing "
    "evidence. Explicit or inferred persona/value language is criterion evidence when "
    "its semantic dimension overlaps with, directly contrasts with, or materially "
    "explains the current criterion; retain it as context, but exclude unrelated persona "
    "dimensions. Persona context cannot prove PASS without the required observed "
    "comparison-to-choice chain. Quote exact criterion-bearing spans. The final verdict "
    "must be PASS or FAIL based on the full trace."
)


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if name and name not in os.environ:
            os.environ[name] = value


_load_env_file(BACKEND_DIR / ".env")
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.schemas.judge import (  # noqa: E402
    ConditionResult,
    EvaluateStatus,
    EvidenceCitation,
    ExperimentCriterionResult,
    ExperimentEvaluationResponse,
    StepEvaluationDetail,
)
from app.services.grounded_judge_evaluator import GroundedJudgeEvaluatorService  # noqa: E402
from app.services.llm_factory import ChatLLMFactory  # noqa: E402


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _case_id(payload: dict[str, Any]) -> str:
    name = str(payload.get("metadata", {}).get("task", {}).get("name", ""))
    return name.split(" | ", 1)[0].strip()


def _load_runs(input_dir: Path, case_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    runs: dict[str, dict[str, Any]] = {}
    for path in sorted(input_dir.glob("webharbor_v13_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        case_id = _case_id(payload)
        if case_id in case_config:
            payload["_source_path"] = str(path.resolve())
            runs[case_id] = payload
    return runs


def _load_case_config(path: Path) -> dict[str, dict[str, str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not raw:
        raise ValueError("Criteria config must be a non-empty JSON object")

    normalized: dict[str, dict[str, str]] = {}
    base_mode = all(
        isinstance(key, str)
        and len(key) == 6
        and key[3] == "-"
        and key[:3].isalpha()
        and key[4:].isdigit()
        for key in raw
    )
    for key, criterion in raw.items():
        if not isinstance(criterion, dict):
            raise ValueError(f"Criterion {key} must be an object")
        normalized_criterion = {
            "title": str(criterion.get("title") or "").strip(),
            "assertion": str(criterion.get("assertion") or "").strip(),
            "description": str(criterion.get("description") or "").strip(),
        }
        if not normalized_criterion["title"] or not normalized_criterion["assertion"]:
            raise ValueError(f"Criterion {key} is missing title or assertion")
        if base_mode:
            for condition in ("A", "B", "C"):
                normalized[f"{key}-{condition}"] = dict(normalized_criterion)
        else:
            normalized[str(key)] = normalized_criterion
    return normalized


def _to_steps(payload: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    model_outputs = payload.get("details", {}).get("model_outputs", [])
    if not isinstance(model_outputs, list):
        return steps
    for raw in model_outputs:
        item = raw if isinstance(raw, dict) else {}
        steps.append(
            {
                "thinking_process": item.get("thinking_process", item.get("thinking")),
                "evaluation_previous_goal": item.get("evaluation_previous_goal"),
                "memory": item.get("memory"),
                "next_goal": item.get("next_goal"),
                "action": item.get("action"),
            }
        )
    return steps


def _status_from_evidence(evidence: list[EvidenceCitation]) -> EvaluateStatus:
    return GroundedJudgeEvaluatorService.status_from_grounded_evidence(evidence)


def _build_step_details(result: Any) -> list[StepEvaluationDetail]:
    by_step: dict[int, list[EvidenceCitation]] = {}
    for evidence in result.highlighted_evidence or []:
        by_step.setdefault(int(evidence.step_index), []).append(evidence)

    raw_statuses = {
        step_index: _status_from_evidence(evidence)
        for step_index, evidence in by_step.items()
    }
    statuses = GroundedJudgeEvaluatorService.reconcile_step_statuses_with_overall(
        raw_statuses,
        result.verdict,
    )
    details: list[StepEvaluationDetail] = []
    for step_index, evidence in sorted(by_step.items()):
        reasoning_parts: list[str] = []
        for item in evidence:
            text = (item.reasoning or "").strip()
            if text and text not in reasoning_parts:
                reasoning_parts.append(text)
        details.append(
            StepEvaluationDetail(
                evaluateStatus=statuses[step_index],
                reasoning=(
                    (
                        "Insufficient for PASS: this step contains a "
                        "criterion-relevant fragment, but the full trajectory "
                        "does not establish the required decision chain. "
                    )
                    if (
                        statuses[step_index] == EvaluateStatus.FAIL
                        and raw_statuses[step_index] == EvaluateStatus.PASS
                    )
                    else ""
                )
                + (
                    " ".join(reasoning_parts)
                    or "Grounded evidence from this step."
                ),
                highlighted_evidence=evidence,
                confidenceScore=float(result.confidence_score),
                steps=[step_index],
            )
        )
    return details


def _overall_status(verdict: str) -> EvaluateStatus:
    normalized = str(verdict or "").strip().upper()
    if normalized == "PASS":
        return EvaluateStatus.PASS
    if normalized == "FAIL":
        return EvaluateStatus.FAIL
    return EvaluateStatus.UNKNOWN


async def _evaluate_case(
    *,
    service: GroundedJudgeEvaluatorService,
    case_id: str,
    criterion: dict[str, str],
    payload: dict[str, Any],
    judge_model: str,
    semaphore: asyncio.Semaphore,
    collect_debug: bool = False,
) -> tuple[
    str,
    ConditionResult,
    dict[str, Any],
    dict[str, Any] | None,
]:
    metadata = payload.get("metadata", {})
    task = metadata.get("task", {})
    persona = metadata.get("persona", {})
    steps = _to_steps(payload)
    task_name = str(task.get("description") or task.get("name") or case_id)

    criterion_description = " ".join(
        part
        for part in (
            criterion.get("description", ""),
            GROUNDED_EVIDENCE_POLICY,
        )
        if part
    )
    evaluate_kwargs = {
        "criterion_name": criterion["title"],
        "criterion_assertion": criterion["assertion"],
        "criterion_description": criterion_description,
        "task_name": task_name,
        # Persona/model metadata remains available in the exported bundle for
        # stratified analysis. The judge identifies criterion-related persona
        # language from the observable trajectory itself.
        "personas": [],
        "models": [],
        "all_steps": steps,
        "model_name": judge_model,
        "llm_semaphore": semaphore,
    }
    debug_trace: dict[str, Any] | None = None
    if collect_debug:
        result, debug_trace = (
            await service.evaluate_criterion_unified_with_debug(
                **evaluate_kwargs
            )
        )
    else:
        result = await service.evaluate_criterion_unified(**evaluate_kwargs)

    step_details = _build_step_details(result)
    criterion_result = ExperimentCriterionResult(
        title=criterion["title"],
        assertion=criterion["assertion"],
        description=criterion.get("description"),
        involved_steps=step_details,
        overall_assessment=_overall_status(result.verdict),
        overall_reasoning=result.reasoning,
        confidence=float(result.confidence_score),
    )
    condition = ConditionResult(
        conditionID=case_id,
        persona=str(persona.get("content", "")),
        value=str(persona.get("value", "")) or None,
        model=str(metadata.get("model", "")),
        run_index=int(metadata.get("run_index", 1) or 1),
        criteria=[criterion_result],
    )

    visualization = {
        "case_id": case_id,
        "site": str(task.get("url", "")),
        "task": task_name,
        "criterion": criterion,
        "agent": {
            "model": metadata.get("model"),
            "persona_value": persona.get("value"),
            "run_id": metadata.get("id"),
            "summary": payload.get("summary", {}),
        },
        "judge": {
            "model": judge_model,
            "version": GroundedJudgeEvaluatorService.VERSION,
            "verdict": result.verdict,
            "confidence": result.confidence_score,
            "reasoning": result.reasoning,
            "summary": result.aggregated_step_summary,
            "relevant_steps": result.relevant_steps,
            "evidence": [item.model_dump(mode="json") for item in result.highlighted_evidence],
            "step_verdicts": {
                str(detail.steps[0]): detail.evaluateStatus.value
                for detail in step_details
                if detail.steps
            },
        },
        "steps": steps,
        "screenshots": payload.get("details", {}).get("screenshots", []),
        "source_path": payload.get("_source_path"),
    }
    if debug_trace is not None:
        debug_trace = {
            "case_id": case_id,
            "criterion": criterion,
            "task": task_name,
            "stages": debug_trace.get("stages", []),
            "judge_version": debug_trace.get(
                "judge_version",
                GroundedJudgeEvaluatorService.VERSION,
            ),
        }
    return case_id, condition, visualization, debug_trace


async def _run(args: argparse.Namespace) -> int:
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    all_case_config = _load_case_config(args.cases_file)
    case_config = dict(all_case_config)
    if args.case_ids:
        requested = set(args.case_ids)
        unknown = requested - set(all_case_config)
        if unknown:
            raise ValueError(f"Unknown case IDs: {sorted(unknown)}")
        case_config = {
            case_id: criterion
            for case_id, criterion in all_case_config.items()
            if case_id in requested
        }
    runs = _load_runs(input_dir, case_config)
    missing = sorted(set(case_config) - set(runs))
    if missing:
        raise FileNotFoundError(f"Missing WebHarbor runs for: {missing}")

    status_path = output_dir / "run_status.json"
    status: dict[str, Any] = {
        "state": "running",
        "started_at_utc": _utc_now(),
        "finished_at_utc": None,
        "judge_model": args.judge_model,
        "judge_version": GroundedJudgeEvaluatorService.VERSION,
        "total": len(case_config),
        "completed": 0,
        "failed": 0,
        "cases": {case_id: "pending" for case_id in case_config},
    }
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    service = GroundedJudgeEvaluatorService(llm_factory=ChatLLMFactory())
    concurrency = max(1, args.concurrency)
    llm_semaphore = asyncio.Semaphore(concurrency)
    case_semaphore = asyncio.Semaphore(concurrency)

    async def evaluate_with_case_limit(
        case_id: str,
    ) -> tuple[
        str,
        ConditionResult | None,
        dict[str, Any] | None,
        dict[str, Any] | None,
        Exception | None,
    ]:
        # Bound whole trajectories, not merely individual stage calls. Without
        # this outer limit, all 72 cases queue their contract stage before any
        # one case can advance through extraction, repair, audit, and verdict.
        async with case_semaphore:
            try:
                result = await asyncio.wait_for(
                    _evaluate_case(
                        service=service,
                        case_id=case_id,
                        criterion=case_config[case_id],
                        payload=runs[case_id],
                        judge_model=args.judge_model,
                        semaphore=llm_semaphore,
                        collect_debug=args.debug_trace,
                    ),
                    timeout=max(60, args.case_timeout),
                )
                (
                    result_case_id,
                    condition,
                    visualization,
                    debug_trace,
                ) = result
                return (
                    result_case_id,
                    condition,
                    visualization,
                    debug_trace,
                    None,
                )
            except Exception as exc:
                return case_id, None, None, None, exc

    tasks = [evaluate_with_case_limit(case_id) for case_id in case_config]

    condition_by_id: dict[str, ConditionResult] = {}
    visualization_by_id: dict[str, dict[str, Any]] = {}
    debug_by_id: dict[str, dict[str, Any]] = {}
    response_path = output_dir / "experiment_evaluation.json"
    visualization_path = output_dir / "visualization_data.json"
    debug_path = output_dir / "pipeline_debug.json"
    if args.merge_existing and response_path.is_file():
        existing_response = ExperimentEvaluationResponse.model_validate_json(
            response_path.read_text(encoding="utf-8")
        )
        condition_by_id.update(
            {condition.conditionID: condition for condition in existing_response.conditions}
        )
    if args.merge_existing and visualization_path.is_file():
        existing_visualization = json.loads(visualization_path.read_text(encoding="utf-8"))
        visualization_by_id.update(
            {
                str(case.get("case_id")): case
                for case in existing_visualization.get("cases", [])
                if isinstance(case, dict) and case.get("case_id")
            }
        )
    if args.merge_existing and debug_path.is_file():
        existing_debug = json.loads(debug_path.read_text(encoding="utf-8"))
        debug_by_id.update(
            {
                str(case.get("case_id")): case
                for case in existing_debug.get("cases", [])
                if isinstance(case, dict) and case.get("case_id")
            }
        )

    def write_snapshots() -> None:
        ordered_ids = [
            case_id for case_id in all_case_config if case_id in condition_by_id
        ]
        response = ExperimentEvaluationResponse(
            conditions=[condition_by_id[case_id] for case_id in ordered_ids],
            multi_condition_assessment=None,
        )
        response_path.write_text(response.model_dump_json(indent=2), encoding="utf-8")
        visualization_payload = {
            "generated_at_utc": _utc_now(),
            "judge_model": args.judge_model,
            "judge_version": GroundedJudgeEvaluatorService.VERSION,
            "selection_rule": (
                "24 base tasks x A/B/C; one shared task-specific criterion per base task; "
                "persona/value context retained only when semantically related to the criterion"
            ),
            "cases": [visualization_by_id[case_id] for case_id in ordered_ids],
        }
        visualization_path.write_text(
            json.dumps(visualization_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if args.debug_trace:
            debug_payload = {
                "generated_at_utc": _utc_now(),
                "judge_model": args.judge_model,
                "judge_version": GroundedJudgeEvaluatorService.VERSION,
                "cases": [
                    debug_by_id[case_id]
                    for case_id in ordered_ids
                    if case_id in debug_by_id
                ],
            }
            debug_path.write_text(
                json.dumps(debug_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    for future in asyncio.as_completed(tasks):
        (
            case_id,
            condition,
            visualization,
            debug_trace,
            error,
        ) = await future
        if error is None and condition is not None and visualization is not None:
            condition_by_id[case_id] = condition
            visualization_by_id[case_id] = visualization
            if debug_trace is not None:
                debug_by_id[case_id] = debug_trace
            status["completed"] += 1
            status["cases"][case_id] = "completed"
            verdict = condition.criteria[0].overall_assessment.value
            print(f"DONE {case_id} verdict={verdict} confidence={condition.criteria[0].confidence:.3f}", flush=True)
            write_snapshots()
        else:
            status["failed"] += 1
            status["cases"][case_id] = (
                f"failed: {type(error).__name__}: {error}"
            )
            print(
                f"FAIL {case_id} {type(error).__name__}: {error}",
                file=sys.stderr,
                flush=True,
            )
        status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    write_snapshots()

    status["state"] = "completed" if status["failed"] == 0 else "completed_with_failures"
    status["finished_at_utc"] = _utc_now()
    status["response"] = str(response_path)
    status["visualization_data"] = str(visualization_path)
    if args.debug_trace:
        status["pipeline_debug"] = str(debug_path)
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"RESULT {response_path}", flush=True)
    print(f"VIS_DATA {visualization_path}", flush=True)
    selected_complete = all(case_id in condition_by_id for case_id in case_config)
    return 0 if status["failed"] == 0 and selected_complete else 2


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate the 72-case WebHarbor v1.3 set with the grounded judge."
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--cases-file", type=Path, default=DEFAULT_CASES_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--judge-model", default="deepseek-chat")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument(
        "--case-timeout",
        type=int,
        default=900,
        help="Maximum wall-clock seconds for one complete judge case.",
    )
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument(
        "--merge-existing",
        action="store_true",
        help="Replace selected cases while retaining other existing results.",
    )
    parser.add_argument(
        "--debug-trace",
        action="store_true",
        help=(
            "Write pipeline_debug.json with every intermediate judge stage. "
            "The formal EvalAgent response schema is unchanged."
        ),
    )
    return parser.parse_args()


def main() -> int:
    return asyncio.run(_run(_parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
