"""Utilities for loading cached history logs and preparing them for API responses."""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Iterable, List, Optional

from ..schemas.history_logs import HistoryLogDetails, HistoryLogPayload


class HistoryLogsServiceError(RuntimeError):
    """Raised when cached history logs cannot be processed."""


class HistoryLogsService:
    """Provides read access to cached history logs on disk."""

    def __init__(self, cache_dir: Optional[Path | str] = None) -> None:
        base_dir = Path(cache_dir) if cache_dir is not None else self._default_cache_dir()
        self._cache_dir = base_dir
        self._project_root = base_dir.parent

    def list_logs(self) -> List[HistoryLogPayload]:
        """Return all cached history logs with inline screenshot payloads."""

        if not self._cache_dir.exists() or not self._cache_dir.is_dir():
            return []

        logs: List[HistoryLogPayload] = []
        for json_path in sorted(self._cache_dir.glob("*.json")):
            try:
                logs.append(self._load_single_log(json_path))
            except Exception as exc:  # pragma: no cover - serialization must remain stable
                raise HistoryLogsServiceError(
                    f"Unable to load history log '{json_path.name}': {exc}"
                ) from exc
        return logs

    def _load_single_log(self, json_path: Path) -> HistoryLogPayload:
        raw_payload = self._read_json(json_path)

        if not isinstance(raw_payload, dict):
            raise ValueError("History log payload must be a JSON object.")

        details_data = dict(raw_payload.get("details") or {})
        original_screenshot_paths = list(self._ensure_iterable(details_data.get("screenshots")))

        encoded_screenshots: List[Optional[str]] = []
        missing_screenshots: List[str] = []

        for path_str in original_screenshot_paths:
            resolved_path = self._resolve_screenshot_path(path_str)
            if not resolved_path or not resolved_path.exists() or not resolved_path.is_file():
                missing_screenshots.append(str(path_str))
                encoded_screenshots.append(None)
                continue

            try:
                image_bytes = resolved_path.read_bytes()
                encoded_screenshots.append(base64.b64encode(image_bytes).decode("utf-8"))
            except Exception as exc:  # pragma: no cover - IO failure edge case
                missing_screenshots.append(str(path_str))
                encoded_screenshots.append(None)

        preserved_fields = {
            "screenshots",
            "model_outputs",
            "last_action",
            "structured_output",
            "screenshot_paths",
            "missing_screenshots",
        }

        details = HistoryLogDetails(
            screenshots=encoded_screenshots,
            screenshot_paths=[str(path) for path in original_screenshot_paths],
            missing_screenshots=missing_screenshots,
            model_outputs=details_data.get("model_outputs"),
            last_action=details_data.get("last_action"),
            structured_output=details_data.get("structured_output"),
            **{key: value for key, value in details_data.items() if key not in preserved_fields},
        )

        return HistoryLogPayload(
            filename=json_path.name,
            metadata=dict(raw_payload.get("metadata") or {}),
            summary=dict(raw_payload.get("summary") or {}),
            details=details,
        )

    @staticmethod
    def _read_json(json_path: Path) -> Any:
        with json_path.open("r", encoding="utf-8") as file:
            return json.load(file)

    @staticmethod
    def _ensure_iterable(value: Any) -> Iterable[str]:
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return value
        return [value]

    def _resolve_screenshot_path(self, path_str: Any) -> Optional[Path]:
        if not path_str:
            return None

        candidate = Path(str(path_str))
        if candidate.is_absolute():
            return candidate

        # Treat paths as relative to the project root to support stored relative references.
        candidate = (self._project_root / candidate).resolve()
        return candidate

    @staticmethod
    def _default_cache_dir() -> Path:
        return Path(__file__).resolve().parents[2] / "history_logs"


class HistoryLogsReader:
    """Reader for agent execution history logs."""
    
    def __init__(self, history_dir: Optional[Path | str] = None) -> None:
        """Initialize the HistoryLogsReader.
        
        Args:
            history_dir: Directory containing history logs (defaults to history_logs/)
        """
        if history_dir is None:
            self.history_dir = Path(__file__).resolve().parents[2] / "history_logs"
        else:
            self.history_dir = Path(history_dir)
    
    def read_run(self, run_id: str) -> dict[str, Any]:
        """Read a run result by ID.
        
        Args:
            run_id: The run ID (can be partial, will match first file containing it)
            
        Returns:
            Dictionary with metadata, summary, details
            
        Raises:
            FileNotFoundError: If run not found
        """
        
        # Search for matching file
        matching_files = list(self.history_dir.glob(f"*{run_id}*.json"))
        
        if not matching_files:
            raise FileNotFoundError(f"No history logs found for run: {run_id}")
        
        # Use the first matching file
        log_file = matching_files[0]
        
        with log_file.open("r", encoding="utf-8") as f:
            return json.load(f)
    
    def read_judge_evaluation(self, run_id: str) -> Optional[dict[str, Any]]:
        """Read a judge evaluation report by run ID.
        
        Args:
            run_id: The run ID
            
        Returns:
            Judge evaluation report dict, or None if not found
        """
        
        # Search for judge evaluation files
        matching_files = list(self.history_dir.glob(f"*{run_id}*judge*.json"))
        
        if not matching_files:
            return None
        
        try:
            with matching_files[0].open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            raise FileNotFoundError(f"Failed to read judge evaluation: {e}")

