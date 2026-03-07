import logging
import os
import stat
import shutil
import threading
import time
from pathlib import Path

from fastapi import APIRouter

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
    summary="Cleanup files in browser_agent_runs",
)
async def cleanup_backend_files():
    backend_root = Path(__file__).resolve().parents[2]
    browser_runs_dir = backend_root / "browser_agent_runs"
    browser_runs_root_resolved = browser_runs_dir.resolve(strict=False)

    deleted = []
    skipped = []
    failed = []

    def is_reparse_point(entry: Path) -> bool:
        try:
            attrs = getattr(entry.lstat(), "st_file_attributes", 0)
            return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
        except OSError:
            return False

    def safe_remove(entry: Path):
        relative_name = entry.relative_to(backend_root).as_posix()
        entry_resolved = entry.resolve(strict=False)

        if (
            entry_resolved != browser_runs_root_resolved
            and browser_runs_root_resolved not in entry_resolved.parents
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

    if not browser_runs_dir.exists():
        return {
            "ok": True,
            "backend_root": backend_root.as_posix(),
            "scope": "browser_agent_runs",
            "message": "browser_agent_runs directory does not exist.",
            "preserved": [],
            "deleted": deleted,
            "skipped": skipped,
            "failed": failed,
        }

    for entry in browser_runs_dir.iterdir():
        safe_remove(entry)

    return {
        "ok": len(failed) == 0,
        "backend_root": backend_root.as_posix(),
        "scope": "browser_agent_runs",
        "preserved": [],
        "deleted": deleted,
        "skipped": skipped,
        "failed": failed,
    }
