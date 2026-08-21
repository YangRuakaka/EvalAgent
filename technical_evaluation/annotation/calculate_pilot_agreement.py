"""Calculate blinded human-vs-judge agreement for the 24-case pilot."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_DIR = (
    REPO_ROOT
    / "technical_evaluation"
    / "results"
    / "grounded_judge_webharbor_v13_v19_pilot_24"
)
DEFAULT_PILOT_DIR = Path(__file__).resolve().parent / "pilot_24_v19"


def _normalize_label(value: Any) -> str | None:
    label = str(value or "").strip().upper()
    return label if label in {"PASS", "FAIL"} else None


def _cohens_kappa(human: list[str], judge: list[str]) -> float | None:
    if not human:
        return None
    observed = sum(a == b for a, b in zip(human, judge)) / len(human)
    human_pass = human.count("PASS") / len(human)
    judge_pass = judge.count("PASS") / len(judge)
    expected = human_pass * judge_pass + (1 - human_pass) * (1 - judge_pass)
    if math.isclose(expected, 1.0):
        return 1.0 if math.isclose(observed, 1.0) else None
    return (observed - expected) / (1 - expected)


def _wilson_interval(hits: int, total: int) -> tuple[float | None, float | None]:
    if total == 0:
        return None, None
    z = 1.959963984540054
    p = hits / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def _load_human(path: Path) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    annotations = payload.get("annotations", {})
    overall: dict[str, str] = {}
    steps: dict[str, dict[str, str]] = {}
    for case_id, annotation in annotations.items():
        label = _normalize_label(annotation.get("overall_assessment"))
        if label:
            overall[str(case_id)] = label
        step_labels: dict[str, str] = {}
        for step_id, raw_label in (annotation.get("step_labels") or {}).items():
            normalized = _normalize_label(raw_label)
            if normalized:
                step_labels[str(step_id)] = normalized
        steps[str(case_id)] = step_labels
    return overall, steps


def calculate(
    human_path: Path,
    results_dir: Path,
    output_path: Path,
    allow_incomplete: bool,
) -> dict[str, Any]:
    human, human_steps = _load_human(human_path)
    judge_payload = json.loads(
        (results_dir / "visualization_data.json").read_text(encoding="utf-8")
    )
    cases = {str(item["case_id"]): item for item in judge_payload.get("cases", [])}
    expected_ids = set(cases)
    if len(expected_ids) != 24:
        raise ValueError(f"Expected 24 judge cases, found {len(expected_ids)}")
    missing = sorted(expected_ids - set(human))
    if missing and not allow_incomplete:
        raise ValueError(
            "Human annotations are incomplete; missing overall labels for: "
            + ", ".join(missing)
        )

    compared = sorted(expected_ids & set(human))
    human_labels = [human[case_id] for case_id in compared]
    judge_labels = [
        _normalize_label(cases[case_id].get("judge", {}).get("verdict")) or ""
        for case_id in compared
    ]
    hits = sum(a == b for a, b in zip(human_labels, judge_labels))
    confusion = {
        human_label: {
            judge_label: sum(
                h == human_label and j == judge_label
                for h, j in zip(human_labels, judge_labels)
            )
            for judge_label in ("PASS", "FAIL")
        }
        for human_label in ("PASS", "FAIL")
    }
    ci_low, ci_high = _wilson_interval(hits, len(compared))
    disagreements = [
        {
            "case_id": case_id,
            "human_verdict": human[case_id],
            "judge_verdict": _normalize_label(
                cases[case_id].get("judge", {}).get("verdict")
            ),
            "criterion": cases[case_id].get("criterion", {}).get("title"),
            "persona_value": cases[case_id].get("agent", {}).get("persona_value"),
        }
        for case_id in compared
        if human[case_id]
        != _normalize_label(cases[case_id].get("judge", {}).get("verdict"))
    ]

    step_hits = 0
    step_total = 0
    step_disagreements: list[dict[str, Any]] = []
    for case_id in compared:
        judge_steps = cases[case_id].get("judge", {}).get("step_verdicts", {})
        for step_id, human_label in human_steps.get(case_id, {}).items():
            judge_label = _normalize_label(judge_steps.get(str(step_id)))
            if judge_label is None:
                continue
            step_total += 1
            if human_label == judge_label:
                step_hits += 1
            else:
                step_disagreements.append(
                    {
                        "case_id": case_id,
                        "step_id": step_id,
                        "human_verdict": human_label,
                        "judge_verdict": judge_label,
                    }
                )

    report = {
        "pilot": "webharbor_v13_grounded_v19_pilot_24",
        "judge_version": judge_payload.get("judge_version"),
        "primary_case_level": {
            "expected_cases": 24,
            "compared_cases": len(compared),
            "missing_human_cases": missing,
            "agreements": hits,
            "disagreements": len(disagreements),
            "agreement_rate": hits / len(compared) if compared else None,
            "agreement_rate_95pct_wilson_ci": [ci_low, ci_high],
            "cohens_kappa": _cohens_kappa(human_labels, judge_labels),
            "human_label_distribution": {
                "PASS": human_labels.count("PASS"),
                "FAIL": human_labels.count("FAIL"),
            },
            "judge_label_distribution": {
                "PASS": judge_labels.count("PASS"),
                "FAIL": judge_labels.count("FAIL"),
            },
            "confusion_matrix_human_rows_judge_columns": confusion,
        },
        "secondary_step_level": {
            "compared_steps": step_total,
            "agreements": step_hits,
            "agreement_rate": step_hits / step_total if step_total else None,
            "disagreements": step_disagreements,
        },
        "case_disagreements": disagreements,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    markdown_path = output_path.with_suffix(".md")
    primary = report["primary_case_level"]
    markdown_path.write_text(
        "\n".join(
            [
                "# Human–Judge Pilot Agreement",
                "",
                f"- Compared cases: {primary['compared_cases']}/24",
                f"- Exact agreements: {primary['agreements']}",
                f"- Agreement rate: {primary['agreement_rate']}",
                f"- Cohen's kappa: {primary['cohens_kappa']}",
                f"- Step-level agreement: "
                f"{report['secondary_step_level']['agreement_rate']}",
                "",
                "See the JSON report for the confusion matrix and disagreement cases.",
            ]
        ),
        encoding="utf-8",
    )
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calculate PASS/FAIL agreement for the 24-case pilot."
    )
    parser.add_argument("--human-annotations", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_PILOT_DIR / "agreement_report.json",
    )
    parser.add_argument("--allow-incomplete", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    report = calculate(
        args.human_annotations.resolve(),
        args.results_dir.resolve(),
        args.output.resolve(),
        args.allow_incomplete,
    )
    primary = report["primary_case_level"]
    print(
        f"agreement={primary['agreement_rate']} "
        f"kappa={primary['cohens_kappa']} "
        f"n={primary['compared_cases']}"
    )
