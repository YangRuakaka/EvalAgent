import logging
import shutil
from pathlib import Path

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.post(
    "/cleanup-files",
    summary="Cleanup extra files in history_logs",
)
async def cleanup_backend_files():
    backend_root = Path(__file__).resolve().parents[2]
    history_logs_dir = backend_root / "history_logs"
    screenshots_dir = history_logs_dir / "screenshots"

    deleted = []
    skipped = []
    failed = []

    def safe_remove(entry: Path):
        relative_name = entry.relative_to(backend_root).as_posix()
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

    if not history_logs_dir.exists():
        return {
            "ok": True,
            "backend_root": backend_root.as_posix(),
            "scope": "history_logs",
            "message": "history_logs directory does not exist.",
            "preserved": ["history_logs/screenshots/**", "history_logs/buy_milk*.json"],
            "deleted": deleted,
            "skipped": skipped,
            "failed": failed,
        }

    for entry in history_logs_dir.iterdir():
        relative_name = entry.relative_to(backend_root).as_posix()

        if entry.name == "screenshots":
            skipped.append(relative_name)
            continue

        if is_buy_milk_name(entry.name):
            skipped.append(relative_name)
            continue

        safe_remove(entry)

    if screenshots_dir.exists() and screenshots_dir.is_dir():
        for screenshot_entry in screenshots_dir.iterdir():
            relative_name = screenshot_entry.relative_to(backend_root).as_posix()
            if is_buy_milk_name(screenshot_entry.name):
                skipped.append(relative_name)
                continue
            safe_remove(screenshot_entry)

    return {
        "ok": len(failed) == 0,
        "backend_root": backend_root.as_posix(),
        "scope": "history_logs",
        "preserved": ["history_logs/screenshots/buy_milk*/**", "history_logs/buy_milk*"],
        "deleted": deleted,
        "skipped": skipped,
        "failed": failed,
    }
