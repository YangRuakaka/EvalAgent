"""Utilities for backfilling missing screenshot hashes into cached history logs."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Optional

from ..core.config import get_settings
from ..core.storage_paths import (
    get_cache_dataset_dir,
    get_legacy_data1_dirs,
    normalize_cache_dataset,
    resolve_backend_path,
)
from .history_logs_reader import HistoryLogsService


@dataclass
class TargetDirectory:
    label: str
    path: Path


@dataclass
class FileProcessResult:
    changed: bool
    generated_hashes: int
    recomputed_hashes: int
    missing_screenshot_files: int
    screenshot_entries: int
    skipped: bool = False
    reason: Optional[str] = None


def build_target_directories(
    datasets: Optional[Iterable[str]] = None,
    cache_dir: Optional[str | Path] = None,
    skip_legacy_data1: bool = False,
) -> List[TargetDirectory]:
    settings = get_settings()
    backend_root = Path(__file__).resolve().parents[2]

    if cache_dir:
        custom_dir = resolve_backend_path(cache_dir, backend_root)
        return [TargetDirectory(label="custom", path=custom_dir)]

    raw_datasets = list(datasets) if datasets else ["data1", "data2", "data3"]
    targets: List[TargetDirectory] = []
    seen: set[Path] = set()

    for raw_dataset in raw_datasets:
        dataset_key = normalize_cache_dataset(raw_dataset)
        dataset_dir = get_cache_dataset_dir(settings, dataset_key)
        if dataset_dir not in seen:
            targets.append(TargetDirectory(label=dataset_key, path=dataset_dir))
            seen.add(dataset_dir)

        if dataset_key != "data1" or skip_legacy_data1:
            continue

        for legacy_dir in get_legacy_data1_dirs(settings):
            resolved_legacy = resolve_backend_path(legacy_dir, backend_root)
            if resolved_legacy in seen:
                continue
            targets.append(TargetDirectory(label="data1-legacy", path=resolved_legacy))
            seen.add(resolved_legacy)

    return targets


def iter_json_files(directory: Path) -> List[Path]:
    if not directory.exists() or not directory.is_dir():
        return []
    return sorted(directory.glob("*.json"))


def _normalize_existing_hashes(
    service: HistoryLogsService,
    details: dict[str, Any],
    screenshot_paths: List[str],
) -> List[Optional[str]]:
    return service._normalize_screenshot_hashes(details.get("screenshot_hashes"), len(screenshot_paths))


def _compute_next_hashes(
    service: HistoryLogsService,
    json_path: Path,
    screenshot_paths: List[str],
    existing_hashes: List[Optional[str]],
    overwrite_existing: bool,
) -> tuple[List[Optional[str]], int, int, int]:
    next_hashes = list(existing_hashes)
    generated_hashes = 0
    recomputed_hashes = 0
    missing_screenshot_files = 0

    if len(next_hashes) < len(screenshot_paths):
        next_hashes.extend([None] * (len(screenshot_paths) - len(next_hashes)))

    for index, path_str in enumerate(screenshot_paths):
        has_existing_hash = index < len(existing_hashes) and existing_hashes[index] is not None
        if has_existing_hash and not overwrite_existing:
            continue

        resolved_path = service._resolve_screenshot_path(path_str, json_path=json_path)
        computed_hash = service._compute_cached_screenshot_hash(resolved_path)

        if computed_hash is None:
            if resolved_path is None or not resolved_path.exists() or not resolved_path.is_file():
                missing_screenshot_files += 1
            continue

        previous_hash = next_hashes[index]
        normalized_hash = service._normalize_screenshot_hash_value(computed_hash)
        next_hashes[index] = normalized_hash

        if previous_hash is None:
            generated_hashes += 1
        elif previous_hash != normalized_hash:
            recomputed_hashes += 1

    return next_hashes, generated_hashes, recomputed_hashes, missing_screenshot_files


def _hashes_field_needs_update(
    details: dict[str, Any],
    next_hashes: List[Optional[str]],
    existing_hashes: List[Optional[str]],
) -> bool:
    original_value = details.get("screenshot_hashes")
    if not isinstance(original_value, list):
        return any(hash_value is not None for hash_value in next_hashes)
    return original_value != next_hashes or existing_hashes != next_hashes


def process_json_file(
    service: HistoryLogsService,
    json_path: Path,
    overwrite_existing: bool,
) -> tuple[dict[str, Any], FileProcessResult]:
    try:
        raw_payload = service._read_json(json_path)
    except Exception as exc:
        return {}, FileProcessResult(
            changed=False,
            generated_hashes=0,
            recomputed_hashes=0,
            missing_screenshot_files=0,
            screenshot_entries=0,
            skipped=True,
            reason=f"failed to read JSON: {exc}",
        )

    if not isinstance(raw_payload, dict):
        return raw_payload, FileProcessResult(
            changed=False,
            generated_hashes=0,
            recomputed_hashes=0,
            missing_screenshot_files=0,
            screenshot_entries=0,
            skipped=True,
            reason="payload is not a JSON object",
        )

    details = raw_payload.get("details")
    if details is None:
        details = {}
        raw_payload["details"] = details

    if not isinstance(details, dict):
        return raw_payload, FileProcessResult(
            changed=False,
            generated_hashes=0,
            recomputed_hashes=0,
            missing_screenshot_files=0,
            screenshot_entries=0,
            skipped=True,
            reason="details is not a JSON object",
        )

    screenshot_paths = [str(item) for item in service._ensure_iterable(details.get("screenshots"))]
    existing_hashes = _normalize_existing_hashes(service, details, screenshot_paths)
    next_hashes, generated_hashes, recomputed_hashes, missing_screenshot_files = _compute_next_hashes(
        service,
        json_path,
        screenshot_paths,
        existing_hashes,
        overwrite_existing,
    )

    changed = _hashes_field_needs_update(details, next_hashes, existing_hashes)
    if changed:
        details["screenshot_hashes"] = next_hashes

    return raw_payload, FileProcessResult(
        changed=changed,
        generated_hashes=generated_hashes,
        recomputed_hashes=recomputed_hashes,
        missing_screenshot_files=missing_screenshot_files,
        screenshot_entries=len(screenshot_paths),
    )


def write_json_file(json_path: Path, payload: dict[str, Any]) -> None:
    temp_path = json_path.with_suffix(f"{json_path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(json_path)


def run_backfill(
    *,
    write_changes: bool = False,
    datasets: Optional[Iterable[str]] = None,
    cache_dir: Optional[str | Path] = None,
    overwrite_existing: bool = False,
    skip_legacy_data1: bool = False,
    verbose: bool = False,
) -> dict[str, Any]:
    targets = build_target_directories(
        datasets=datasets,
        cache_dir=cache_dir,
        skip_legacy_data1=skip_legacy_data1,
    )

    service = HistoryLogsService(
        cache_dir=resolve_backend_path(cache_dir, Path(__file__).resolve().parents[2]) if cache_dir else None,
    )

    summary = {
        "mode": "write" if write_changes else "dry-run",
        "files_scanned": 0,
        "files_updated": 0,
        "files_unchanged": 0,
        "files_skipped": 0,
        "write_failures": 0,
        "screenshot_entries": 0,
        "hashes_generated": 0,
        "hashes_recomputed": 0,
        "missing_screenshot_files": 0,
    }
    file_reports: list[dict[str, Any]] = []
    target_reports: list[dict[str, Any]] = []

    for target in targets:
        json_files = iter_json_files(target.path)
        target_reports.append(
            {
                "label": target.label,
                "path": str(target.path),
                "json_files": len(json_files),
            }
        )

        for json_path in json_files:
            summary["files_scanned"] += 1
            payload, result = process_json_file(
                service=service,
                json_path=json_path,
                overwrite_existing=overwrite_existing,
            )
            summary["screenshot_entries"] += result.screenshot_entries
            summary["hashes_generated"] += result.generated_hashes
            summary["hashes_recomputed"] += result.recomputed_hashes
            summary["missing_screenshot_files"] += result.missing_screenshot_files

            report = {
                "path": str(json_path),
                "generated_hashes": result.generated_hashes,
                "recomputed_hashes": result.recomputed_hashes,
                "missing_screenshot_files": result.missing_screenshot_files,
                "screenshot_entries": result.screenshot_entries,
            }

            if result.skipped:
                summary["files_skipped"] += 1
                report["status"] = "skipped"
                report["reason"] = result.reason
                if verbose:
                    file_reports.append(report)
                continue

            if not result.changed:
                summary["files_unchanged"] += 1
                report["status"] = "unchanged"
                if verbose:
                    file_reports.append(report)
                continue

            if not write_changes:
                summary["files_updated"] += 1
                report["status"] = "would-update"
                file_reports.append(report)
                continue

            try:
                write_json_file(json_path, payload)
                summary["files_updated"] += 1
                report["status"] = "updated"
            except Exception as exc:
                summary["write_failures"] += 1
                report["status"] = "failed"
                report["reason"] = str(exc)
            file_reports.append(report)

    return {
        "ok": summary["write_failures"] == 0,
        "targets": target_reports,
        "summary": summary,
        "files": file_reports if verbose or write_changes else [],
    }
