from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "browser_agent_runs_webharbor_v13_pilot"
DEFAULT_REPORT_PATH = DEFAULT_OUTPUT_DIR / "quality_audit.json"

SELF_REPORTED_FAILURE_PATTERNS = {
    "partial_failure": re.compile(r"\bpartial failure\b", re.IGNORECASE),
    "wrong_course": re.compile(r"\bwrong course\b", re.IGNORECASE),
    "wrong_date": re.compile(r"\bwrong date\b", re.IGNORECASE),
    "wrong_page": re.compile(r"\bwrong page\b", re.IGNORECASE),
    "navigation_loop": re.compile(
        r"\b(?:stuck in a loop|looping between|stuck in the navigation loop)\b",
        re.IGNORECASE,
    ),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _case_id(payload: dict[str, Any]) -> str:
    return str(payload["metadata"]["task"]["name"]).split(" | ", 1)[0]


def _action_signature(model_output: dict[str, Any]) -> str:
    actions = model_output.get("action") or []
    return json.dumps(actions, ensure_ascii=False, sort_keys=True)


def _latest_runs(output_dir: Path) -> tuple[dict[str, tuple[Path, dict[str, Any]]], int]:
    candidates: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    total = 0
    for path in output_dir.glob("webharbor_v13_*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            case_id = _case_id(payload)
            candidates.setdefault(case_id, []).append((path, payload))
            total += 1
        except Exception:
            continue

    latest: dict[str, tuple[Path, dict[str, Any]]] = {}
    for case_id, runs in candidates.items():
        latest[case_id] = max(
            runs,
            key=lambda item: (
                str(item[1].get("metadata", {}).get("timestamp_utc", "")),
                item[0].stat().st_mtime_ns,
            ),
        )
    return latest, total


def audit_runs(output_dir: Path) -> dict[str, Any]:
    latest, artifact_count = _latest_runs(output_dir)
    reports: list[dict[str, Any]] = []

    for case_id, (path, payload) in sorted(latest.items()):
        summary = payload["summary"]
        model_outputs = payload.get("details", {}).get("model_outputs") or []
        reasons: list[str] = []
        observations: list[dict[str, Any]] = []

        if not bool(summary.get("is_done")):
            reasons.append("terminal_not_done")
        if not bool(summary.get("is_successful")):
            reasons.append("terminal_unsuccessful")
        if bool(summary.get("has_errors")):
            reasons.append("browseruse_process_error")

        wait_count = 0
        action_signatures: list[str] = []
        for step_index, model_output in enumerate(model_outputs, start=1):
            signature = _action_signature(model_output)
            action_signatures.append(signature)
            for action in model_output.get("action") or []:
                if "wait" in action:
                    wait_count += 1

            trace_text = " ".join(
                str(model_output.get(field) or "")
                for field in (
                    "thinking",
                    "evaluation_previous_goal",
                    "memory",
                    "next_goal",
                )
            )
            for label, pattern in SELF_REPORTED_FAILURE_PATTERNS.items():
                match = pattern.search(trace_text)
                if match:
                    observations.append(
                        {
                            "type": label,
                            "step": step_index,
                            "excerpt": re.sub(r"\s+", " ", trace_text)[
                                max(0, match.start() - 80) : match.end() + 120
                            ],
                        }
                    )

        observation_types = {item["type"] for item in observations}
        if observation_types:
            reasons.extend(f"trace_{label}" for label in sorted(observation_types))
        if wait_count >= 4:
            reasons.append("redundant_wait_loop")

        repeated_action_count = 0
        for index in range(2, len(action_signatures)):
            if (
                action_signatures[index]
                and action_signatures[index] == action_signatures[index - 1]
                and action_signatures[index] == action_signatures[index - 2]
            ):
                repeated_action_count += 1
        if repeated_action_count:
            reasons.append("repeated_identical_action")

        reasons = list(dict.fromkeys(reasons))
        steps = int(summary.get("number_of_steps") or len(model_outputs))
        long_but_retained = steps >= 13 and not reasons
        reports.append(
            {
                "case_id": case_id,
                "decision": "rerun" if reasons else "retain",
                "reasons": reasons,
                "long_comparison_retained": long_but_retained,
                "source": str(path),
                "summary": {
                    "is_done": summary.get("is_done"),
                    "is_successful": summary.get("is_successful"),
                    "has_errors": summary.get("has_errors"),
                    "number_of_steps": steps,
                    "duration_seconds": summary.get("total_duration_seconds"),
                },
                "diagnostics": {
                    "wait_count": wait_count,
                    "self_reported_failures": observations,
                },
            }
        )

    rerun_ids = [report["case_id"] for report in reports if report["decision"] == "rerun"]
    retained_long = [
        report["case_id"] for report in reports if report["long_comparison_retained"]
    ]
    reason_counts = Counter(
        reason for report in reports for reason in report.get("reasons", [])
    )
    return {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "output_dir": str(output_dir),
        "policy": {
            "rerun": [
                "terminal task is not done or not successful",
                "BrowserUse reports a process error",
                "trace explicitly reports a wrong course/date/page, partial failure, or navigation loop",
                "four or more wait actions or three identical consecutive actions",
            ],
            "retain": (
                "A long trajectory is retained when the extra steps are attributable to "
                "the requested comparison and none of the rerun conditions is present."
            ),
        },
        "artifact_count": artifact_count,
        "unique_case_count": len(reports),
        "rerun_count": len(rerun_ids),
        "retain_count": len(reports) - len(rerun_ids),
        "rerun_case_ids": rerun_ids,
        "long_comparison_retained_case_ids": retained_long,
        "reason_counts": dict(sorted(reason_counts.items())),
        "cases": reports,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit BrowserUse v1.3 trajectories.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = audit_runs(args.output_dir.resolve())
    _write_json(args.report.resolve(), report)
    print(
        f"AUDIT cases={report['unique_case_count']} rerun={report['rerun_count']} "
        f"retain={report['retain_count']} report={args.report.resolve()}",
        flush=True,
    )
    print("RERUN " + ",".join(report["rerun_case_ids"]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

