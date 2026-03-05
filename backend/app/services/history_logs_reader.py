"""Utilities for loading cached history logs and preparing them for API responses."""
from __future__ import annotations

import base64
import io
import json
import mimetypes
from pathlib import Path
from typing import Any, Iterable, List, Optional

from PIL import Image

from ..core.config import get_settings
from ..core.storage_paths import (
    get_cache_dataset_dir,
    get_cache_history_root,
    get_legacy_data1_dirs,
    normalize_cache_dataset,
    resolve_backend_path,
)
from ..schemas.history_logs import HistoryLogDetails, HistoryLogPayload


class HistoryLogsServiceError(RuntimeError):
    """Raised when cached history logs cannot be processed."""


class HistoryLogsService:
    """Provides read access to cached history logs on disk."""

    def __init__(self, cache_dir: Optional[Path | str] = None) -> None:
        self._settings = get_settings()
        self._backend_root = Path(__file__).resolve().parents[2]
        self._has_custom_cache_dir = cache_dir is not None
        self._cache_root = (
            resolve_backend_path(cache_dir, self._backend_root)
            if cache_dir is not None
            else get_cache_history_root(self._settings)
        )
        self._legacy_data1_dirs = [
            resolve_backend_path(path, self._backend_root)
            for path in get_legacy_data1_dirs(self._settings)
        ]

    def list_logs(self, dataset: str = "data1") -> List[HistoryLogPayload]:
        """Return all cached history logs with inline screenshot payloads."""
        try:
            dataset_key = normalize_cache_dataset(dataset)
        except ValueError as exc:
            raise HistoryLogsServiceError(str(exc)) from exc

        cache_dir = self._resolve_dataset_dir(dataset_key)

        if not cache_dir.exists() or not cache_dir.is_dir():
            return []

        logs: List[HistoryLogPayload] = []
        for json_path in sorted(cache_dir.glob("*.json")):
            try:
                logs.append(self._load_single_log(json_path))
            except Exception as exc:
                print(f"Warning: Skipping corrupted or invalid log file '{json_path.name}': {exc}")
                continue
        return logs

    def _resolve_dataset_dir(self, dataset_key: str) -> Path:
        if self._has_custom_cache_dir:
            return self._cache_root

        dataset_dir = get_cache_dataset_dir(self._settings, dataset_key)
        if dataset_key != "data1":
            return dataset_dir

        has_dataset_data = any(dataset_dir.glob("*.json"))
        if has_dataset_data:
            return dataset_dir

        for legacy_dir in self._legacy_data1_dirs:
            if legacy_dir.exists() and legacy_dir.is_dir() and any(legacy_dir.glob("*.json")):
                return legacy_dir

        return dataset_dir

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
                encoded_screenshots.append(self._encode_screenshot_data_uri(image_bytes, resolved_path))
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

    @staticmethod
    def _guess_mime_type(path: Optional[Path]) -> str:
        if path is None:
            return "application/octet-stream"
        guessed, _ = mimetypes.guess_type(str(path))
        return guessed or "application/octet-stream"

    @classmethod
    def _encode_raw_data_uri(cls, image_bytes: bytes, path: Optional[Path]) -> str:
        mime_type = cls._guess_mime_type(path)
        payload = base64.b64encode(image_bytes).decode("utf-8")
        return f"data:{mime_type};base64,{payload}"

    @classmethod
    def _encode_screenshot_data_uri(cls, image_bytes: bytes, path: Optional[Path]) -> str:
        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                if image.mode not in {"RGB", "RGBA"}:
                    image = image.convert("RGBA" if "A" in image.getbands() else "RGB")

                output = io.BytesIO()
                image.save(output, format="WEBP", quality=75, method=6)
                webp_bytes = output.getvalue()
                webp_payload = base64.b64encode(webp_bytes).decode("utf-8")
                return f"data:image/webp;base64,{webp_payload}"
        except Exception:
            return cls._encode_raw_data_uri(image_bytes, path)

    def _resolve_screenshot_path(self, path_str: Any) -> Optional[Path]:
        if not path_str:
            return None

        # Normalize path separators to forward slashes to handle Windows-generated paths on Linux
        clean_path = str(path_str).replace("\\", "/")
        candidate = Path(clean_path)
        
        if candidate.is_absolute():
            return candidate

        # Treat paths as relative to the project root to support stored relative references.
        candidate = (self._backend_root / candidate).resolve()
        return candidate


class HistoryLogsReader:
    """Reader for agent execution history logs."""
    
    def __init__(self, history_dir: Optional[Path | str] = None) -> None:
        """Initialize the HistoryLogsReader.
        
        Args:
            history_dir: Directory containing history logs (defaults to cache_history_logs/data1)
        """
        if history_dir is None:
            self.history_dir = get_cache_dataset_dir(get_settings(), "data1")
        else:
            self.history_dir = resolve_backend_path(history_dir)
    
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

