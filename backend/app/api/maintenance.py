import logging
import os
import shutil
import threading
import time
from pathlib import Path

from fastapi import APIRouter

from ..core.config import settings
from ..core.storage_paths import get_cache_dataset_dir

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
    summary="Cleanup extra files in cache_history_logs/data1",
)
async def cleanup_backend_files():
    backend_root = Path(__file__).resolve().parents[2]
    cache_data1_dir = get_cache_dataset_dir(settings, "data1")
    screenshots_dir = cache_data1_dir / "screenshots"

    deleted = []
    skipped = []
    failed = []

    def to_display_path(entry: Path) -> str:
        try:
            return entry.relative_to(backend_root).as_posix()
        except ValueError:
            return entry.as_posix()

    def safe_remove(entry: Path):
        relative_name = to_display_path(entry)
        try:
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry)
            else:
                entry.unlink(missing_ok=True)
            deleted.append(relative_name)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to delete %s: %s", relative_name, exc)
            failed.append({"path": relative_name, "error": str(exc)})

    def is_buy_milk_name(name: str) -> bool:
        return name.lower().startswith("buy_milk")

    if not cache_data1_dir.exists():
        return {
            "ok": True,
            "backend_root": backend_root.as_posix(),
            "scope": "cache_history_logs/data1",
            "message": "cache_history_logs/data1 directory does not exist.",
            "preserved": ["cache_history_logs/data1/screenshots/**", "cache_history_logs/data1/buy_milk*.json"],
            "deleted": deleted,
            "skipped": skipped,
            "failed": failed,
        }

    for entry in cache_data1_dir.iterdir():
        relative_name = to_display_path(entry)

        if entry.name == "screenshots":
            skipped.append(relative_name)
            continue

        if is_buy_milk_name(entry.name):
            skipped.append(relative_name)
            continue

        safe_remove(entry)

    if screenshots_dir.exists() and screenshots_dir.is_dir():
        for screenshot_entry in screenshots_dir.iterdir():
            relative_name = to_display_path(screenshot_entry)
            if is_buy_milk_name(screenshot_entry.name):
                skipped.append(relative_name)
                continue
            safe_remove(screenshot_entry)

    return {
        "ok": len(failed) == 0,
        "backend_root": backend_root.as_posix(),
        "scope": "cache_history_logs/data1",
        "preserved": ["cache_history_logs/data1/screenshots/buy_milk*/**", "cache_history_logs/data1/buy_milk*"],
        "deleted": deleted,
        "skipped": skipped,
        "failed": failed,
    }
