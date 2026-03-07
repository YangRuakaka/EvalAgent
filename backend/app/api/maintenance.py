import logging
import os
import stat
import shutil
import threading
import time
from pathlib import Path

from fastapi import APIRouter

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
    summary="Cleanup server files while preserving history_logs",
)
async def cleanup_backend_files():
    settings = get_settings()
    backend_root = Path(__file__).resolve().parents[2]
    backend_root_resolved = backend_root.resolve(strict=False)

    browser_runs_dir = get_browser_run_output_dir(settings).resolve(strict=False)
    cache_history_root = get_cache_history_root(settings).resolve(strict=False)

    use_shared_storage_cleanup = (
        browser_runs_dir.is_absolute()
        and cache_history_root.is_absolute()
        and browser_runs_dir.parent == cache_history_root.parent
        and browser_runs_dir.parent != backend_root_resolved
    )

    if use_shared_storage_cleanup:
        cleanup_root = browser_runs_dir.parent
        preserved_roots = [cache_history_root]
        scope = "storage_root_except_history_logs"
    else:
        cleanup_root = browser_runs_dir
        preserved_roots = []
        scope = "browser_agent_runs"

    cleanup_root_resolved = cleanup_root.resolve(strict=False)
    preserved_roots_resolved = [path.resolve(strict=False) for path in preserved_roots]

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

        for preserve_root in preserved_roots_resolved:
            if entry_resolved == preserve_root or entry_resolved in preserve_root.parents:
                preserved.append(relative_name)
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
        return {
            "ok": True,
            "backend_root": backend_root.as_posix(),
            "cleanup_root": cleanup_root.as_posix(),
            "scope": scope,
            "message": "Cleanup target directory does not exist.",
            "preserved": preserved,
            "deleted": deleted,
            "skipped": skipped,
            "failed": failed,
        }

    for entry in cleanup_root.iterdir():
        safe_remove(entry)

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
