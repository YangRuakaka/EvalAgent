"""Run the 2026-03-19 agentic judge with the minimal PARTIAL->PASS patch.

All backend modules are imported directly from the pinned Git commit. Only the
three files that implement the binary-label patch are overlaid from the current
working tree, which keeps this experiment isolated from later backend changes.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import sys
from pathlib import Path


PIPELINES_DIR = Path(__file__).resolve().parent
ROOT = PIPELINES_DIR.parents[1]
if str(PIPELINES_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINES_DIR))

import run_initial_agentic_judge_yukun as runner


MARCH_COMMIT = "2881b03bc19ac4ee6c53c08ec94930348ab59465"
PATCHED_BACKEND_FILES = {
    "backend/app/services/evaluation_prompts.py": ROOT
    / "backend"
    / "app"
    / "services"
    / "evaluation_prompts.py",
    "backend/app/services/judge_evaluator.py": ROOT
    / "backend"
    / "app"
    / "services"
    / "judge_evaluator.py",
    "backend/app/api/judge.py": ROOT / "backend" / "app" / "api" / "judge.py",
}


_original_read_git_path = runner.GitCommitBackendFinder._read_git_path


def _read_pinned_or_patched_source(
    self: runner.GitCommitBackendFinder,
    git_path: str,
) -> str | None:
    override = PATCHED_BACKEND_FILES.get(git_path)
    if override is not None:
        return override.read_text(encoding="utf-8-sig")
    return _original_read_git_path(self, git_path)


runner.GitCommitBackendFinder._read_git_path = _read_pinned_or_patched_source


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the pinned March 2026 agentic judge with PARTIAL mapped to PASS."
    )
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--judge-model", required=True)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--case-timeout", type=int, default=1200)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--retry-delay", type=float, default=5.0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    return parser.parse_args()


def _materialize_evaluated_records(args: argparse.Namespace) -> int:
    response_path = args.output_dir.resolve() / "experiment_evaluation.json"
    if not response_path.is_file():
        return 0

    response = runner.json.loads(response_path.read_text(encoding="utf-8"))
    conditions = {
        str(item.get("conditionID")): item
        for item in response.get("conditions", [])
        if isinstance(item, dict) and item.get("conditionID")
    }
    inputs = runner._load_raw_cases(args.input_dir.resolve())
    evaluated_dir = args.output_dir.resolve() / "evaluated"
    evaluated_dir.mkdir(parents=True, exist_ok=True)
    written = 0

    for case_id, condition in conditions.items():
        source = inputs.get(case_id)
        criteria = condition.get("criteria") if isinstance(condition, dict) else None
        if not isinstance(source, dict) or not isinstance(criteria, list) or not criteria:
            continue
        criterion = criteria[0]
        if not isinstance(criterion, dict):
            continue

        record = copy.deepcopy(source)
        record.pop("_input_path", None)
        record["data_id"] = case_id
        record["source_file"] = str((args.input_dir.resolve() / f"{case_id}.json"))
        record["criteria1_evaluation"] = copy.deepcopy(criterion)
        record["judge_evaluation"] = {
            "judge_model": args.judge_model,
            "judge_version": f"march-binary-partial-as-pass@{MARCH_COMMIT}",
            "criteria_results": [
                {"source_key": "criteria1", **copy.deepcopy(criterion)}
            ],
        }
        output_path = evaluated_dir / f"{case_id}__evaluated.json"
        output_path.write_text(
            runner.json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        written += 1
    return written


def _update_experiment_metadata(args: argparse.Namespace) -> None:
    output_dir = args.output_dir.resolve()
    case_count = len(runner._load_raw_cases(args.input_dir.resolve()))
    status_path = output_dir / "run_status.json"
    if status_path.is_file():
        status = runner.json.loads(status_path.read_text(encoding="utf-8"))
        status["pipeline"] = "march_2026_agentic_judge_binary_partial_as_pass"
        status["label_policy"] = {
            "allowed_labels": ["pass", "fail"],
            "legacy_partial_mapping": "pass",
        }
        status_path.write_text(
            runner.json.dumps(status, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    visualization_path = output_dir / "visualization_data.json"
    if visualization_path.is_file():
        visualization = runner.json.loads(visualization_path.read_text(encoding="utf-8"))
        visualization["judge_version"] = f"march-binary-partial-as-pass@{MARCH_COMMIT}"
        visualization["selection_rule"] = (
            f"Dan's {case_count}-case input set; "
            "criteria1 only; March 2026 agentic judge with PARTIAL mapped to PASS."
        )
        visualization_path.write_text(
            runner.json.dumps(visualization, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def main() -> int:
    args = _parse_args()
    runner.INITIAL_COMMIT = MARCH_COMMIT
    runner.JUDGE_MODEL = args.judge_model

    if args.plan_only:
        cases = runner._load_raw_cases(args.input_dir.resolve())
        if args.case_ids:
            requested = set(args.case_ids)
            cases = {case_id: payload for case_id, payload in cases.items() if case_id in requested}
        print(
            runner.json.dumps(
                {
                    "pipeline": "march_2026_agentic_judge_binary_partial_as_pass",
                    "source_commit": MARCH_COMMIT,
                    "patched_backend_files": sorted(PATCHED_BACKEND_FILES),
                    "judge_model": args.judge_model,
                    "case_count": len(cases),
                    "case_ids": list(cases),
                    "output_dir": str(args.output_dir.resolve()),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    exit_code = asyncio.run(runner._run(args))
    _update_experiment_metadata(args)
    written = _materialize_evaluated_records(args)
    print(f"MATERIALIZED {written} evaluated records", flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
