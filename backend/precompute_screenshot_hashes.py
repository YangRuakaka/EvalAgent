#!/usr/bin/env python3
"""Backfill missing screenshot hashes in cached history log JSON files."""
from __future__ import annotations

import argparse

from app.services.screenshot_hash_backfill import run_backfill


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Precompute and write missing details.screenshot_hashes into cached history log JSON files. "
            "By default this is a dry run; pass --write to persist changes."
        )
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write changes back to the JSON files. Without this flag, only a preview summary is shown.",
    )
    parser.add_argument(
        "--datasets",
        nargs="*",
        default=["data1", "data2", "data3"],
        help="Datasets to scan when --cache-dir is not provided. Supports data1/data2/data3 or 1/2/3.",
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default="",
        help="Optional custom directory containing history log JSON files. Overrides --datasets.",
    )
    parser.add_argument(
        "--overwrite-existing",
        action="store_true",
        help="Recompute hashes even when screenshot_hashes already exist.",
    )
    parser.add_argument(
        "--skip-legacy-data1",
        action="store_true",
        help="Skip legacy data1 directories such as history_logs_cache/ when scanning default locations.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-file details.",
    )
    return parser.parse_args()

def print_summary(result: dict) -> None:
    summary = result.get("summary", {})
    print("\n=== screenshot_hashes backfill summary ===")
    print(f"mode: {summary.get('mode', 'unknown').upper()}")
    print(f"files scanned: {summary.get('files_scanned', 0)}")
    print(f"files updated: {summary.get('files_updated', 0)}")
    print(f"files unchanged: {summary.get('files_unchanged', 0)}")
    print(f"files skipped: {summary.get('files_skipped', 0)}")
    print(f"write failures: {summary.get('write_failures', 0)}")
    print(f"screenshot entries scanned: {summary.get('screenshot_entries', 0)}")
    print(f"missing hashes generated: {summary.get('hashes_generated', 0)}")
    print(f"existing hashes recomputed: {summary.get('hashes_recomputed', 0)}")
    print(f"missing screenshot files: {summary.get('missing_screenshot_files', 0)}")


def main() -> int:
    args = parse_args()
    result = run_backfill(
        write_changes=args.write,
        datasets=args.datasets,
        cache_dir=args.cache_dir or None,
        overwrite_existing=args.overwrite_existing,
        skip_legacy_data1=args.skip_legacy_data1,
        verbose=args.verbose,
    )

    targets = result.get("targets", [])
    if not targets:
        print("No target directories found.")
        return 1

    for target in targets:
        print(f"\n[{target.get('label', 'unknown')}] {target.get('path', '')}")
        print(f"  json files: {target.get('json_files', 0)}")

    for file_report in result.get("files", []):
        status = file_report.get("status", "unknown")
        path = file_report.get("path", "")
        name = path.rsplit("/", 1)[-1]
        reason = file_report.get("reason")
        if status == "unchanged":
            print(f"  - unchanged {name}")
        elif status == "skipped":
            print(f"  - skip {name}: {reason}")
        elif status in {"would-update", "updated", "failed"}:
            suffix = (
                f"generated={file_report.get('generated_hashes', 0)}, "
                f"recomputed={file_report.get('recomputed_hashes', 0)}, "
                f"missing_files={file_report.get('missing_screenshot_files', 0)}"
            )
            if reason and status == "failed":
                suffix = f"{suffix}, reason={reason}"
            print(f"  - {status} {name}: {suffix}")

    print_summary(result)
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
