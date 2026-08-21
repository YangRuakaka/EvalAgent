from __future__ import annotations

import argparse
import asyncio
import importlib.abc
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
DEFAULT_INPUT_DIR = (
    ROOT
    / "technical_evaluation"
    / "annotation"
    / "webharbor_72_human"
    / "Yukun"
    / "raw_data"
)
DEFAULT_OUTPUT_DIR = (
    ROOT
    / "technical_evaluation"
    / "results"
    / "initial_agentic_judge_yukun_48"
)
INITIAL_COMMIT = "19fc0a2"
INITIAL_PACKAGE = "evalagent_initial_app"
JUDGE_MODEL = "deepseek-chat"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


class GitCommitBackendFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Import the initial backend package directly from a Git commit."""

    def __init__(self, *, commit: str, package: str) -> None:
        self.commit = commit
        self.package = package
        self._resolved: dict[str, tuple[str, bool, str]] = {}

    def _read_git_path(self, git_path: str) -> str | None:
        completed = subprocess.run(
            ["git", "show", f"{self.commit}:{git_path}"],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            return None
        return completed.stdout.decode("utf-8-sig")

    def _resolve(self, fullname: str) -> tuple[str, bool, str] | None:
        if fullname in self._resolved:
            return self._resolved[fullname]
        if fullname == self.package:
            relative = ""
        elif fullname.startswith(self.package + "."):
            relative = fullname[len(self.package) + 1 :].replace(".", "/")
        else:
            return None

        candidates = []
        if relative:
            candidates.extend(
                [
                    (f"backend/app/{relative}/__init__.py", True),
                    (f"backend/app/{relative}.py", False),
                ]
            )
        else:
            candidates.append(("backend/app/__init__.py", True))

        for git_path, is_package in candidates:
            source = self._read_git_path(git_path)
            if source is not None:
                resolved = (git_path, is_package, source)
                self._resolved[fullname] = resolved
                return resolved
        # The initial commit used implicit namespace packages and therefore did
        # not contain __init__.py files under backend/app.
        directory = "backend/app" + (f"/{relative}" if relative else "")
        completed = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", self.commit, directory],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            resolved = (f"{directory}/<namespace>", True, "")
            self._resolved[fullname] = resolved
            return resolved
        return None

    def find_spec(
        self,
        fullname: str,
        path: Any = None,
        target: ModuleType | None = None,
    ) -> Any:
        resolved = self._resolve(fullname)
        if resolved is None:
            return None
        _, is_package, _ = resolved
        return importlib.util.spec_from_loader(fullname, self, is_package=is_package)

    def create_module(self, spec: Any) -> ModuleType | None:
        return None

    def exec_module(self, module: ModuleType) -> None:
        git_path, is_package, source = self._resolved[module.__name__]
        module.__file__ = f"git://{self.commit}/{git_path}"
        if is_package:
            module.__path__ = []  # type: ignore[attr-defined]
        exec(compile(source, module.__file__, "exec"), module.__dict__)


def _install_initial_backend_importer() -> None:
    if not any(
        isinstance(item, GitCommitBackendFinder)
        and item.commit == INITIAL_COMMIT
        and item.package == INITIAL_PACKAGE
        for item in sys.meta_path
    ):
        sys.meta_path.insert(
            0,
            GitCommitBackendFinder(
                commit=INITIAL_COMMIT,
                package=INITIAL_PACKAGE,
            ),
        )


def _load_raw_cases(input_dir: Path) -> dict[str, dict[str, Any]]:
    cases: dict[str, dict[str, Any]] = {}
    for path in sorted(input_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        case_id = str(payload.get("data_id") or path.stem).strip()
        if not case_id:
            continue
        payload["_input_path"] = str(path.resolve())
        cases[case_id] = payload
    return cases


def _to_initial_steps(payload: dict[str, Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for step in payload.get("steps") or []:
        normalized.append(
            {
                "thinking": step.get("AI REASONING"),
                "evaluation_previous_goal": step.get("EVALUATION"),
                "memory": step.get("MEMORY"),
                "next_goal": step.get("TARGET OBJECTIVE"),
                "action": step.get("ACTION"),
            }
        )
    return normalized


def _load_source_run(payload: dict[str, Any]) -> dict[str, Any]:
    source = Path(str(payload.get("source_file") or ""))
    if not source.is_file():
        return {}
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _criterion_to_dict(result: Any) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    return dict(result)


def _criterion_payload_is_usable(payload: dict[str, Any]) -> bool:
    verdict = str(payload.get("overall_assessment") or "").strip().lower()
    try:
        confidence = float(payload.get("confidence") or 0.0)
    except Exception:
        confidence = 0.0
    serialized = json.dumps(payload, ensure_ascii=False).lower()
    infrastructure_markers = (
        "connection error",
        "assessment generation failed",
        "evaluation failed due to error",
        "evaluation parsing failed",
        "rate limit",
        "timed out",
    )
    return (
        verdict in {"pass", "fail", "partial"}
        and confidence > 0.0
        and not any(marker in serialized for marker in infrastructure_markers)
    )


def _stored_condition_is_usable(condition: dict[str, Any]) -> bool:
    criteria = condition.get("criteria") or []
    return (
        isinstance(criteria, list)
        and len(criteria) == 1
        and isinstance(criteria[0], dict)
        and _criterion_payload_is_usable(criteria[0])
    )


def _build_visualization(
    *,
    case_id: str,
    payload: dict[str, Any],
    criterion_result: Any,
) -> dict[str, Any]:
    source_run = _load_source_run(payload)
    source_metadata = source_run.get("metadata", {})
    source_details = source_run.get("details", {})
    evidence: list[dict[str, Any]] = []
    step_verdicts: dict[str, str] = {}
    involved_steps = list(getattr(criterion_result, "involved_steps", []) or [])
    for detail in involved_steps:
        status = _enum_value(getattr(detail, "evaluateStatus", "unknown"))
        for step_index in list(getattr(detail, "steps", []) or []):
            step_verdicts[str(step_index)] = status
        for item in list(getattr(detail, "highlighted_evidence", []) or []):
            if hasattr(item, "model_dump"):
                evidence.append(item.model_dump(mode="json"))
            elif isinstance(item, dict):
                evidence.append(item)

    overall = _enum_value(getattr(criterion_result, "overall_assessment", "unknown"))
    confidence = float(getattr(criterion_result, "confidence", 0.0) or 0.0)
    return {
        "case_id": case_id,
        "site": str(source_metadata.get("task", {}).get("url", "")),
        "task": str(payload.get("task") or ""),
        "criterion": {
            "title": "criteria1",
            "assertion": str(payload.get("criteria1") or ""),
            "description": "",
        },
        "agent": {
            "model": source_metadata.get("model", JUDGE_MODEL),
            "persona_value": payload.get("persona_value"),
            "run_id": source_metadata.get("id", case_id),
            "summary": source_run.get("summary", {}),
        },
        "judge": {
            "model": JUDGE_MODEL,
            "version": f"initial-agentic-judge@{INITIAL_COMMIT}",
            "verdict": overall.upper(),
            "confidence": confidence,
            "reasoning": str(getattr(criterion_result, "overall_reasoning", "") or ""),
            "summary": "",
            "relevant_steps": sorted(
                {
                    int(index)
                    for detail in involved_steps
                    for index in (getattr(detail, "steps", []) or [])
                }
            ),
            "evidence": evidence,
            "step_verdicts": step_verdicts,
            "granularity": _enum_value(getattr(criterion_result, "granularity", "")),
        },
        "steps": _to_initial_steps(payload),
        "screenshots": source_details.get("screenshots", []),
        "source_path": payload.get("source_file"),
    }


async def _run(args: argparse.Namespace) -> int:
    _load_env_file(BACKEND_DIR / ".env")
    _load_env_file(ROOT / ".env")
    _install_initial_backend_importer()

    from evalagent_initial_app.api.deps import get_judge_services
    from evalagent_initial_app.api.judge import _process_single_criterion
    from evalagent_initial_app.schemas.browser_agent import BrowserAgentTask
    from evalagent_initial_app.schemas.judge import ExperimentCriterion

    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = _load_raw_cases(input_dir)
    if args.case_ids:
        requested = set(args.case_ids)
        missing = requested - set(cases)
        if missing:
            raise ValueError(f"Unknown Yukun case IDs: {sorted(missing)}")
        cases = {case_id: cases[case_id] for case_id in cases if case_id in requested}
    if not cases:
        raise ValueError(f"No cases found in {input_dir}")

    status_path = output_dir / "run_status.json"
    response_path = output_dir / "experiment_evaluation.json"
    visualization_path = output_dir / "visualization_data.json"
    status: dict[str, Any] = {
        "state": "running",
        "started_at_utc": _utc_now(),
        "finished_at_utc": None,
        "pipeline": "initial agentic judge",
        "source_commit": INITIAL_COMMIT,
        "judge_model": JUDGE_MODEL,
        "input_dir": str(input_dir),
        "total": len(cases),
        "completed": 0,
        "failed": 0,
        "cases": {case_id: "pending" for case_id in cases},
    }

    existing_conditions: dict[str, dict[str, Any]] = {}
    existing_visualizations: dict[str, dict[str, Any]] = {}
    if args.resume and response_path.is_file():
        existing = json.loads(response_path.read_text(encoding="utf-8"))
        existing_conditions = {
            str(item.get("conditionID")): item
            for item in existing.get("conditions", [])
            if (
                isinstance(item, dict)
                and item.get("conditionID") in cases
                and _stored_condition_is_usable(item)
            )
        }
    if args.resume and visualization_path.is_file():
        existing = json.loads(visualization_path.read_text(encoding="utf-8"))
        existing_visualizations = {
            str(item.get("case_id")): item
            for item in existing.get("cases", [])
            if (
                isinstance(item, dict)
                and item.get("case_id") in existing_conditions
            )
        }

    services = get_judge_services()
    condition_by_id = dict(existing_conditions)
    visualization_by_id = dict(existing_visualizations)
    for case_id in condition_by_id:
        status["cases"][case_id] = "completed"
    status["completed"] = len(condition_by_id)

    def write_snapshots() -> None:
        ordered_ids = [case_id for case_id in cases if case_id in condition_by_id]
        response_path.write_text(
            json.dumps(
                {
                    "conditions": [condition_by_id[case_id] for case_id in ordered_ids],
                    "multi_condition_assessment": None,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        visualization_path.write_text(
            json.dumps(
                {
                    "generated_at_utc": _utc_now(),
                    "judge_model": JUDGE_MODEL,
                    "judge_version": f"initial-agentic-judge@{INITIAL_COMMIT}",
                    "selection_rule": (
                        "Yukun's 48 assigned WebHarbor cases; criteria1 assertion only; "
                        "full persona supplied; exact initial agentic judge code loaded from Git"
                    ),
                    "cases": [
                        visualization_by_id[case_id]
                        for case_id in ordered_ids
                        if case_id in visualization_by_id
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        status_path.write_text(
            json.dumps(status, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    write_snapshots()
    for case_id, payload in cases.items():
        if case_id in condition_by_id and case_id in visualization_by_id:
            print(f"SKIP {case_id} existing initial-pipeline result", flush=True)
            continue

        status["cases"][case_id] = "running"
        write_snapshots()
        print(f"START {case_id}", flush=True)
        try:
            steps = _to_initial_steps(payload)
            if not steps:
                raise ValueError("Case has no trajectory steps")
            criterion = ExperimentCriterion(
                title="criteria1",
                assertion=str(payload.get("criteria1") or "").strip(),
                description="",
            )
            task = BrowserAgentTask(
                name=str(payload.get("task") or case_id),
                description=str(payload.get("task") or ""),
                url="",
            )
            result = None
            last_error: Exception | None = None
            for attempt in range(1, max(1, args.max_attempts) + 1):
                try:
                    candidate = await asyncio.wait_for(
                        _process_single_criterion(
                            crit=criterion,
                            task=task,
                            all_steps=steps,
                            personas=[str(payload.get("persona") or "")],
                            models=[JUDGE_MODEL],
                            services=services,
                            judge_model=JUDGE_MODEL,
                        ),
                        timeout=max(60, args.case_timeout),
                    )
                    if candidate is None:
                        raise RuntimeError("Initial pipeline returned no criterion result")
                    candidate_payload = _criterion_to_dict(candidate)
                    if not _criterion_payload_is_usable(candidate_payload):
                        raise RuntimeError(
                            "Initial pipeline produced an infrastructure-fallback result"
                        )
                    result = candidate
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt >= max(1, args.max_attempts):
                        break
                    print(
                        f"RETRY {case_id} attempt={attempt + 1}/{args.max_attempts} "
                        f"after {type(exc).__name__}: {exc}",
                        flush=True,
                    )
                    await asyncio.sleep(max(0.0, args.retry_delay))
            if result is None:
                raise last_error or RuntimeError("Initial pipeline failed without a result")

            result_dict = _criterion_to_dict(result)
            condition_by_id[case_id] = {
                "conditionID": case_id,
                "persona": str(payload.get("persona") or ""),
                "value": payload.get("persona_value"),
                "model": JUDGE_MODEL,
                "run_index": 1,
                "criteria": [result_dict],
            }
            visualization_by_id[case_id] = _build_visualization(
                case_id=case_id,
                payload=payload,
                criterion_result=result,
            )
            status["completed"] += 1
            status["cases"][case_id] = "completed"
            verdict = _enum_value(getattr(result, "overall_assessment", "unknown"))
            confidence = float(getattr(result, "confidence", 0.0) or 0.0)
            print(
                f"DONE {case_id} verdict={verdict} confidence={confidence:.3f}",
                flush=True,
            )
        except Exception as exc:
            status["failed"] += 1
            status["cases"][case_id] = f"failed: {type(exc).__name__}: {exc}"
            print(
                f"FAIL {case_id} {type(exc).__name__}: {exc}",
                file=sys.stderr,
                flush=True,
            )
        write_snapshots()

    status["state"] = "completed" if status["failed"] == 0 else "completed_with_failures"
    status["finished_at_utc"] = _utc_now()
    status["response"] = str(response_path)
    status["visualization_data"] = str(visualization_path)
    write_snapshots()
    print(f"RESULT {response_path}", flush=True)
    print(f"VIS_DATA {visualization_path}", flush=True)
    return 0 if status["failed"] == 0 and status["completed"] == len(cases) else 2


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run EvalAgent's first committed agentic judge on Yukun's cases."
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--case-timeout", type=int, default=1200)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--retry-delay", type=float, default=5.0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.plan_only:
        cases = _load_raw_cases(args.input_dir.resolve())
        if args.case_ids:
            cases = {case_id: cases[case_id] for case_id in args.case_ids}
        print(
            json.dumps(
                {
                    "pipeline": "initial agentic judge",
                    "source_commit": INITIAL_COMMIT,
                    "judge_model": JUDGE_MODEL,
                    "case_count": len(cases),
                    "case_ids": list(cases),
                    "output_dir": str(args.output_dir.resolve()),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
