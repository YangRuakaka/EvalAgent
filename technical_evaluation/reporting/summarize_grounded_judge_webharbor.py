from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


DOMAIN_NAMES = {
    "RET": "Retail",
    "HOT": "Hotels",
    "FLT": "Flights",
    "SPT": "Sports",
    "REC": "Recipes",
    "EDU": "Education",
    "MLM": "ML models",
    "INF": "Information",
}


def _rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def _summarize(cases: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(cases)
    labels = Counter(str(case.get("judge", {}).get("verdict", "UNKNOWN")).upper() for case in rows)
    confidences = [
        float(case.get("judge", {}).get("confidence", 0.0) or 0.0) for case in rows
    ]
    evidence_counts = [
        len(case.get("judge", {}).get("evidence", []) or []) for case in rows
    ]
    total = len(rows)
    return {
        "total": total,
        "labels": dict(sorted(labels.items())),
        "pass_rate": _rate(labels["PASS"], total),
        "fail_rate": _rate(labels["FAIL"], total),
        "unknown_rate": _rate(labels["UNKNOWN"] + labels["UNABLE_TO_EVALUATE"], total),
        "mean_confidence": round(statistics.fmean(confidences), 4) if confidences else 0.0,
        "median_confidence": round(statistics.median(confidences), 4) if confidences else 0.0,
        "mean_evidence_count": round(statistics.fmean(evidence_counts), 2)
        if evidence_counts
        else 0.0,
        "median_evidence_count": round(statistics.median(evidence_counts), 2)
        if evidence_counts
        else 0.0,
        "cases_without_evidence": sum(count == 0 for count in evidence_counts),
    }


def _group(
    cases: list[dict[str, Any]], key_fn: Any
) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        buckets[str(key_fn(case))].append(case)
    return {key: _summarize(buckets[key]) for key in sorted(buckets)}


def _case_id(case: dict[str, Any]) -> str:
    return str(case.get("case_id", ""))


def _base_task(case: dict[str, Any]) -> str:
    case_id = _case_id(case)
    return case_id.rsplit("-", 1)[0] if "-" in case_id else case_id


def _condition(case: dict[str, Any]) -> str:
    return _case_id(case).rsplit("-", 1)[-1]


def _domain(case: dict[str, Any]) -> str:
    prefix = _case_id(case).split("-", 1)[0]
    return f"{prefix} · {DOMAIN_NAMES.get(prefix, prefix)}"


def _write_case_csv(path: Path, cases: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "case_id",
                "base_task",
                "condition",
                "domain",
                "persona_value",
                "criterion",
                "verdict",
                "confidence",
                "evidence_count",
                "relevant_steps",
                "agent_success",
                "agent_steps",
            ],
        )
        writer.writeheader()
        for case in cases:
            judge = case.get("judge", {})
            agent = case.get("agent", {})
            summary = agent.get("summary", {}) or {}
            writer.writerow(
                {
                    "case_id": _case_id(case),
                    "base_task": _base_task(case),
                    "condition": _condition(case),
                    "domain": _domain(case),
                    "persona_value": agent.get("persona_value", ""),
                    "criterion": case.get("criterion", {}).get("title", ""),
                    "verdict": str(judge.get("verdict", "UNKNOWN")).upper(),
                    "confidence": judge.get("confidence", 0.0),
                    "evidence_count": len(judge.get("evidence", []) or []),
                    "relevant_steps": "|".join(
                        str(value) for value in (judge.get("relevant_steps", []) or [])
                    ),
                    "agent_success": summary.get("is_successful", ""),
                    "agent_steps": len(case.get("steps", []) or []),
                }
            )


