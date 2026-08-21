"""Compute Dan-only accuracy and strict evidence metrics for all four systems."""

from __future__ import annotations

import json
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPERIMENT_DIR = Path(__file__).resolve().parent
ROOT = EXPERIMENT_DIR.parents[2]
ANALYSIS_DIR = ROOT / "technical_evaluation" / "analysis"
if str(ANALYSIS_DIR) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_DIR))

import compare_criteria1_agreement as metrics


HUMAN_FILE = (
    ROOT
    / "technical_evaluation"
    / "experiments"
    / "march_binary_dan48"
    / "dan_criteria1_annotations.json"
)
PROJECTION_ROOT = EXPERIMENT_DIR / "dan48_projection"
SYSTEMS = {
    "agentic_gpt5": EXPERIMENT_DIR / "results" / "agentic_gpt5" / "evaluated",
    "baseline_gpt5": EXPERIMENT_DIR / "results" / "baseline" / "GPT",
    "agentic_deepseek": EXPERIMENT_DIR
    / "results"
    / "agentic_deepseek_v4_flash"
    / "evaluated",
    "baseline_deepseek": EXPERIMENT_DIR / "results" / "baseline" / "Deepseek",
}


def _project_dan_files(source_dir: Path, target_dir: Path, dan_ids: set[str]) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for stale in target_dir.glob("*__evaluated.json"):
        stale.unlink()
    copied_ids: set[str] = set()
    for source in source_dir.glob("*__evaluated.json"):
        record = json.loads(source.read_text(encoding="utf-8"))
        case_id = str(record.get("data_id") or "")
        if case_id not in dan_ids:
            continue
        if case_id in copied_ids:
            raise ValueError(f"Duplicate source result for {case_id}: {source_dir}")
        shutil.copy2(source, target_dir / source.name)
        copied_ids.add(case_id)
    if copied_ids != dan_ids:
        raise ValueError(
            f"Projection mismatch for {source_dir}: "
            f"missing={sorted(dan_ids - copied_ids)} extra={sorted(copied_ids - dan_ids)}"
        )


