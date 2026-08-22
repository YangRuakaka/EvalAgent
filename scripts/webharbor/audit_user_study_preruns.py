"""Audit pre-run success, format, grounding markers, and persona divergence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from itertools import combinations
from pathlib import Path
from typing import Any

import browseruse_compat as legacy
from user_study_prerun_catalog import DATASETS, iter_runs


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "browser_agent_runs_userstudy_preruns_v1"


def _stable_id(run: dict[str, Any]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", run["case_id"].lower()).strip("_")
    return f"userstudy_{slug}_{run['run_index']:02d}_{run['persona']['persona_id']}"


def _expected_path(output_root: Path, run: dict[str, Any]) -> Path:
    return output_root / run["dataset"] / f"{_stable_id(run)}.json"


def _action_events(payload: dict[str, Any]) -> list[str]:
    """Canonicalize browser interactions while excluding persona-specific answer text."""

    events: list[str] = []
    for model_output in payload.get("details", {}).get("model_outputs", []):
        raw_actions = model_output.get("action") if isinstance(model_output, dict) else None
        actions = raw_actions if isinstance(raw_actions, list) else [raw_actions]
        for action in actions:
            if not isinstance(action, dict):
                continue
            for name, arguments in action.items():
                if name == "done":
                    events.append("done")
                    continue
                normalized = arguments
                if isinstance(arguments, dict):
                    normalized = {
                        key: value
                        for key, value in arguments.items()
                        if key not in {"text", "success", "files_to_display"}
                    }
                events.append(
                    f"{name}:"
                    + json.dumps(normalized, ensure_ascii=False, sort_keys=True)
                )
    return events


def _extract_final_field(text: str, label: str) -> str | None:
    match = re.search(
        rf"(?im)^\s*{re.escape(label)}\s*:\s*(.+?)\s*$", text
    )
    if match:
        return match.group(1).strip()
    next_line_match = re.search(
        rf"(?im)^\s*{re.escape(label)}\s*:\s*$\r?\n\s*(\S[^\r\n]*)\s*$",
        text,
    )
    return next_line_match.group(1).strip() if next_line_match else None


def _normalized_recommendation(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"[*_`#]", "", value).strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized or None


def _common_prefix_length(left: list[str], right: list[str]) -> int:
    count = 0
    for left_event, right_event in zip(left, right):
        if left_event != right_event:
            break
        count += 1
    return count


def _audit_run(path: Path, run: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "run_id": run["run_id"],
        "persona": run["persona"]["value"],
        "path": str(path),
        "passed": False,
        "checks": {},
        "errors": [],
    }
    if not path.is_file():
        result["errors"].append("expected output file is missing")
        return result

    try:
        legacy._validate_legacy_format(path, legacy.DEFAULT_REFERENCE_CASE.resolve())
        result["checks"]["legacy_format"] = True
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        result["checks"]["legacy_format"] = False
        result["errors"].append(f"format validation failed: {type(exc).__name__}: {exc}")
        return result

    metadata = payload["metadata"]
    summary = payload["summary"]
    final_result = summary.get("final_result")
    final_text = final_result if isinstance(final_result, str) else ""
    persona = metadata.get("persona")

    checks = {
        "task_exact": metadata.get("task", {}).get("description") == run["task"],
        "url_exact": metadata.get("task", {}).get("url") == run["url"],
        "persona_exact": isinstance(persona, dict)
        and persona.get("value") == run["persona"]["value"]
        and persona.get("content") == run["persona"]["content"],
        "run_index_exact": metadata.get("run_index") == run["run_index"],
        "is_done": summary.get("is_done") is True,
        "is_successful": summary.get("is_successful") is True,
        "no_errors": summary.get("has_errors") is False,
        "has_screenshots": bool(payload["details"].get("screenshots")),
        "has_model_outputs": bool(payload["details"].get("model_outputs")),
        "has_final_recommendation": bool(
            _extract_final_field(final_text, "FINAL RECOMMENDATION")
        ),
        "has_tradeoff_basis": bool(_extract_final_field(final_text, "TRADE-OFF BASIS")),
        "has_visible_evidence": bool(_extract_final_field(final_text, "VISIBLE EVIDENCE")),
        "has_comparison_table": "|" in final_text,
    }
    result["checks"].update(checks)
    result["recommendation"] = _extract_final_field(
        final_text, "FINAL RECOMMENDATION"
    )
    result["tradeoff_basis"] = _extract_final_field(final_text, "TRADE-OFF BASIS")
    result["visible_evidence"] = _extract_final_field(final_text, "VISIBLE EVIDENCE")
    result["trajectory"] = _action_events(payload)
    extract_count = sum(
        event.startswith("extract:") for event in result["trajectory"]
    )
    detail_text = json.dumps(payload.get("details", {}), ensure_ascii=False).lower()
    evidence_checks = {
        "at_least_four_extract_actions": extract_count >= 4,
        "no_404_navigation": re.search(r"(?<!\d)404(?!\d)", detail_text) is None,
    }
    result["checks"].update(evidence_checks)
    result["extract_count"] = extract_count
    result["trajectory_hash"] = hashlib.sha256(
        "\n".join(result["trajectory"]).encode("utf-8")
    ).hexdigest()[:16]
    result["steps"] = summary.get("number_of_steps")

    failed_checks = [
        name
        for name, passed in {**checks, **evidence_checks}.items()
        if not passed
    ]
    result["errors"].extend(f"failed check: {name}" for name in failed_checks)
    result["passed"] = not result["errors"]
    return result


def _audit_dataset(
    output_root: Path, dataset: dict[str, Any], runs: list[dict[str, Any]]
) -> dict[str, Any]:
    run_results = [
        _audit_run(_expected_path(output_root, run), run) for run in runs
    ]
    dataset_dir = output_root / dataset["dataset"]
    actual_jsons = sorted(dataset_dir.glob("*.json")) if dataset_dir.is_dir() else []

    task_values: set[str] = set()
    model_values: set[str] = set()
    for result in run_results:
        path = Path(result["path"])
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            task_values.add(payload["metadata"]["task"]["description"])
            model_values.add(payload["metadata"]["model"])
        except Exception:
            continue

    trajectories = {
        result["persona"]: result.get("trajectory", [])
        for result in run_results
        if result.get("trajectory")
    }
    identical_pairs: list[list[str]] = []
    pairwise_prefixes: list[dict[str, Any]] = []
    for (left_name, left), (right_name, right) in combinations(
        trajectories.items(), 2
    ):
        if left == right:
            identical_pairs.append([left_name, right_name])
        pairwise_prefixes.append(
            {
                "personas": [left_name, right_name],
                "shared_prefix_events": _common_prefix_length(left, right),
                "left_event_count": len(left),
                "right_event_count": len(right),
            }
        )

    recommendations = {
        result["persona"]: _normalized_recommendation(result.get("recommendation"))
        for result in run_results
        if _normalized_recommendation(result.get("recommendation"))
    }
    distinct_recommendations = len(set(recommendations.values()))
    checks = {
        "exactly_four_root_json_files": len(actual_jsons) == 4,
        "all_four_runs_pass": len(run_results) == 4
        and all(result["passed"] for result in run_results),
        "one_fixed_task": len(task_values) == 1 and task_values == {dataset["task"]},
        "one_fixed_model": len(model_values) == 1,
        "four_unique_personas": len({result["persona"] for result in run_results}) == 4,
        "four_unique_trajectories": len(trajectories) == 4 and not identical_pairs,
        "at_least_three_distinct_recommendations": distinct_recommendations >= 3,
    }
    return {
        "dataset": dataset["dataset"],
        "case_id": dataset["case_id"],
        "domain": dataset["domain"],
        "site": dataset["site"],
        "task": dataset["task"],
        "checks": checks,
        "passed": all(checks.values()),
        "actual_root_json_files": [str(path) for path in actual_jsons],
        "recommendations": recommendations,
        "distinct_recommendation_count": distinct_recommendations,
        "identical_trajectory_pairs": identical_pairs,
        "pairwise_shared_prefixes": pairwise_prefixes,
        "runs": run_results,
    }


def _markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# User-study pre-run audit",
        "",
        f"Overall: **{'PASS' if report['passed'] else 'FAIL'}**",
        "",
    ]
    for dataset in report["datasets"]:
        lines.extend(
            [
                f"## {dataset['dataset']} — {dataset['domain']}",
                "",
                f"Result: **{'PASS' if dataset['passed'] else 'FAIL'}**",
                "",
                "| Gate | Result |",
                "|---|---|",
            ]
        )
        for name, passed in dataset["checks"].items():
            lines.append(f"| {name} | {'PASS' if passed else 'FAIL'} |")
        lines.extend(
            [
                "",
                "| Persona | Run | Success | Steps | Recommendation | Trajectory |",
                "|---|---|---:|---:|---|---|",
            ]
        )
        for run in dataset["runs"]:
            recommendation = run.get("recommendation") or "—"
            lines.append(
                f"| {run['persona']} | {run['run_id']} | "
                f"{'PASS' if run['passed'] else 'FAIL'} | {run.get('steps', '—')} | "
                f"{recommendation.replace('|', '/')} | {run.get('trajectory_hash', '—')} |"
            )
        if dataset["identical_trajectory_pairs"]:
            lines.extend(
                [
                    "",
                    "Identical trajectories: "
                    + ", ".join(
                        " / ".join(pair)
                        for pair in dataset["identical_trajectory_pairs"]
                    ),
                ]
            )
        for run in dataset["runs"]:
            if run["errors"]:
                lines.append("")
                lines.append(f"- {run['run_id']}: " + "; ".join(run["errors"]))
        lines.append("")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--report-md", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output_root = args.output_root.resolve()
    all_runs = iter_runs()
    datasets = [
        _audit_dataset(
            output_root,
            dataset,
            [run for run in all_runs if run["dataset"] == dataset["dataset"]],
        )
        for dataset in DATASETS
    ]
    report = {
        "schema_version": 1,
        "output_root": str(output_root),
        "passed": all(dataset["passed"] for dataset in datasets),
        "datasets": datasets,
    }
    report_json = (args.report_json or output_root / "audit_report.json").resolve()
    report_md = (args.report_md or output_root / "audit_report.md").resolve()
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_md.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report_md.write_text(_markdown_report(report), encoding="utf-8")
    print(_markdown_report(report))
    print(f"JSON report: {report_json}")
    print(f"Markdown report: {report_md}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
