from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.schemas.judge import ExperimentEvaluationResponse  # noqa: E402


FIELD_MAP = {
    "Thinking Process": "thinking_process",
    "Evaluation": "evaluation_previous_goal",
    "Memory": "memory",
    "Next Goal": "next_goal",
    "Action": "action",
}
GENERIC_TASK_STATUS = re.compile(
    r"\b(successfully completed|task completed|completion status|"
    r"failed to complete)\b|\"success\"\s*:\s*(?:true|false)",
    re.IGNORECASE,
)


def _source_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify completeness, schema, shared criteria, and evidence grounding."
    )
    parser.add_argument("results_dir", type=Path)
    parser.add_argument(
        "--criteria",
        type=Path,
        default=ROOT
        / "technical_evaluation"
        / "webharbor_v13_judge_base_criteria.json",
    )
    args = parser.parse_args()
    results_dir = args.results_dir.resolve()

    response = ExperimentEvaluationResponse.model_validate_json(
        (results_dir / "experiment_evaluation.json").read_text(encoding="utf-8")
    )
    data = json.loads(
        (results_dir / "visualization_data.json").read_text(encoding="utf-8")
    )
    criteria = json.loads(args.criteria.read_text(encoding="utf-8"))
    expected_ids = {
        f"{base}-{condition}" for base in criteria for condition in ("A", "B", "C")
    }
    response_ids = {condition.conditionID for condition in response.conditions}
    cases = data.get("cases", [])
    case_ids = {str(case.get("case_id")) for case in cases}

    errors: list[str] = []
    warnings: list[str] = []
    if len(response.conditions) != 72:
        errors.append(f"experiment_evaluation conditions={len(response.conditions)}, expected 72")
    if len(cases) != 72:
        errors.append(f"visualization cases={len(cases)}, expected 72")
    if response_ids != expected_ids:
        errors.append(
            f"response IDs mismatch: missing={sorted(expected_ids-response_ids)}, "
            f"extra={sorted(response_ids-expected_ids)}"
        )
    if case_ids != expected_ids:
        errors.append(
            f"visualization IDs mismatch: missing={sorted(expected_ids-case_ids)}, "
            f"extra={sorted(case_ids-expected_ids)}"
        )

    for condition in response.conditions:
        for criterion in condition.criteria:
            step_statuses = [
                str(detail.evaluateStatus.value).upper()
                for detail in criterion.involved_steps
            ]
            for status in step_statuses:
                if status not in {"PASS", "FAIL"}:
                    errors.append(
                        f"{condition.conditionID}: non-binary step verdict {status!r}"
                    )
            if (
                str(criterion.overall_assessment.value).upper() == "FAIL"
                and step_statuses
                and any(status != "FAIL" for status in step_statuses)
            ):
                errors.append(
                    f"{condition.conditionID}: overall FAIL has a non-FAIL cited step"
                )
            if (
                str(criterion.overall_assessment.value).upper() == "PASS"
                and step_statuses
                and all(status != "PASS" for status in step_statuses)
            ):
                errors.append(
                    f"{condition.conditionID}: overall PASS has no PASS cited step"
                )

    evidence_count = 0
    screenshot_count = 0
    label_counts: dict[str, int] = {}
    for case in cases:
        case_id = str(case.get("case_id"))
        base = case_id.rsplit("-", 1)[0]
        expected_criterion = criteria.get(base)
        if case.get("criterion") != expected_criterion:
            errors.append(f"{case_id}: criterion differs from shared base criterion {base}")

        judge = case.get("judge", {})
        verdict = str(judge.get("verdict", "")).upper()
        label_counts[verdict] = label_counts.get(verdict, 0) + 1
        if verdict not in {"PASS", "FAIL"}:
            errors.append(f"{case_id}: non-binary verdict {verdict!r}")

        evidence = judge.get("evidence", []) or []
        if not evidence:
            warnings.append(f"{case_id}: no highlighted evidence")
        for item in evidence:
            evidence_count += 1
            evidence_verdict = str(item.get("verdict", "")).upper()
            if evidence_verdict not in {"PASS", "FAIL"}:
                errors.append(
                    f"{case_id}: non-binary evidence verdict {evidence_verdict!r}"
                )
            try:
                step_index = int(item["step_index"])
                step = case["steps"][step_index]
                field = FIELD_MAP[item["source_field"]]
                quote = str(item["highlighted_text"])
                source = _source_text(step.get(field))
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                errors.append(f"{case_id}: malformed evidence {item!r}: {exc}")
                continue
            if quote not in source:
                errors.append(
                    f"{case_id}: ungrounded evidence step={step_index} "
                    f"field={item.get('source_field')} quote={quote[:120]!r}"
                )
            if GENERIC_TASK_STATUS.search(quote):
                errors.append(
                    f"{case_id}: generic task-status evidence step={step_index} "
                    f"quote={quote[:120]!r}"
                )

        for screenshot in case.get("screenshots", []) or []:
            screenshot_count += 1
            screenshot_path = Path(str(screenshot))
            if not screenshot_path.is_absolute():
                screenshot_path = ROOT / screenshot_path
            if not screenshot_path.is_file():
                errors.append(f"{case_id}: missing screenshot {screenshot}")

        for step_key, step_verdict in (judge.get("step_verdicts", {}) or {}).items():
            normalized_step_verdict = str(step_verdict).upper()
            if normalized_step_verdict not in {"PASS", "FAIL"}:
                errors.append(
                    f"{case_id}: step {step_key} has non-binary visualization "
                    f"verdict {normalized_step_verdict!r}"
                )
            if verdict == "FAIL" and normalized_step_verdict != "FAIL":
                errors.append(
                    f"{case_id}: overall FAIL but visualization step {step_key} "
                    f"is {normalized_step_verdict!r}"
                )

    triplets: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        triplets.setdefault(str(case["case_id"]).rsplit("-", 1)[0], []).append(
            case.get("criterion", {})
        )
    for base, values in triplets.items():
        if len(values) != 3 or not all(value == values[0] for value in values):
            errors.append(f"{base}: A/B/C do not share one identical criterion")

    summary = {
        "valid": not errors,
        "conditions": len(response.conditions),
        "cases": len(cases),
        "labels": dict(sorted(label_counts.items())),
        "grounded_evidence": evidence_count,
        "screenshots": screenshot_count,
        "errors": errors,
        "warnings": warnings,
    }
    html_path = results_dir / "index.html"
    if html_path.is_file():
        html = html_path.read_text(encoding="utf-8")
        for marker in (
            "const binaryVerdict=",
            "const stepVerdict=",
        ):
            if marker not in html:
                errors.append(f"HTML missing binary-verdict marker: {marker}")
        for forbidden_marker in (
            "--partial-bg:",
            "PARTIAL · light support",
            ".timeline-eval.partial",
            "mark.evidence.partial",
        ):
            if forbidden_marker in html:
                errors.append(
                    f"HTML still contains non-binary marker: {forbidden_marker}"
                )
        summary["valid"] = not errors
        summary["errors"] = errors
    (results_dir / "verification.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
