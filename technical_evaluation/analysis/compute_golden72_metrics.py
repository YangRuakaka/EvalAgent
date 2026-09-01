"""Pool the original 33-case evaluation with the WebHarbor-72 golden set.

Counts are pooled before division. The summary composite uses four metrics:
final-verdict accuracy, grounding, human-evidence hit rate, and overlap.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


THIS_DIR = Path(__file__).resolve().parent
ROOT = THIS_DIR.parents[1]
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

import compare_criteria1_agreement as metrics


EXPERIMENT_DIR = ROOT / "technical_evaluation" / "experiments" / "march_binary_webharbor72"
OLD_METRICS_FILE = (
    ROOT / "technical_evaluation" / "results" / "criteria1_gpt5_deepseek_human_metrics.json"
)
OLD_HUMAN_FILE = ROOT / "technical_evaluation" / "results" / "Yukun_criteria1_annotations.json"
SYSTEMS = {
    "agentic_gpt5": EXPERIMENT_DIR / "results" / "agentic_gpt5" / "evaluated",
    "baseline_gpt5": EXPERIMENT_DIR / "results" / "baseline" / "GPT",
    "agentic_deepseek": EXPERIMENT_DIR
    / "results"
    / "agentic_deepseek_v4_flash"
    / "evaluated",
    "baseline_deepseek": EXPERIMENT_DIR / "results" / "baseline" / "Deepseek",
}

OLD_KEYS = {
    "agentic_gpt5": ("gpt5_vs_human", "gpt5"),
    "baseline_gpt5": ("baseline_gpt5_vs_human", "baseline_gpt5"),
    "agentic_deepseek": ("deepseek_vs_human", "deepseek"),
    "baseline_deepseek": ("baseline_deepseek_vs_human", "baseline_deepseek"),
}


def _wilson_interval(successes: int, n: int, z: float = 1.959963984540054) -> list[float]:
    if n == 0:
        return []
    proportion = successes / n
    denominator = 1 + z * z / n
    center = (proportion + z * z / (2 * n)) / denominator
    half_width = (
        z
        * math.sqrt(proportion * (1 - proportion) / n + z * z / (4 * n * n))
        / denominator
    )
    return [center - half_width, center + half_width]


def _raw_overall_labels(results_dir: Path) -> dict[str, str]:
    labels: dict[str, str] = {}
    for path in results_dir.glob("*__evaluated.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        case_id = str(record.get("data_id") or "")
        result = metrics._extract_criteria1_result(record) or {}
        labels[case_id] = str(result.get("overall_assessment") or "missing").strip().lower()
    return labels


def _exact_mcnemar_p(agentic_only: int, baseline_only: int) -> float:
    discordant = agentic_only + baseline_only
    if discordant == 0:
        return 1.0
    lower_tail = sum(
        math.comb(discordant, k)
        for k in range(min(agentic_only, baseline_only) + 1)
    ) / (2**discordant)
    return min(1.0, 2 * lower_tail)


def _pct(value: Any) -> str:
    return "N/A" if value is None else f"{100 * float(value):.2f}%"


def _correct_from_confusion(confusion: dict[str, dict[str, int]]) -> int:
    return sum(confusion.get(label, {}).get(label, 0) for label in metrics.SUPPORTED_LABELS)


def _merge_confusions(
    left: dict[str, dict[str, int]], right: dict[str, dict[str, int]]
) -> dict[str, dict[str, int]]:
    return {
        human: {
            predicted: left.get(human, {}).get(predicted, 0)
            + right.get(human, {}).get(predicted, 0)
            for predicted in metrics.SUPPORTED_LABELS
        }
        for human in metrics.SUPPORTED_LABELS
    }


def _apply_data_000032_binary_adjudication(old_report: dict[str, Any]) -> None:
    """Relabel the sole old human `partial` case as `fail` in verdict tables."""
    for verdict_key, _ in OLD_KEYS.values():
        verdict = old_report[verdict_key]
        confusion = verdict["confusion_matrix"]
        for predicted in metrics.SUPPORTED_LABELS:
            moved = confusion.get("partial", {}).get(predicted, 0)
            confusion.setdefault("fail", {}).setdefault(predicted, 0)
            confusion["fail"][predicted] += moved
            confusion.setdefault("partial", {})[predicted] = 0
        distribution = verdict.get("human_distribution")
        if isinstance(distribution, dict):
            moved = int(distribution.get("partial", 0))
            distribution["partial"] = 0
            distribution["fail"] = int(distribution.get("fail", 0)) + moved


def _kappa_from_confusion(confusion: dict[str, dict[str, int]]) -> float | None:
    n = sum(sum(row.values()) for row in confusion.values())
    if n == 0:
        return None
    observed = _correct_from_confusion(confusion) / n
    expected = sum(
        sum(confusion[label].values())
        * sum(confusion[human][label] for human in metrics.SUPPORTED_LABELS)
        for label in metrics.SUPPORTED_LABELS
    ) / (n * n)
    return 1.0 if expected == 1.0 and observed == 1.0 else (observed - expected) / (1 - expected)


def _score_system(
    system_id: str,
    results_dir: Path,
    human_cases: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    human_labels = {
        case_id: str(case["overall_assessment"])
        for case_id, case in human_cases.items()
    }
    model_labels = metrics._load_model_labels(results_dir)
    agreement = metrics._build_model_vs_human_metrics(
        model_labels=model_labels,
        human_labels=human_labels,
        label_space=metrics.SUPPORTED_LABELS,
        model_distribution_key="model_distribution",
    )
    raw_labels = _raw_overall_labels(results_dir)
    unknown_cases = sorted(
        case_id
        for case_id, label in raw_labels.items()
        if label not in metrics.SUPPORTED_LABELS
    )
    correct = sum(
        raw_labels.get(case_id) == human_label
        for case_id, human_label in human_labels.items()
    )
    pass_ids = [case_id for case_id, label in human_labels.items() if label == "pass"]
    fail_ids = [case_id for case_id, label in human_labels.items() if label == "fail"]
    pass_hits = sum(raw_labels.get(case_id) == "pass" for case_id in pass_ids)
    fail_hits = sum(raw_labels.get(case_id) == "fail" for case_id in fail_ids)

    grounding = metrics._compute_evidence_substring_accuracy(results_dir, system_id)
    hit = metrics._compute_model_human_step_label_hit_rates(
        results_dir=results_dir,
        model_name=system_id,
        human_cases=human_cases,
        require_grounded_evidence=True,
    )
    n = len(human_labels)
    accuracy = correct / n
    refreshed_components = {
        "verdict": accuracy,
        "grounding": grounding["substring_grounding_accuracy"],
        "hit_rate": hit["evidence_human_label_hit_rate"],
        "overlap": hit["model_evidence_also_human_and_grounded_rate"],
    }
    refreshed_score = sum(refreshed_components.values()) / len(refreshed_components)

    return {
        "case_count": n,
        "correct_final_verdict_count": correct,
        "accuracy_all_cases_unknown_as_incorrect": accuracy,
        "accuracy_wilson_95_ci": _wilson_interval(correct, n),
        "accuracy_on_evaluable": agreement["accuracy"],
        "evaluable_count": agreement["sample_size"],
        "unknown_count": len(unknown_cases),
        "unknown_case_ids": unknown_cases,
        "macro_f1_on_evaluable": agreement["macro_f1"],
        "cohens_kappa_on_evaluable": agreement["cohens_kappa"],
        "sensitivity_pass": pass_hits / len(pass_ids),
        "specificity_fail": fail_hits / len(fail_ids),
        "balanced_accuracy": 0.5
        * (pass_hits / len(pass_ids) + fail_hits / len(fail_ids)),
        "confusion_matrix_evaluable": agreement["confusion_matrix"],
        "grounding_accuracy": grounding["substring_grounding_accuracy"],
        "grounding_numerator": grounding["substring_grounded_items"],
        "grounding_denominator": grounding["evidence_items_total"],
        "hit_rate": hit["evidence_human_label_hit_rate"],
        "hit_numerator": hit["evidence_hits"],
        "hit_denominator": hit["evidence_items_compared"],
        "overlap_rate": hit["model_evidence_also_human_and_grounded_rate"],
        "overlap_numerator": hit["model_evidence_items_also_human_and_grounded"],
        "overlap_denominator": hit["model_evidence_items_total"],
        "refreshed_four_metric_components": refreshed_components,
        "refreshed_four_metric_composite": refreshed_score,
    }


def _pool_system(
    system_id: str,
    old_report: dict[str, Any],
    new_item: dict[str, Any],
    total_cases: int,
) -> dict[str, Any]:
    verdict_key, evidence_key = OLD_KEYS[system_id]
    old_verdict = old_report[verdict_key]
    old_confusion = old_verdict["confusion_matrix"]
    new_confusion = new_item["confusion_matrix_evaluable"]
    combined_confusion = _merge_confusions(old_confusion, new_confusion)
    old_correct = _correct_from_confusion(old_confusion)
    correct = old_correct + new_item["correct_final_verdict_count"]
    evaluable = old_verdict["sample_size"] + new_item["evaluable_count"]

    old_grounding = old_report["evidence_substring_accuracy"][evidence_key]
    old_hit = old_report["evidence_vs_human_label_hit_rate"][evidence_key]

    grounding_num = old_grounding["substring_grounded_items"] + new_item["grounding_numerator"]
    grounding_den = old_grounding["evidence_items_total"] + new_item["grounding_denominator"]
    hit_num = old_hit["evidence_hits"] + new_item["hit_numerator"]
    hit_den = old_hit["evidence_items_compared"] + new_item["hit_denominator"]
    overlap_num = (
        old_hit["model_evidence_items_also_human_and_grounded"]
        + new_item["overlap_numerator"]
    )
    overlap_den = old_hit["model_evidence_items_total"] + new_item["overlap_denominator"]

    accuracy_all = correct / total_cases
    accuracy_evaluable = correct / evaluable
    grounding = grounding_num / grounding_den
    hit = hit_num / hit_den
    overlap = overlap_num / overlap_den
    components = {
        "verdict_all_cases_missing_or_unknown_as_incorrect": accuracy_all,
        "grounding_pooled_by_item_count": grounding,
        "hit_rate_pooled_by_human_evidence_count": hit,
        "overlap_pooled_by_model_evidence_count": overlap,
    }

    return {
        "case_count": total_cases,
        "correct_final_verdict_count": correct,
        "missing_or_unknown_count": total_cases - evaluable,
        "accuracy_all_cases_missing_or_unknown_as_incorrect": accuracy_all,
        "accuracy_all_cases_wilson_95_ci": _wilson_interval(correct, total_cases),
        "evaluable_count": evaluable,
        "accuracy_on_evaluable": accuracy_evaluable,
        "accuracy_evaluable_wilson_95_ci": _wilson_interval(correct, evaluable),
        "cohens_kappa_on_evaluable": _kappa_from_confusion(combined_confusion),
        "confusion_matrix_evaluable": combined_confusion,
        "grounding_accuracy": grounding,
        "grounding_numerator": grounding_num,
        "grounding_denominator": grounding_den,
        "hit_rate": hit,
        "hit_numerator": hit_num,
        "hit_denominator": hit_den,
        "overlap_rate": overlap,
        "overlap_numerator": overlap_num,
        "overlap_denominator": overlap_den,
        "four_metric_components": components,
        "four_metric_composite": sum(components.values()) / len(components),
        "old_33_contribution": {
            "correct": old_correct,
            "evaluable": old_verdict["sample_size"],
        },
        "new_72_contribution": {
            "correct": new_item["correct_final_verdict_count"],
            "evaluable": new_item["evaluable_count"],
        },
    }


def _pairwise_test(
    human_cases: dict[str, dict[str, Any]],
    agentic_dir: Path,
    baseline_dir: Path,
) -> dict[str, Any]:
    human = {case_id: case["overall_assessment"] for case_id, case in human_cases.items()}
    agentic = _raw_overall_labels(agentic_dir)
    baseline = _raw_overall_labels(baseline_dir)
    agentic_only = sum(
        agentic.get(case_id) == label and baseline.get(case_id) != label
        for case_id, label in human.items()
    )
    baseline_only = sum(
        baseline.get(case_id) == label and agentic.get(case_id) != label
        for case_id, label in human.items()
    )
    return {
        "agentic_correct_baseline_wrong": agentic_only,
        "baseline_correct_agentic_wrong": baseline_only,
        "exact_two_sided_mcnemar_p": _exact_mcnemar_p(agentic_only, baseline_only),
    }


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Combined Technical Evaluation: Final Results",
        "",
        "## Experiment setup",
        "",
        "The evaluation pools the original 33 cases and the new 72-case WebHarbor golden set: 105 cases and 967 human evidence items. Human verdicts use binary `pass`/`fail` labels. The four-metric total is the unweighted mean of final-verdict accuracy, grounding, human-evidence hit rate, and evidence overlap.",
        "",
        "## Final results",
        "",
        "| System | Verdict (all 105) | Evaluable-only | Kappa | Grounding | Hit | Overlap | Four-metric total |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for system_id, item in report["combined_105"]["systems"].items():
        lines.append(
            f"| {system_id} | {item['correct_final_verdict_count']}/105 "
            f"({_pct(item['accuracy_all_cases_missing_or_unknown_as_incorrect'])}) | "
            f"{item['correct_final_verdict_count']}/{item['evaluable_count']} "
            f"({_pct(item['accuracy_on_evaluable'])}) | "
            f"{item['cohens_kappa_on_evaluable']:.3f} | "
            f"{_pct(item['grounding_accuracy'])} | {_pct(item['hit_rate'])} | "
            f"{_pct(item['overlap_rate'])} | "
            f"{100 * item['four_metric_composite']:.2f}/100 |"
        )
    lines.extend(
        [
            "",
            "## Cross-model summary",
            "",
            f"- Agentic Judge mean total: {100 * report['combined_105']['cross_model_summary']['agentic_mean_composite']:.2f}/100",
            f"- Baseline mean total: {100 * report['combined_105']['cross_model_summary']['baseline_mean_composite']:.2f}/100",
            f"- Agentic advantage: {100 * report['combined_105']['cross_model_summary']['agentic_advantage']:.2f} points",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--human-file", type=Path, required=True)
    parser.add_argument(
        "--baseline-gpt-dir",
        type=Path,
        default=SYSTEMS["baseline_gpt5"],
        help="Optional merged/overlaid baseline GPT-5 results directory for the 72-case set.",
    )
    parser.add_argument(
        "--old-baseline-gpt-metrics-file",
        type=Path,
        default=None,
        help="Optional 33-case metrics report whose baseline GPT-5 sections replace the published report sections.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=ROOT / "technical_evaluation" / "results" / "webharbor105_combined_metrics_after_rerun.json",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=ROOT / "technical_evaluation" / "results" / "webharbor105_combined_metrics_after_rerun.md",
    )
    args = parser.parse_args()

    human_cases = metrics._load_human_cases(args.human_file)
    if len(human_cases) != 72:
        raise ValueError(f"Expected 72 golden cases, found {len(human_cases)}")
    system_dirs = dict(SYSTEMS)
    system_dirs["baseline_gpt5"] = args.baseline_gpt_dir.resolve()
    new_systems = {
        system_id: _score_system(system_id, results_dir, human_cases)
        for system_id, results_dir in system_dirs.items()
    }
    old_report = json.loads(OLD_METRICS_FILE.read_text(encoding="utf-8"))
    if args.old_baseline_gpt_metrics_file is not None:
        rerun_old_report = json.loads(
            args.old_baseline_gpt_metrics_file.read_text(encoding="utf-8")
        )
        old_report["baseline_gpt5_vs_human"] = rerun_old_report[
            "baseline_gpt5_vs_human"
        ]
        for section in (
            "evidence_substring_accuracy",
            "evidence_vs_human_label_hit_rate",
        ):
            old_report[section]["baseline_gpt5"] = rerun_old_report[section][
                "baseline_gpt5"
            ]
    _apply_data_000032_binary_adjudication(old_report)
    old_human_cases = metrics._load_human_cases(OLD_HUMAN_FILE)
    total_cases = len(old_human_cases) + len(human_cases)
    combined_systems = {
        system_id: _pool_system(system_id, old_report, item, total_cases)
        for system_id, item in new_systems.items()
    }
    agentic_mean = 0.5 * (
        combined_systems["agentic_gpt5"]["four_metric_composite"]
        + combined_systems["agentic_deepseek"]["four_metric_composite"]
    )
    baseline_mean = 0.5 * (
        combined_systems["baseline_gpt5"]["four_metric_composite"]
        + combined_systems["baseline_deepseek"]["four_metric_composite"]
    )
    new_pass_count = sum(
        case["overall_assessment"] == "pass" for case in human_cases.values()
    )
    old_distribution = old_report["gpt5_vs_human"]["human_distribution"]
    pass_count = old_distribution["pass"] + new_pass_count
    partial_count = old_distribution["partial"] + sum(
        case["overall_assessment"] == "partial" for case in human_cases.values()
    )
    old_ids = set(old_human_cases)
    new_ids = set(human_cases)
    report = {
        "experiment_id": "combined_original33_plus_webharbor72",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "old_human_file": str(OLD_HUMAN_FILE),
        "new_human_file": str(args.human_file),
        "baseline_gpt_new_results_dir": str(system_dirs["baseline_gpt5"]),
        "baseline_gpt_old_metrics_overlay": (
            str(args.old_baseline_gpt_metrics_file.resolve())
            if args.old_baseline_gpt_metrics_file is not None
            else None
        ),
        "case_counts": {"old": len(old_human_cases), "new": len(human_cases), "combined": total_cases},
        "case_overlap_check": {
            "method": "exact_case_id_intersection",
            "intersection_count": len(old_ids & new_ids),
            "intersection_ids": sorted(old_ids & new_ids),
        },
        "binary_adjudication": {
            "case_id": "data_000032",
            "source_file": "buy_milk_tradition_20250925_131407.json",
            "previous_human_verdict": "partial",
            "final_human_verdict": "fail",
            "reason": "No grounded cultural, religious, or familial custom is identified or compared; whole/organic milk and established branding are unsupported proxies for Tradition.",
        },
        "combined_human_evidence_count": old_report["evidence_vs_human_label_hit_rate"]["gpt5"]["evidence_items_compared"]
        + sum(len(case["evidence"]) for case in human_cases.values()),
        "new_72": {"systems": new_systems},
        "combined_105": {
            "systems": combined_systems,
            "cross_model_summary": {
                "agentic_mean_composite": agentic_mean,
                "baseline_mean_composite": baseline_mean,
                "agentic_advantage": agentic_mean - baseline_mean,
            },
        },
        "paired_verdict_tests": {
            "gpt5": _pairwise_test(
                human_cases, system_dirs["agentic_gpt5"], system_dirs["baseline_gpt5"]
            ),
            "deepseek": _pairwise_test(
                human_cases,
                system_dirs["agentic_deepseek"],
                system_dirs["baseline_deepseek"],
            ),
        },
        "ppi": {
            "is_standalone_reliability_score": False,
            "labeled_cases": total_cases,
            "unlabeled_cases_in_supplied_dataset": 0,
            "human_pass_count": pass_count,
            "human_partial_count": partial_count,
            "human_pass_prevalence_partial_as_nonpass": pass_count / total_cases,
            "human_pass_or_partial_prevalence": (pass_count + partial_count) / total_cases,
            "same_set_mean_ppi_result_partial_as_nonpass": pass_count / total_cases,
            "interpretation": (
                "With human labels on every pooled case, the PPI mean estimator "
                "reduces exactly to the direct human mean and adds no information."
            ),
        },
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.output_md.write_text(_render_markdown(report), encoding="utf-8")
    print(json.dumps({"json": str(args.output_json), "markdown": str(args.output_md)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