def _raw_overall_labels(results_dir: Path) -> dict[str, str]:
    labels: dict[str, str] = {}
    for path in results_dir.glob("*__evaluated.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        case_id = str(record.get("data_id") or "")
        result = metrics._extract_criteria1_result(record) or {}
        labels[case_id] = str(result.get("overall_assessment") or "missing").strip().lower()
    return labels


def _pct(value: Any) -> str:
    return "N/A" if value is None else f"{100 * float(value):.2f}%"


def main() -> int:
    human_cases = metrics._load_human_cases(HUMAN_FILE)
    dan_ids = set(human_cases)
    if len(dan_ids) != 48:
        raise ValueError(f"Expected 48 Dan cases, found {len(dan_ids)}")
    human_labels = {
        case_id: str(case["overall_assessment"])
        for case_id, case in human_cases.items()
    }

    systems: dict[str, Any] = {}
    for system_id, source_dir in SYSTEMS.items():
        projected_dir = PROJECTION_ROOT / system_id
        _project_dan_files(source_dir, projected_dir, dan_ids)

        model_labels = metrics._load_model_labels(projected_dir)
        agreement = metrics._build_model_vs_human_metrics(
            model_labels=model_labels,
            human_labels=human_labels,
            label_space=metrics.SUPPORTED_LABELS,
            model_distribution_key="model_distribution",
        )
        confusion = agreement["confusion_matrix"]
        correct = sum(
            int(confusion.get(label, {}).get(label, 0))
            for label in metrics.SUPPORTED_LABELS
        )
        raw_labels = _raw_overall_labels(projected_dir)
        unknown_cases = sorted(
            case_id
            for case_id, label in raw_labels.items()
            if label not in metrics.SUPPORTED_LABELS
        )
        grounding = metrics._compute_evidence_substring_accuracy(projected_dir, system_id)
        hit = metrics._compute_model_human_step_label_hit_rates(
            results_dir=projected_dir,
            model_name=system_id,
            human_cases=human_cases,
            require_grounded_evidence=True,
        )
        step_accuracy = metrics._compute_model_vs_human_step_verdict_accuracy(
            model_results_dir=projected_dir,
            model_name=system_id,
            human_cases=human_cases,
            require_grounded_model_evidence=True,
        )
        systems[system_id] = {
            "projected_results_dir": str(projected_dir),
            "dan_case_count": len(dan_ids),
            "evaluable_final_verdict_count": agreement["sample_size"],
            "unknown_final_verdict_count": len(unknown_cases),
            "unknown_final_verdict_case_ids": unknown_cases,
            "correct_final_verdict_count": correct,
            "accuracy_on_evaluable": agreement["accuracy"],
            "accuracy_all_48_unknown_as_incorrect": correct / len(dan_ids),
            "macro_f1_on_evaluable": agreement["macro_f1"],
            "cohens_kappa_on_evaluable": agreement["cohens_kappa"],
            "human_distribution": agreement["human_distribution"],
            "model_distribution": agreement["model_distribution"],
            "confusion_matrix": agreement["confusion_matrix"],
            "grounding_accuracy": grounding["substring_grounding_accuracy"],
            "grounding_numerator": grounding["substring_grounded_items"],
            "grounding_denominator": grounding["evidence_items_total"],
            "hit_rate": hit["evidence_human_label_hit_rate"],
            "hit_numerator": hit["evidence_hits"],
            "hit_denominator": hit["evidence_items_compared"],
            "overlap_rate": hit["model_evidence_also_human_and_grounded_rate"],
            "overlap_numerator": hit["model_evidence_items_also_human_and_grounded"],
            "overlap_denominator": hit["model_evidence_items_total"],
            "strict_step_accuracy": step_accuracy["step_verdict_accuracy"],
            "strict_step_hits": step_accuracy["step_verdict_hits"],
            "strict_step_denominator": step_accuracy["human_steps_compared"],
            "step_accuracy_given_overlap": step_accuracy[
                "step_verdict_accuracy_given_step_field_overlap"
            ],
            "step_overlap_denominator": step_accuracy["step_overlap_items"],
        }

    report = {
        "experiment_id": "march_binary_webharbor72_dan48_projection",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "human_file": str(HUMAN_FILE),
        "human_case_count": len(dan_ids),
        "human_evidence_items": sum(
            len(case.get("evidence") or []) for case in human_cases.values()
        ),
        "accuracy_policy": {
            "primary": "correct final verdict / all 48 Dan cases; unknown counts as incorrect",
            "secondary": "accuracy on evaluable pass/fail verdicts only",
        },
        "step_alignment": (
            "strict one-to-one model step_index -> raw steps[index].step_id -> "
            "human step_id; normalized source field must match"
        ),
        "systems": systems,
    }
    json_path = EXPERIMENT_DIR / "dan48_metrics.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# March-binary WebHarbor-72 Judge × Dan-48",
        "",
        "Primary accuracy uses all 48 Dan cases and counts a final `unknown` as incorrect.",
        "",
        "| System | Correct / 48 | Accuracy | Evaluable-only | Grounding | Hit rate | Overlap | Strict step accuracy |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for system_id, item in systems.items():
        lines.append(
            f"| {system_id} | {item['correct_final_verdict_count']}/48 | "
            f"{_pct(item['accuracy_all_48_unknown_as_incorrect'])} | "
            f"{_pct(item['accuracy_on_evaluable'])} "
            f"({item['evaluable_final_verdict_count']}/48 evaluable) | "
            f"{_pct(item['grounding_accuracy'])} "
            f"({item['grounding_numerator']}/{item['grounding_denominator']}) | "
            f"{_pct(item['hit_rate'])} "
            f"({item['hit_numerator']}/{item['hit_denominator']}) | "
            f"{_pct(item['overlap_rate'])} "
            f"({item['overlap_numerator']}/{item['overlap_denominator']}) | "
            f"{_pct(item['strict_step_accuracy'])} "
            f"({item['strict_step_hits']}/{item['strict_step_denominator']}) |"
        )
    lines.extend(["", "## Final-verdict unknown cases", ""])
    for system_id, item in systems.items():
        unknown = item["unknown_final_verdict_case_ids"]
        lines.append(f"- `{system_id}`: {', '.join(unknown) if unknown else 'none'}")
    md_path = EXPERIMENT_DIR / "dan48_metrics.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"json": str(json_path), "markdown": str(md_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
