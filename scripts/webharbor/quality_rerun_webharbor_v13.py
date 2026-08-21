from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from audit_webharbor_v13_runs import _case_id, _write_json, audit_runs


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "browser_agent_runs_webharbor_v13_pilot"
DEFAULT_STATUS_PATH = DEFAULT_OUTPUT_DIR / "quality_rerun_supervisor_status.json"
RUNNER_PATH = Path(__file__).with_name("run_webharbor_v13_pilot.py")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _current_case_paths(output_dir: Path) -> dict[str, set[Path]]:
    paths: dict[str, set[Path]] = {}
    for path in output_dir.glob("webharbor_v13_*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            paths.setdefault(_case_id(payload), set()).add(path.resolve())
        except Exception:
            continue
    return paths


def _archive_superseded(
    output_dir: Path,
    rerun_ids: list[str],
    before: dict[str, set[Path]],
    archive_dir: Path,
) -> dict[str, Any]:
    after = _current_case_paths(output_dir)
    manifest: dict[str, Any] = {"archive_dir": str(archive_dir), "cases": []}
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / "screenshots").mkdir(parents=True, exist_ok=True)

    output_root = output_dir.resolve()
    screenshot_root = (output_dir / "screenshots").resolve()
    for case_id in rerun_ids:
        new_paths = after.get(case_id, set()) - before.get(case_id, set())
        if not new_paths:
            manifest["cases"].append(
                {"case_id": case_id, "state": "no_new_output", "archived": []}
            )
            continue

        newest = max(
            new_paths,
            key=lambda path: (
                json.loads(path.read_text(encoding="utf-8"))["metadata"].get(
                    "timestamp_utc", ""
                ),
                path.stat().st_mtime_ns,
            ),
        )
        archived: list[str] = []
        for old_path in sorted(after.get(case_id, set()) - {newest}):
            if old_path.parent.resolve() != output_root:
                raise RuntimeError(f"Refusing to archive unexpected path: {old_path}")
            payload = json.loads(old_path.read_text(encoding="utf-8"))
            run_id = str(payload["metadata"]["id"])
            target_json = archive_dir / old_path.name
            shutil.move(str(old_path), str(target_json))
            archived.append(str(target_json))

            screenshot_dir = (output_dir / "screenshots" / run_id).resolve()
            if screenshot_dir.is_dir():
                if screenshot_dir.parent.resolve() != screenshot_root:
                    raise RuntimeError(
                        f"Refusing to archive unexpected screenshot path: {screenshot_dir}"
                    )
                target_screenshots = archive_dir / "screenshots" / run_id
                shutil.move(str(screenshot_dir), str(target_screenshots))
                archived.append(str(target_screenshots))

        manifest["cases"].append(
            {
                "case_id": case_id,
                "state": "new_output_selected",
                "selected": str(newest),
                "archived": archived,
            }
        )
    return manifest


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit all 72 BrowserUse cases and rerun only rejected trajectories."
    )
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--max-steps", type=int, default=15)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", type=Path, default=DEFAULT_STATUS_PATH)
    parser.add_argument(
        "--case",
        action="append",
        dest="case_ids",
        help="Explicit case ID to rerun; may be supplied more than once.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output_dir = args.output_dir.resolve()
    status_path = args.status_path.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    batch_tag = started.strftime("%Y%m%d_%H%M%S")
    before_report_path = output_dir / "quality_audit_before_rerun.json"
    after_report_path = output_dir / "quality_audit_after_rerun.json"
    rerun_status_path = output_dir / "quality_rerun_batch_status.json"
    archive_dir = output_dir / "quality_archive" / batch_tag

    before_report = audit_runs(output_dir)
    _write_json(before_report_path, before_report)
    rerun_ids = (
        list(dict.fromkeys(args.case_ids))
        if args.case_ids
        else list(before_report["rerun_case_ids"])
    )
    before_paths = _current_case_paths(output_dir)
    status: dict[str, Any] = {
        "schema_version": 1,
        "pid": os.getpid(),
        "state": "running",
        "browseruse_only": True,
        "started_at_utc": started.isoformat(),
        "finished_at_utc": None,
        "initial_case_count": before_report["unique_case_count"],
        "rerun_count": len(rerun_ids),
        "rerun_case_ids": rerun_ids,
        "selection_rule": (
            "explicit case list" if args.case_ids else "quality audit rejection list"
        ),
        "before_audit": str(before_report_path),
        "after_audit": str(after_report_path),
        "rerun_batch_status": str(rerun_status_path),
        "archive_dir": str(archive_dir),
    }
    _write_json(status_path, status)

    if not rerun_ids:
        status.update(
            {
                "state": "completed_no_reruns",
                "finished_at_utc": _utc_now(),
                "remaining_rejected_count": 0,
            }
        )
        _write_json(status_path, status)
        print("QUALITY no reruns required", flush=True)
        return 0

    command = [
        sys.executable,
        "-u",
        str(RUNNER_PATH),
        "--full",
        "--no-resume",
        "--model",
        args.model,
        "--max-steps",
        str(args.max_steps),
        "--output-dir",
        str(output_dir),
        "--status-path",
        str(rerun_status_path),
    ]
    for case_id in rerun_ids:
        command.extend(["--case", case_id])

    print(
        f"QUALITY rerunning {len(rerun_ids)} cases: {','.join(rerun_ids)}", flush=True
    )
    completed = subprocess.run(command, cwd=REPO_ROOT, check=False)

    manifest = _archive_superseded(
        output_dir=output_dir,
        rerun_ids=rerun_ids,
        before=before_paths,
        archive_dir=archive_dir,
    )
    manifest_path = archive_dir / "manifest.json"
    _write_json(manifest_path, manifest)

    after_report = audit_runs(output_dir)
    _write_json(after_report_path, after_report)
    state = "completed" if completed.returncode == 0 else "completed_with_run_errors"
    status.update(
        {
            "state": state,
            "finished_at_utc": _utc_now(),
            "runner_return_code": completed.returncode,
            "remaining_rejected_count": after_report["rerun_count"],
            "remaining_rejected_case_ids": after_report["rerun_case_ids"],
            "archive_manifest": str(manifest_path),
        }
    )
    _write_json(status_path, status)
    print(
        f"QUALITY {state} rerun={len(rerun_ids)} "
        f"remaining_rejected={after_report['rerun_count']}",
        flush=True,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
