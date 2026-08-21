from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = (
    ROOT / "technical_evaluation" / "results" / "initial_agentic_judge_yukun_48"
)
RUNNER = ROOT / "technical_evaluation" / "pipelines" / "run_initial_agentic_judge_yukun.py"
RENDERER = ROOT / "technical_evaluation" / "reporting" / "render_grounded_judge_html.py"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def wait_for_batch(status_path: Path, timeout_seconds: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if status_path.is_file():
            try:
                status = read_json(status_path)
            except (OSError, json.JSONDecodeError):
                time.sleep(2)
                continue
            if status.get("state") != "running":
                return status
        time.sleep(10)
    raise TimeoutError(f"Timed out waiting for {status_path}")


def audit(output_dir: Path, expected_count: int) -> tuple[dict[str, Any], list[str]]:
    response = read_json(output_dir / "experiment_evaluation.json")
    visualization = read_json(output_dir / "visualization_data.json")
    conditions = response.get("conditions", [])
    cases = visualization.get("cases", [])
    errors: list[str] = []

    condition_ids = [str(item.get("conditionID")) for item in conditions]
    case_ids = [str(item.get("case_id")) for item in cases]
    if len(condition_ids) != expected_count:
        errors.append(f"condition count {len(condition_ids)} != {expected_count}")
    if len(set(condition_ids)) != len(condition_ids):
        errors.append("duplicate condition IDs")
    if set(condition_ids) != set(case_ids):
        errors.append("condition IDs and visualization case IDs differ")

    labels: Counter[str] = Counter()
    invalid_cases: list[str] = []
    for item in cases:
        case_id = str(item.get("case_id"))
        judge = item.get("judge") or {}
        verdict = str(judge.get("verdict") or "").upper()
        confidence = float(judge.get("confidence") or 0.0)
        labels[verdict] += 1
        if verdict not in {"PASS", "PARTIAL", "FAIL"} or confidence <= 0:
            invalid_cases.append(case_id)
    if invalid_cases:
        errors.append("invalid judge results: " + ", ".join(invalid_cases))

    report = {
        "generated_at_utc": utc_now(),
        "pipeline": "initial agentic judge",
        "source_commit": "19fc0a2",
        "expected_cases": expected_count,
        "condition_count": len(condition_ids),
        "visualization_case_count": len(case_ids),
        "unique_case_count": len(set(condition_ids)),
        "label_counts": {
            "PASS": labels["PASS"],
            "PARTIAL": labels["PARTIAL"],
            "FAIL": labels["FAIL"],
        },
        "valid": not errors,
        "errors": errors,
    }
    return report, errors


def write_outputs(output_dir: Path, report: dict[str, Any]) -> None:
    (output_dir / "verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    labels = report["label_counts"]
    (output_dir / "label_statistics.md").write_text(
        "\n".join(
            [
                "# Initial agentic judge · Yukun 48",
                "",
                f"- PASS: {labels['PASS']}",
                f"- PARTIAL: {labels['PARTIAL']}",
                f"- FAIL: {labels['FAIL']}",
                f"- Total: {report['condition_count']}",
                f"- Validation: {'passed' if report['valid'] else 'failed'}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    visualization = read_json(output_dir / "visualization_data.json")
    with (output_dir / "case_labels.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["case_id", "verdict", "confidence", "persona_value"])
        for case in visualization.get("cases", []):
            judge = case.get("judge") or {}
            writer.writerow(
                [
                    case.get("case_id"),
                    str(judge.get("verdict") or "").upper(),
                    judge.get("confidence"),
                    (case.get("agent") or {}).get("persona_value"),
                ]
            )


def run_retry(output_dir: Path, attempts: int, delay: float) -> int:
    stdout_path = output_dir / "finalizer_retry_stdout.log"
    stderr_path = output_dir / "finalizer_retry_stderr.log"
    command = [
        sys.executable,
        str(RUNNER),
        "--output-dir",
        str(output_dir),
        "--resume",
        "--max-attempts",
        str(attempts),
        "--retry-delay",
        str(delay),
    ]
    with stdout_path.open("a", encoding="utf-8") as stdout, stderr_path.open(
        "a", encoding="utf-8"
    ) as stderr:
        return subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr).returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Wait for, validate, summarize, and render the initial Yukun judge run."
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--expected-count", type=int, default=48)
    parser.add_argument("--wait-timeout", type=int, default=4 * 60 * 60)
    parser.add_argument("--retry-batches", type=int, default=2)
    parser.add_argument("--case-attempts", type=int, default=3)
    parser.add_argument("--retry-delay", type=float, default=8.0)
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    status_path = output_dir / "run_status.json"
    finalizer_status_path = output_dir / "finalizer_status.json"
    finalizer_status_path.write_text(
        json.dumps({"state": "waiting", "started_at_utc": utc_now()}, indent=2),
        encoding="utf-8",
    )

    status = wait_for_batch(status_path, args.wait_timeout)
    retry_number = 0
    while (
        status.get("state") != "completed"
        or int(status.get("completed") or 0) != args.expected_count
        or int(status.get("failed") or 0) != 0
    ) and retry_number < args.retry_batches:
        retry_number += 1
        finalizer_status_path.write_text(
            json.dumps(
                {
                    "state": "retrying",
                    "retry_batch": retry_number,
                    "previous_status": status,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        run_retry(output_dir, args.case_attempts, args.retry_delay)
        status = read_json(status_path)

    report, errors = audit(output_dir, args.expected_count)
    write_outputs(output_dir, report)
    if not errors:
        subprocess.run(
            [
                sys.executable,
                str(RENDERER),
                "--results-dir",
                str(output_dir),
            ],
            cwd=ROOT,
            check=True,
        )

    finalizer_status_path.write_text(
        json.dumps(
            {
                "state": "completed" if not errors else "failed",
                "finished_at_utc": utc_now(),
                "retry_batches_used": retry_number,
                "verification": report,
                "index": str(output_dir / "index.html") if not errors else None,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
