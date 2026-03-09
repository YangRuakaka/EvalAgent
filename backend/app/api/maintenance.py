import logging
import os
import stat
import shutil
import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..core.config import get_settings
from ..core.storage_paths import get_browser_run_output_dir, get_cache_history_root

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


def _terminate_process_after_delay(delay_seconds: float = 1.0) -> None:
    def _terminate() -> None:
        time.sleep(delay_seconds)
        os._exit(0)

    threading.Thread(target=_terminate, daemon=True).start()


@router.post(
    "/restart-service",
    summary="Restart backend service process",
)
async def restart_backend_service():
    _terminate_process_after_delay(1.0)
    return {
        "ok": True,
        "message": "Backend restart requested. The process will exit shortly.",
    }


@router.post(
    "/cleanup-files",
    summary="Cleanup browser-agent temporary files only",
)
async def cleanup_backend_files():
    settings = get_settings()
    backend_root = Path(__file__).resolve().parents[2]
    backend_root_resolved = backend_root.resolve(strict=False)

    browser_runs_dir = get_browser_run_output_dir(settings).resolve(strict=False)
    cache_history_root = get_cache_history_root(settings).resolve(strict=False)

    cleanup_root = browser_runs_dir
    scope = "browser_agent_runs_contents_only"
    preserved_top_level_dirs = {"screenshots"}
    screenshots_dir = cleanup_root / "screenshots"
    screenshots_marker = screenshots_dir / ".keep"

    protected_roots = {
        cache_history_root,
        (backend_root_resolved / "history_logs").resolve(strict=False),
    }

    def overlaps_with_protected(candidate: Path, protected: Path) -> bool:
        return (
            candidate == protected
            or candidate in protected.parents
        )

    overlapping_protected = [
        protected.as_posix()
        for protected in protected_roots
        if overlaps_with_protected(cleanup_root, protected)
    ]

    if overlapping_protected:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Cleanup blocked because cleanup target overlaps protected history_logs paths.",
                "backend_root": backend_root.as_posix(),
                "cleanup_root": cleanup_root.as_posix(),
                "scope": scope,
                "protected_paths": overlapping_protected,
            },
        )

    cleanup_root_resolved = cleanup_root.resolve(strict=False)

    deleted = []
    preserved = []
    skipped = []
    failed = []

    def is_reparse_point(entry: Path) -> bool:
        try:
            attrs = getattr(entry.lstat(), "st_file_attributes", 0)
            return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
        except OSError:
            return False

    def safe_remove(entry: Path):
        relative_name = entry.relative_to(cleanup_root).as_posix()
        entry_resolved = entry.resolve(strict=False)

        if (
            entry_resolved != cleanup_root_resolved
            and cleanup_root_resolved not in entry_resolved.parents
        ):
            skipped.append(relative_name)
            return

        if is_reparse_point(entry):
            skipped.append(relative_name)
            return

        try:
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry)
            else:
                entry.unlink(missing_ok=True)
            deleted.append(relative_name)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to delete %s: %s", relative_name, exc)
            failed.append({"path": relative_name, "error": str(exc)})

    if not cleanup_root.exists():
        cleanup_root.mkdir(parents=True, exist_ok=True)
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        screenshots_marker.write_text("", encoding="utf-8")
        return {
            "ok": True,
            "backend_root": backend_root.as_posix(),
            "cleanup_root": cleanup_root.as_posix(),
            "scope": scope,
            "message": "Cleanup target directory did not exist and has been recreated.",
            "preserved": preserved,
            "deleted": deleted,
            "skipped": skipped,
            "failed": failed,
        }

    for entry in cleanup_root.iterdir():
        if entry.is_dir() and entry.name in preserved_top_level_dirs:
            preserved.append(entry.relative_to(cleanup_root).as_posix())
            for nested_entry in entry.iterdir():
                safe_remove(nested_entry)
            continue
        safe_remove(entry)

    try:
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        screenshots_marker.write_text("", encoding="utf-8")
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Failed to ensure screenshots folder marker: %s", exc)
        failed.append({"path": screenshots_dir.relative_to(cleanup_root).as_posix(), "error": str(exc)})

    return {
        "ok": len(failed) == 0,
        "backend_root": backend_root.as_posix(),
        "cleanup_root": cleanup_root.as_posix(),
        "scope": scope,
        "preserved": preserved,
        "deleted": deleted,
        "skipped": skipped,
        "failed": failed,
    }
