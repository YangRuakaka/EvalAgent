"""Validate the four completed March-binary WebHarbor-72 Judge outputs."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


EXPERIMENT_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EXPERIMENT_DIR / "results"
REPORT_PATH = EXPERIMENT_DIR / "validation_report.json"
LABEL_KEYS = {
    "verdict",
    "evaluatestatus",
    "overall_assessment",
    "evaluation_status",
}


def _collect_labels(node: Any, sink: Counter[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if str(key).strip().lower() in LABEL_KEYS and isinstance(value, str):
                sink[value.strip().lower()] += 1
            _collect_labels(value, sink)
    elif isinstance(node, list):
        for item in node:
            _collect_labels(item, sink)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_evaluated_dir(
    directory: Path,
    expected_ids: set[str],
    expected_model: str,
) -> dict[str, Any]:
    files = sorted(directory.glob("*__evaluated.json"))
    ids: list[str] = []
    labels: Counter[str] = Counter()
    model_names: Counter[str] = Counter()
    parse_errors: list[dict[str, str]] = []
    for path in files:
        try:
            payload = _read_json(path)
        except Exception as exc:
            parse_errors.append({"file": path.name, "error": str(exc)})
            continue
        ids.append(str(payload.get("data_id") or ""))
        _collect_labels(payload.get("judge_evaluation", payload), labels)
        judge_evaluation = payload.get("judge_evaluation")
        if isinstance(judge_evaluation, dict) and judge_evaluation.get("judge_model"):
            model_names[str(judge_evaluation["judge_model"])] += 1
        baseline_evaluation = payload.get("baseline_judge_evaluation")
        if isinstance(baseline_evaluation, dict) and baseline_evaluation.get("judge_model"):
            model_names[str(baseline_evaluation["judge_model"])] += 1
        metadata = payload.get("baseline_metadata")
        if isinstance(metadata, dict) and metadata.get("judge_model"):
            model_names[str(metadata["judge_model"])] += 1

    id_counts = Counter(ids)
    duplicates = sorted(case_id for case_id, count in id_counts.items() if count > 1)
    found_ids = set(ids)
    model_ok = not model_names or set(model_names) == {expected_model}
    return {
        "directory": str(directory),
        "file_count": len(files),
        "parsed_count": len(ids),
        "unique_case_count": len(found_ids),
        "missing_case_ids": sorted(expected_ids - found_ids),
        "extra_case_ids": sorted(found_ids - expected_ids),
        "duplicate_case_ids": duplicates,
        "parse_errors": parse_errors,
        "models": dict(model_names),
        "labels": dict(labels),
        "partial_label_count": labels.get("partial", 0),
        "valid": (
            len(files) == 72
            and len(found_ids) == 72
            and found_ids == expected_ids
            and not duplicates
            and not parse_errors
            and model_ok
            and labels.get("partial", 0) == 0
        ),
    }


def _validate_agentic_summary(directory: Path, expected_ids: set[str]) -> dict[str, Any]:
    response = _read_json(directory / "experiment_evaluation.json")
    status = _read_json(directory / "run_status.json")
    conditions = response.get("conditions", [])
    condition_ids = [str(item.get("conditionID") or "") for item in conditions]
    labels: Counter[str] = Counter()
    _collect_labels(conditions, labels)
    return {
        "condition_count": len(conditions),
        "unique_condition_count": len(set(condition_ids)),
        "missing_condition_ids": sorted(expected_ids - set(condition_ids)),
        "extra_condition_ids": sorted(set(condition_ids) - expected_ids),
        "state": status.get("state"),
        "completed": status.get("completed"),
        "failed": status.get("failed"),
        "partial_label_count": labels.get("partial", 0),
        "valid": (
            len(conditions) == 72
            and set(condition_ids) == expected_ids
            and len(set(condition_ids)) == 72
            and status.get("state") == "completed"
            and int(status.get("completed") or 0) == 72
            and int(status.get("failed") or 0) == 0
            and labels.get("partial", 0) == 0
        ),
    }


def main() -> int:
    input_ids = {path.stem for path in (EXPERIMENT_DIR / "inputs").glob("*.json")}
    if len(input_ids) != 72:
        raise ValueError(f"Expected 72 input IDs, found {len(input_ids)}")

    agentic_gpt5_dir = RESULTS_DIR / "agentic_gpt5"
    agentic_deepseek_dir = RESULTS_DIR / "agentic_deepseek_v4_flash"
    systems = {
        "agentic_gpt5": _validate_evaluated_dir(
            agentic_gpt5_dir / "evaluated", input_ids, "gpt-5"
        ),
        "baseline_gpt5": _validate_evaluated_dir(
            RESULTS_DIR / "baseline" / "GPT", input_ids, "gpt-5"
        ),
        "agentic_deepseek": _validate_evaluated_dir(
            agentic_deepseek_dir / "evaluated", input_ids, "deepseek-v4-flash"
        ),
        "baseline_deepseek": _validate_evaluated_dir(
            RESULTS_DIR / "baseline" / "Deepseek", input_ids, "deepseek-v4-flash"
        ),
    }
    agentic_summaries = {
        "agentic_gpt5": _validate_agentic_summary(agentic_gpt5_dir, input_ids),
        "agentic_deepseek": _validate_agentic_summary(agentic_deepseek_dir, input_ids),
    }
    report = {
        "experiment": "march_binary_webharbor72",
        "input_case_count": len(input_ids),
        "systems": systems,
        "agentic_summaries": agentic_summaries,
        "valid": all(item["valid"] for item in systems.values())
        and all(item["valid"] for item in agentic_summaries.values()),
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
