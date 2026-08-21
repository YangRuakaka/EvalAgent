"""Compute strict grounding/hit/overlap metrics for the full Dan-48 GPT-5 run."""

from __future__ import annotations

import argparse
import json
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

import compare_criteria1_agreement as legacy_metrics


SYSTEM_DIRS = {
    "agentic_gpt5": EXPERIMENT_DIR / "results" / "agentic_gpt5" / "evaluated",
    "baseline_gpt5": EXPERIMENT_DIR / "results" / "baseline" / "GPT",
}


def _audit_labels(results_dir: Path) -> dict[str, Any]:
    overall = Counter()
    raw_overall = Counter()
    non_binary_overall_cases: list[dict[str, str]] = []
    partial_paths: list[str] = []
    data_ids: list[str] = []
    files = sorted(results_dir.rglob("*__evaluated.json")) if results_dir.exists() else []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if key in {"overall_assessment", "evaluateStatus", "verdict"}:
                    if str(item or "").strip().lower() == "partial":
                        partial_paths.append(child_path)
                visit(item, child_path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")

    for path in files:
        record = json.loads(path.read_text(encoding="utf-8"))
        data_id = str(record.get("data_id") or "").strip()
        data_ids.append(data_id)
        criteria1_result = legacy_metrics._extract_criteria1_result(record)
        raw_overall_label = str(
            criteria1_result.get("overall_assessment") if isinstance(criteria1_result, dict) else ""
        ).strip().lower()
        raw_overall[raw_overall_label or "missing"] += 1
        if raw_overall_label not in {"pass", "fail"}:
            non_binary_overall_cases.append(
                {"data_id": data_id, "label": raw_overall_label or "missing"}
            )
        case = legacy_metrics._extract_model_case(record)
        if case:
            overall[str(case.get("overall_assessment"))] += 1
        before = len(partial_paths)
        visit(record, path.name)
        if len(partial_paths) > before:
            partial_paths[before:] = [f"{path.name}:{item}" for item in partial_paths[before:]]

    return {
        "evaluated_file_count": len(files),
        "data_ids": data_ids,
        "unique_data_id_count": len(set(data_ids)),
        "duplicate_data_ids": sorted(
            data_id for data_id, count in Counter(data_ids).items() if data_id and count > 1
        ),
        "overall_label_counts": dict(sorted(overall.items())),
        "raw_overall_label_counts": dict(sorted(raw_overall.items())),
        "binary_overall_label_coverage": sum(
            count for label, count in raw_overall.items() if label in {"pass", "fail"}
        ),
        "non_binary_overall_cases": non_binary_overall_cases,
        "partial_label_occurrences": len(partial_paths),
        "partial_label_paths": partial_paths[:50],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-dir", type=Path, default=EXPERIMENT_DIR)
    args = parser.parse_args()
    experiment_dir = args.experiment_dir.resolve()

    manifest = json.loads((experiment_dir / "sample_manifest.json").read_text(encoding="utf-8"))
    case_ids = [str(item["case_id"]) for item in manifest["cases"]]
    human_file = experiment_dir / "dan_criteria1_annotations.json"
    all_human_cases = legacy_metrics._load_human_cases(human_file)
    human_cases = {case_id: all_human_cases[case_id] for case_id in case_ids}

    system_dirs = {
        key: experiment_dir / path.relative_to(EXPERIMENT_DIR)
        for key, path in SYSTEM_DIRS.items()
    }
    systems: dict[str, Any] = {}
    for system_id, results_dir in system_dirs.items():
        grounding = legacy_metrics._compute_evidence_substring_accuracy(
            results_dir=results_dir,
            model_name=system_id,
        )
        hit = legacy_metrics._compute_model_human_step_label_hit_rates(
            results_dir=results_dir,
            model_name=system_id,
            human_cases=human_cases,
            require_grounded_evidence=True,
        )
        audit = _audit_labels(results_dir)
        actual_ids = set(audit["data_ids"])
        expected_ids = set(case_ids)
        audit["missing_case_ids"] = sorted(expected_ids - actual_ids)
        audit["extra_case_ids"] = sorted(actual_ids - expected_ids)
        complete = (
            audit["evaluated_file_count"] == len(case_ids)
            and audit["unique_data_id_count"] == len(case_ids)
            and not audit["missing_case_ids"]
            and not audit["extra_case_ids"]
        )
        progress_metrics = {
            "grounding_accuracy": grounding.get("substring_grounding_accuracy"),
            "grounding_numerator": grounding.get("substring_grounded_items"),
            "grounding_denominator": grounding.get("evidence_items_total"),
            "hit_rate": hit.get("evidence_human_label_hit_rate"),
            "hit_numerator": hit.get("evidence_hits"),
            "hit_denominator": hit.get("evidence_items_compared"),
            "overlap_rate": hit.get("model_evidence_also_human_and_grounded_rate"),
            "overlap_numerator": hit.get("model_evidence_items_also_human_and_grounded"),
            "overlap_denominator": hit.get("model_evidence_items_total"),
        }
        systems[system_id] = {
            "results_dir": str(results_dir),
            "status": "complete" if complete else "incomplete",
            "completed_cases": audit["evaluated_file_count"],
            "expected_cases": len(case_ids),
            "grounding_accuracy": progress_metrics["grounding_accuracy"] if complete else None,
            "grounding_numerator": progress_metrics["grounding_numerator"] if complete else None,
            "grounding_denominator": progress_metrics["grounding_denominator"] if complete else None,
            "hit_rate": progress_metrics["hit_rate"] if complete else None,
            "hit_numerator": progress_metrics["hit_numerator"] if complete else None,
            "hit_denominator": progress_metrics["hit_denominator"] if complete else None,
            "overlap_rate": progress_metrics["overlap_rate"] if complete else None,
            "overlap_numerator": progress_metrics["overlap_numerator"] if complete else None,
            "overlap_denominator": progress_metrics["overlap_denominator"] if complete else None,
            "incomplete_progress_metrics": progress_metrics if not complete else None,
            "ungrounded_model_evidence": hit.get("ungrounded_evidence_skipped"),
            "cases_covered": hit.get("human_cases_covered"),
            "label_audit": audit,
            "grounding_details": grounding,
            "hit_overlap_details": hit,
        }

    report = {
        "experiment_id": manifest["experiment_id"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": manifest["source_commit"],
        "label_policy": manifest["label_policy"],
        "case_ids": case_ids,
        "human_case_count": len(human_cases),
        "human_evidence_items": sum(len(case.get("evidence") or []) for case in human_cases.values()),
        "metric_source": str((ANALYSIS_DIR / "compare_criteria1_agreement.py").resolve()),
        "systems": systems,
    }
    output_json = experiment_dir / "metrics.json"
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# March binary Judge × Dan-48 GPT-5 metrics",
        "",
        f"- Source commit: `{manifest['source_commit']}`",
        f"- Sample: all {len(case_ids)} completed Dan Criteria1 annotations",
        f"- Dan evidence denominator: {report['human_evidence_items']} items",
        "- Label policy: prompts forbid PARTIAL; any leaked/legacy PARTIAL is normalized to PASS.",
        "- Step alignment: strict one-to-one model step_index → raw steps[index].step_id → human step_id; same normalized field required.",
        "",
        "| System | Cases | Binary overall labels | Grounding | Hit rate | Overlap rate | PARTIAL labels |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for system_id, result in systems.items():
        def pct(value: Any) -> str:
            return "N/A" if value is None else f"{100 * float(value):.2f}%"

        if result["status"] == "complete":
            lines.append(
                f"| {system_id} | {result['completed_cases']}/{result['expected_cases']} | "
                f"{result['label_audit']['binary_overall_label_coverage']}/{result['expected_cases']} | "
                f"{pct(result['grounding_accuracy'])} "
                f"({result['grounding_numerator']}/{result['grounding_denominator']}) | "
                f"{pct(result['hit_rate'])} ({result['hit_numerator']}/{result['hit_denominator']}) | "
                f"{pct(result['overlap_rate'])} ({result['overlap_numerator']}/{result['overlap_denominator']}) | "
                f"{result['label_audit']['partial_label_occurrences']} |"
            )
        else:
            lines.append(
                f"| {system_id} | {result['completed_cases']}/{result['expected_cases']} | "
                f"{result['label_audit']['binary_overall_label_coverage']}/{result['expected_cases']} | "
                f"INCOMPLETE | INCOMPLETE | INCOMPLETE | "
                f"{result['label_audit']['partial_label_occurrences']} |"
            )
    non_binary_rows = [
        (system_id, item)
        for system_id, result in systems.items()
        for item in result["label_audit"]["non_binary_overall_cases"]
    ]
    if non_binary_rows:
        lines.extend(
            [
                "",
                "## Non-binary overall outputs",
                "",
                "The pilot Baseline prompt explicitly allows `unknown`; these outputs are retained rather than selectively rerun.",
                "",
            ]
        )
        for system_id, item in non_binary_rows:
            lines.append(f"- `{system_id}` / `{item['data_id']}`: `{item['label']}`")
    output_md = experiment_dir / "metrics.md"
    if any(item["status"] == "incomplete" for item in systems.values()):
        lines.extend(
            [
                "",
                "## Incomplete configurations",
                "",
                "At least one requested GPT-5 configuration is incomplete; final metrics are withheld for that configuration.",
            ]
        )
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"output_json": str(output_json), "output_md": str(output_md)}, indent=2))
    return 0 if all(
        item["label_audit"]["partial_label_occurrences"] == 0
        and item["label_audit"]["evaluated_file_count"] == len(case_ids)
        and item["label_audit"]["unique_data_id_count"] == len(case_ids)
        and not item["label_audit"]["missing_case_ids"]
        and not item["label_audit"]["extra_case_ids"]
        for item in systems.values()
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