def _triad_patterns(cases: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        grouped[_base_task(case)].append(case)

    pattern_counts: Counter[str] = Counter()
    tasks: dict[str, dict[str, Any]] = {}
    for base, members in sorted(grouped.items()):
        labels = {
            _condition(case): str(case.get("judge", {}).get("verdict", "UNKNOWN")).upper()
            for case in members
        }
        pass_count = sum(label == "PASS" for label in labels.values())
        fail_count = sum(label == "FAIL" for label in labels.values())
        unknown_count = len(labels) - pass_count - fail_count
        if unknown_count:
            pattern = "contains_unknown"
        elif pass_count == 3:
            pattern = "all_pass"
        elif fail_count == 3:
            pattern = "all_fail"
        elif pass_count == 2:
            pattern = "two_pass_one_fail"
        elif pass_count == 1:
            pattern = "one_pass_two_fail"
        else:
            pattern = "incomplete"
        pattern_counts[pattern] += 1
        tasks[base] = {"labels": dict(sorted(labels.items())), "pattern": pattern}
    return {
        "task_count": len(grouped),
        "pattern_counts": dict(sorted(pattern_counts.items())),
        "tasks": tasks,
    }


def _markdown_table(groups: dict[str, dict[str, Any]]) -> list[str]:
    lines = [
        "| Group | N | PASS | FAIL | UNKNOWN | Pass rate | Mean confidence | Mean evidence |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, stats in groups.items():
        labels = stats["labels"]
        lines.append(
            "| {name} | {n} | {passed} | {failed} | {unknown} | {rate:.1%} | "
            "{confidence:.3f} | {evidence:.2f} |".format(
                name=name,
                n=stats["total"],
                passed=labels.get("PASS", 0),
                failed=labels.get("FAIL", 0),
                unknown=labels.get("UNKNOWN", 0)
                + labels.get("UNABLE_TO_EVALUATE", 0),
                rate=stats["pass_rate"],
                confidence=stats["mean_confidence"],
                evidence=stats["mean_evidence_count"],
            )
        )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize the 72-case grounded WebHarbor judge results."
    )
    parser.add_argument("results_dir", type=Path)
    args = parser.parse_args()
    results_dir = args.results_dir.resolve()
    payload = json.loads(
        (results_dir / "visualization_data.json").read_text(encoding="utf-8")
    )
    cases = sorted(payload.get("cases", []), key=_case_id)

    stats = {
        "judge_model": payload.get("judge_model"),
        "judge_version": payload.get("judge_version"),
        "selection_rule": payload.get("selection_rule"),
        "overall": _summarize(cases),
        "by_condition": _group(cases, _condition),
        "by_domain": _group(cases, _domain),
        "by_base_task": _group(cases, _base_task),
        "by_persona_value": _group(
            cases, lambda case: case.get("agent", {}).get("persona_value", "unknown")
        ),
        "triad_patterns": _triad_patterns(cases),
        "case_ids": [_case_id(case) for case in cases],
    }
    (results_dir / "label_statistics.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_case_csv(results_dir / "case_labels.csv", cases)

    overall = stats["overall"]
    labels = overall["labels"]
    report = [
        "# WebHarbor v1.3 grounded-judge label statistics",
        "",
        f"- Cases: {overall['total']}",
        f"- PASS: {labels.get('PASS', 0)} ({overall['pass_rate']:.1%})",
        f"- FAIL: {labels.get('FAIL', 0)} ({overall['fail_rate']:.1%})",
        (
            "- UNKNOWN / technical failure: "
            f"{labels.get('UNKNOWN', 0) + labels.get('UNABLE_TO_EVALUATE', 0)}"
        ),
        f"- Mean confidence: {overall['mean_confidence']:.3f}",
        f"- Mean evidence spans per case: {overall['mean_evidence_count']:.2f}",
        f"- Cases without evidence: {overall['cases_without_evidence']}",
        "",
        "## By condition",
        "",
        *_markdown_table(stats["by_condition"]),
        "",
        "## By domain",
        "",
        *_markdown_table(stats["by_domain"]),
        "",
        "## By task",
        "",
        *_markdown_table(stats["by_base_task"]),
        "",
        "## A/B/C label patterns",
        "",
        *[
            f"- {name}: {count}"
            for name, count in stats["triad_patterns"]["pattern_counts"].items()
        ],
        "",
        (
            "> These are judge predictions only. Human–judge agreement metrics require "
            "an independently collected human-label file."
        ),
        "",
    ]
    (results_dir / "label_statistics.md").write_text(
        "\n".join(report), encoding="utf-8"
    )
    print(json.dumps(stats["overall"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
