"""Service logic for executing browser-use agents and persisting run artifacts."""
from __future__ import annotations

import asyncio
import base64
import contextvars
import io
import json
import logging
import os
import sys
import threading
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional
from urllib.parse import quote

from ..core.config import get_settings
from ..core.storage_paths import get_browser_run_output_dir

logger = logging.getLogger(__name__)

_ACTIVE_BROWSER_AGENT_RUN_ID: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "active_browser_agent_run_id",
    default=None,
)
_ACTIVE_BROWSER_AGENT_THREAD_STATE = threading.local()
_STATUS_FIELD_UNSET = object()


def _resolve_logging_level(value: Any, default: int = logging.INFO) -> int:
    if isinstance(value, int):
        return value
    if value is None:
        return default

    try:
        candidate = str(value).strip().upper()
    except Exception:
        return default

    resolved = getattr(logging, candidate, None)
    return resolved if isinstance(resolved, int) else default

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("PIL/Pillow not available. Element screenshot cropping will be limited.")
    Image = None
    ImageDraw = None
    ImageFont = None
from ..schemas.browser_agent import (
    BrowserAgentPersona,
    BrowserAgentRunRequest,
    BrowserAgentRunResult,
    BrowserAgentScreenshot,
    BrowserAgentTask,
)
from .llm_factory import LLMConfigurationError, get_browser_use_llm


class BrowserAgentExecutionError(RuntimeError):
    """Raised when the browser agent cannot execute or persist results."""


class BrowserAgentBusyError(RuntimeError):
    """Raised when trying to start a new run while another is active."""


@dataclass
class _RunContext:
    run_id: str
    history_path: Path
    screenshots_dir: Path


@dataclass
class _ScreenshotArtifact:
    path: str
    base64_content: Optional[str] = None


@dataclass(frozen=True)
class _RunUnit:
    persona: BrowserAgentPersona
    persona_index: int
    model_name: str
    model_index: int
    run_index: int

    @property
    def key(self) -> tuple[int, int, int]:
        return (self.persona_index, self.model_index, self.run_index)


class _RunScopedLogHandler(logging.Handler):
    """Capture log lines for the currently executing browser-agent run."""

    def __init__(self, append_callback: Callable[[str, str], None]) -> None:
        super().__init__(level=logging.INFO)
        self._append_callback = append_callback

    def emit(self, record: logging.LogRecord) -> None:
        run_id = (
            getattr(record, "browser_agent_run_id", None)
            or _ACTIVE_BROWSER_AGENT_RUN_ID.get()
            or getattr(_ACTIVE_BROWSER_AGENT_THREAD_STATE, "run_id", None)
        )
        if not run_id:
            return

        try:
            message = self.format(record)
        except Exception:
            message = record.getMessage()

        self._append_callback(str(run_id), str(message))


class BrowserAgentService:
    """High-level service for orchestrating browser agent runs."""

    _LOG_HANDLER_INSTALL_LOCK = threading.Lock()
    _LOG_HANDLER_INSTALLED = False
    _ACTIVE_RUN_STATUSES = {"queued", "running"}
    _MAX_AGENT_STEPS_CAP = 20

    def __init__(self) -> None:
        self._settings = get_settings()
        self._backend_root = Path(__file__).resolve().parents[2]
        self._output_dir = get_browser_run_output_dir(self._settings)
        self._status_dir = (self._output_dir / "run_status").resolve()
        self._status_dir.mkdir(parents=True, exist_ok=True)
        self._max_concurrent = max(
            1,
            int(getattr(self._settings, "BROWSER_AGENT_MAX_CONCURRENT", 4)),
        )
        self._max_concurrent_cap = max(
            1,
            int(getattr(self._settings, "BROWSER_AGENT_MAX_CONCURRENT_CAP", 4)),
        )
        self._force_threaded_run_on_windows = bool(
            getattr(self._settings, "BROWSER_AGENT_FORCE_THREADED_RUN_ON_WINDOWS", True)
        )
        self._enable_concurrency_fallback = bool(
            getattr(self._settings, "BROWSER_AGENT_CONCURRENCY_FALLBACK_ENABLED", True)
        )
        self._concurrency_fallback_max_retries = max(
            0,
            int(getattr(self._settings, "BROWSER_AGENT_CONCURRENCY_FALLBACK_MAX_RETRIES", 2)),
        )
        self._concurrency_fallback_min = max(
            1,
            int(getattr(self._settings, "BROWSER_AGENT_CONCURRENCY_FALLBACK_MIN", 1)),
        )
        self._enable_screenshots = getattr(self._settings, "BROWSER_AGENT_ENABLE_SCREENSHOTS", True)
        self._enable_screenshot_processing = getattr(
            self._settings,
            "BROWSER_AGENT_ENABLE_SCREENSHOT_PROCESSING",
            False,
        )
        self._max_screenshots = max(
            0,
            int(getattr(self._settings, "BROWSER_AGENT_MAX_SCREENSHOTS", 3)),
        )
        self._include_screenshots_in_run_response = False
        self._active_run_tasks: Dict[str, List[asyncio.Task[BrowserAgentRunResult]]] = {}
        self._active_runs_lock = asyncio.Lock()
        # Background run management
        self._run_store: Dict[str, dict] = {}
        self._run_screenshot_url_prefixes: Dict[str, str] = {}
        self._background_run_tasks: Dict[str, asyncio.Task[None]] = {}
        self._run_runtime_stats: Dict[str, dict] = {}
        self._run_logs: Dict[str, deque[str]] = {}
        self._run_logs_lock = threading.Lock()
        configured_log_buffer_size = int(
            getattr(self._settings, "BROWSER_AGENT_STATUS_LOG_BUFFER_SIZE", 0)
        )
        self._run_log_max_entries: Optional[int] = (
            configured_log_buffer_size if configured_log_buffer_size > 0 else None
        )
        status_log_level = _resolve_logging_level(
            getattr(self._settings, "BROWSER_AGENT_STATUS_LOG_LEVEL", "INFO"),
            default=logging.INFO,
        )
        self._run_log_handler = _RunScopedLogHandler(self._append_run_log)
        self._run_log_handler.setLevel(status_log_level)
        self._run_log_handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        self._stream_run_logs_to_stdout = bool(
            getattr(self._settings, "BROWSER_AGENT_STREAM_RUN_LOGS_TO_STDOUT", True)
        )
        self._stdout_run_logger: Optional[logging.Logger] = None

        self._configure_external_log_sources()

        with self.__class__._LOG_HANDLER_INSTALL_LOCK:
            if not self.__class__._LOG_HANDLER_INSTALLED:
                logging.getLogger().addHandler(self._run_log_handler)
                self.__class__._LOG_HANDLER_INSTALLED = True

        if self._stream_run_logs_to_stdout:
            self._stdout_run_logger = self._get_stdout_run_logger(status_log_level)

    def _configure_external_log_sources(self) -> None:
        source_level = _resolve_logging_level(
            getattr(self._settings, "BROWSER_AGENT_EXTERNAL_LOG_LEVEL", "INFO"),
            default=logging.INFO,
        )
        source_logger_names = (
            "app.services.browser_agent_runner",
            "browser_use",
            "browser_use.agent",
            "browser_use.agent.service",
            "browser_use.browser",
            "cdp_use",
            "cdp_use.client",
        )

        for logger_name in source_logger_names:
            source_logger = logging.getLogger(logger_name)
            source_logger.setLevel(source_level)
            source_logger.propagate = True

    def _get_stdout_run_logger(self, log_level: int) -> logging.Logger:
        stdout_logger = logging.getLogger("app.browser_agent.runlog")
        stdout_logger.setLevel(log_level)
        stdout_logger.propagate = False

        if not any(getattr(handler, "_browser_agent_runlog_stdout", False) for handler in stdout_logger.handlers):
            stream_handler = logging.StreamHandler(stream=sys.stdout)
            stream_handler.setLevel(log_level)
            stream_handler.setFormatter(
                logging.Formatter(
                    fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            setattr(stream_handler, "_browser_agent_runlog_stdout", True)
            stdout_logger.addHandler(stream_handler)

        return stdout_logger

    def _status_file_path(self, run_id: str) -> Path:
        return self._status_dir / f"{run_id}.json"

    @staticmethod
    def _normalize_run_id(run_id: str) -> str:
        return (run_id or "").strip()

    def _reset_run_logs(self, run_id: str) -> None:
        normalized_run_id = self._normalize_run_id(run_id)
        if not normalized_run_id:
            return
        with self._run_logs_lock:
            if self._run_log_max_entries is None:
                self._run_logs[normalized_run_id] = deque()
            else:
                self._run_logs[normalized_run_id] = deque(maxlen=self._run_log_max_entries)

    def _append_run_log(self, run_id: str, message: str) -> None:
        normalized_run_id = self._normalize_run_id(run_id)
        if not normalized_run_id:
            return

        text = str(message or "").strip()
        if not text:
            return

        with self._run_logs_lock:
            buffer = self._run_logs.get(normalized_run_id)
            if buffer is None:
                if self._run_log_max_entries is None:
                    buffer = deque()
                else:
                    buffer = deque(maxlen=self._run_log_max_entries)
                self._run_logs[normalized_run_id] = buffer
            buffer.append(text)
            snapshot = list(buffer)

        status_payload = self._run_store.get(normalized_run_id)
        if isinstance(status_payload, dict):
            status_payload["logs"] = snapshot

        if self._stdout_run_logger is not None:
            try:
                self._stdout_run_logger.info("[%s] %s", normalized_run_id, text)
            except Exception:
                pass

    def _get_run_logs(self, run_id: str) -> List[str]:
        normalized_run_id = self._normalize_run_id(run_id)
        if not normalized_run_id:
            return []

        with self._run_logs_lock:
            buffer = self._run_logs.get(normalized_run_id)
            if not buffer:
                return []
            return list(buffer)

    def _write_run_status(self, run_id: str, payload: dict) -> None:
        normalized_run_id = self._normalize_run_id(run_id)
        if not normalized_run_id:
            return

        enriched_payload = {
            **payload,
            "logs": self._get_run_logs(run_id),
        }
        self._run_store[normalized_run_id] = enriched_payload
        try:
            status_file = self._status_file_path(normalized_run_id)
            status_file.parent.mkdir(parents=True, exist_ok=True)
            status_file.write_text(
                json.dumps(enriched_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Failed to persist run status | run_id=%s error=%s", normalized_run_id, exc)

    def _set_run_status(
        self,
        run_id: str,
        status: str,
        *,
        total_tasks: Optional[int] = None,
        results: Any = None,
        error: Optional[str] = None,
        runtime: Any = _STATUS_FIELD_UNSET,
    ) -> Optional[dict]:
        normalized_run_id = self._normalize_run_id(run_id)
        if not normalized_run_id:
            return None

        previous = self._run_store.get(normalized_run_id)
        if not isinstance(previous, dict):
            previous = self._read_run_status(normalized_run_id) or {}

        resolved_total_tasks = previous.get("total_tasks", 0) if total_tasks is None else total_tasks
        payload = {
            "run_id": normalized_run_id,
            "status": status,
            "total_tasks": resolved_total_tasks,
            "results": results,
            "error": error,
        }

        if runtime is not _STATUS_FIELD_UNSET:
            payload["runtime"] = runtime

        self._write_run_status(normalized_run_id, payload)
        return payload

    def _read_run_status(self, run_id: str) -> Optional[dict]:
        normalized_run_id = self._normalize_run_id(run_id)
        if not normalized_run_id:
            return None

        status_file = self._status_file_path(normalized_run_id)
        if not status_file.exists():
            return None
        try:
            return json.loads(status_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to read persisted run status | run_id=%s error=%s", normalized_run_id, exc)
            return None

    @property
    def current_run_task(self) -> Optional[asyncio.Task]:
        for task in self._background_run_tasks.values():
            if not task.done():
                return task
        return None

    def get_active_run_id(self) -> Optional[str]:
        for run_id, payload in self._run_store.items():
            if payload.get("status") in self._ACTIVE_RUN_STATUSES:
                return run_id
        return None

    def get_active_run_ids(self) -> List[str]:
        return [
            run_id
            for run_id, payload in self._run_store.items()
            if payload.get("status") in self._ACTIVE_RUN_STATUSES
        ]

    def register_queued_run(self, run_id: str, total_tasks: int) -> None:
        normalized_run_id = self._normalize_run_id(run_id)
        if not normalized_run_id:
            return

        self._reset_run_logs(normalized_run_id)
        self._append_run_log(
            normalized_run_id,
            f"Run queued | run_id={normalized_run_id} total_tasks={total_tasks}",
        )
        self._set_run_status(
            normalized_run_id,
            "queued",
            total_tasks=total_tasks,
            results=None,
            error=None,
        )

    def mark_run_running(self, run_id: str, total_tasks: int = 0) -> None:
        normalized_run_id = self._normalize_run_id(run_id)
        if not normalized_run_id:
            return

        self._append_run_log(
            normalized_run_id,
            f"Run started | run_id={normalized_run_id} total_tasks={total_tasks}",
        )
        self._set_run_status(
            normalized_run_id,
            "running",
            total_tasks=total_tasks,
            results=None,
            error=None,
        )

    def mark_run_failed(self, run_id: str, error: str) -> None:
        normalized_run_id = self._normalize_run_id(run_id)
        if not normalized_run_id:
            return

        previous = self.get_run_status(normalized_run_id) or {}
        self._append_run_log(normalized_run_id, f"Run failed | run_id={normalized_run_id} error={error}")
        self._set_run_status(
            normalized_run_id,
            "failed",
            total_tasks=previous.get("total_tasks", 0),
            results=previous.get("results"),
            error=error,
        )

    def _set_run_runtime_stats(self, run_id: str, payload: dict) -> None:
        if not run_id:
            return
        self._run_runtime_stats[run_id] = payload

    def _get_run_runtime_stats(self, run_id: str) -> Optional[dict]:
        if not run_id:
            return None
        return self._run_runtime_stats.get(run_id)

    def _clear_run_runtime_stats(self, run_id: str) -> None:
        if not run_id:
            return
        self._run_runtime_stats.pop(run_id, None)

    def set_run_screenshot_url_prefix(self, run_id: str, prefix: str) -> None:
        normalized_run_id = self._normalize_run_id(run_id)
        normalized_prefix = (prefix or "").strip()
        if not normalized_run_id:
            return
        if not normalized_prefix:
            self._run_screenshot_url_prefixes.pop(normalized_run_id, None)
            return
        self._run_screenshot_url_prefixes[normalized_run_id] = normalized_prefix.rstrip("/")

    def _pop_run_screenshot_url_prefix(self, run_id: str) -> None:
        normalized_run_id = self._normalize_run_id(run_id)
        if not normalized_run_id:
            return
        self._run_screenshot_url_prefixes.pop(normalized_run_id, None)

    def _get_run_screenshot_url_prefix(self, run_id: str) -> str:
        normalized_run_id = self._normalize_run_id(run_id)
        if normalized_run_id and normalized_run_id in self._run_screenshot_url_prefixes:
            return self._run_screenshot_url_prefixes[normalized_run_id]

        configured_base = str(getattr(self._settings, "PUBLIC_API_BASE_URL", "") or "").strip().rstrip("/")
        api_prefix = str(getattr(self._settings, "API_V1_PREFIX", "/api/v1") or "/api/v1").strip()
        if configured_base:
            if configured_base.endswith(api_prefix):
                return f"{configured_base}/browser-agent/screenshot"
            return f"{configured_base}{api_prefix}/browser-agent/screenshot"

        return f"{api_prefix}/browser-agent/screenshot"

    @staticmethod
    def _build_run_screenshot_proxy_url(path_str: Any, screenshot_url_prefix: str) -> Optional[str]:
        if path_str is None:
            return None

        clean_path = str(path_str).replace("\\", "/").strip()
        if not clean_path:
            return None

        prefix = str(screenshot_url_prefix or "").strip().rstrip("/")
        if not prefix:
            prefix = "/api/v1/browser-agent/screenshot"

        encoded_path = quote(clean_path, safe="")
        return f"{prefix}?path={encoded_path}"

    @staticmethod
    def _path_is_within_root(path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except ValueError:
            return False

    def resolve_run_screenshot_file(self, path_str: str) -> Optional[Path]:
        clean_path = str(path_str or "").replace("\\", "/").strip()
        if not clean_path:
            return None

        candidate = Path(clean_path)
        output_root = self._output_dir.resolve()
        candidate_paths: list[Path] = []

        if candidate.is_absolute():
            candidate_paths.append(candidate.resolve())
        else:
            candidate_paths.extend([
                (output_root / candidate).resolve(),
                (self._backend_root / candidate).resolve(),
                (Path.cwd().resolve() / candidate).resolve(),
            ])

            parts = [part for part in candidate.parts if part not in {"", "."}]
            if parts:
                try:
                    marker_index = parts.index("browser_agent_runs")
                    tail_parts = parts[marker_index + 1:]
                    if tail_parts:
                        candidate_paths.append((output_root / Path(*tail_parts)).resolve())
                except ValueError:
                    pass

                if len(parts) >= 2 and parts[0] == "history_logs" and parts[1] == "browser_agent_runs":
                    tail_parts = parts[2:]
                    if tail_parts:
                        candidate_paths.append((output_root / Path(*tail_parts)).resolve())

        deduped_paths: list[Path] = []
        seen: set[Path] = set()
        for path_item in candidate_paths:
            if path_item in seen:
                continue
            seen.add(path_item)
            deduped_paths.append(path_item)

        for resolved in deduped_paths:
            if not self._path_is_within_root(resolved, output_root):
                continue
            if resolved.exists() and resolved.is_file():
                return resolved

        return None

    async def run(self, request: BrowserAgentRunRequest, run_id: Optional[str] = None) -> List[BrowserAgentRunResult]:
        """Execute the browser agent across all persona/model combinations."""
        effective_run_id = (run_id or request.run_id or str(uuid.uuid4())).strip()
        run_units: List[_RunUnit] = []

        for persona_index, persona in enumerate(request.personas, start=1):
            for model_index, model_name in enumerate(request.models, start=1):
                for run_index in range(1, request.run_times + 1):
                    run_units.append(
                        _RunUnit(
                            persona=persona,
                            persona_index=persona_index,
                            model_name=model_name,
                            model_index=model_index,
                            run_index=run_index,
                        )
                    )

        if not run_units:
            return []

        requested_max_concurrent = min(self._max_concurrent, self._max_concurrent_cap)
        concurrency_stages = self._build_concurrency_stages(requested_max_concurrent)
        result_map: Dict[tuple[int, int, int], BrowserAgentRunResult] = {}
        pending_units = list(run_units)
        fallback_events: List[dict] = []

        logger.info(
            "Browser-agent run scheduling | run_id=%s total=%d max_concurrent=%d cap=%d stages=%s",
            effective_run_id,
            len(run_units),
            requested_max_concurrent,
            self._max_concurrent_cap,
            concurrency_stages,
        )

        try:
            for stage_index, stage_concurrency in enumerate(concurrency_stages, start=1):
                if not pending_units:
                    break

                stage_semaphore = asyncio.Semaphore(stage_concurrency)

                stage_tasks = [
                    asyncio.create_task(
                        self._run_with_semaphore(
                            stage_semaphore,
                            self._run_single(
                                request=request,
                                persona=unit.persona,
                                persona_index=unit.persona_index,
                                model_name=unit.model_name,
                                model_index=unit.model_index,
                                run_index=unit.run_index,
                            ),
                        )
                    )
                    for unit in pending_units
                ]

                await self._register_active_run(effective_run_id, stage_tasks)
                try:
                    stage_results = await asyncio.gather(*stage_tasks, return_exceptions=False)
                finally:
                    await self._unregister_active_run(effective_run_id)

                retry_units: List[_RunUnit] = []
                has_next_stage = stage_index < len(concurrency_stages)

                for unit, result in zip(pending_units, stage_results):
                    if has_next_stage and self._result_needs_lower_concurrency(result):
                        retry_units.append(unit)
                        continue
                    result_map[unit.key] = result

                if not retry_units:
                    pending_units = []
                    continue

                next_concurrency = concurrency_stages[stage_index]
                fallback_events.append(
                    {
                        "stage": stage_index,
                        "from": stage_concurrency,
                        "to": next_concurrency,
                        "retry_count": len(retry_units),
                    }
                )
                logger.warning(
                    "Browser-agent concurrency fallback triggered | run_id=%s stage=%d from=%d to=%d retry_tasks=%d",
                    effective_run_id,
                    stage_index,
                    stage_concurrency,
                    next_concurrency,
                    len(retry_units),
                )
                pending_units = retry_units

            ordered_results = [
                result_map[unit.key]
                for unit in run_units
                if unit.key in result_map
            ]

            self._set_run_runtime_stats(
                effective_run_id,
                {
                    "requested_max_concurrent": requested_max_concurrent,
                    "effective_stages": concurrency_stages,
                    "fallback_enabled": self._enable_concurrency_fallback,
                    "fallback_events": fallback_events,
                },
            )
            return ordered_results
        except asyncio.CancelledError:
            logger.info("Browser-agent run cancelled | run_id=%s", effective_run_id)
            raise

    def _build_concurrency_stages(self, requested_max_concurrent: int) -> List[int]:
        base = max(1, min(requested_max_concurrent, self._max_concurrent_cap))
        if not self._enable_concurrency_fallback or self._concurrency_fallback_max_retries <= 0:
            return [base]

        min_concurrency = max(1, min(self._concurrency_fallback_min, base))
        stages = [base]
        current = base

        for _ in range(self._concurrency_fallback_max_retries):
            if current <= min_concurrency:
                break
            current = max(min_concurrency, current // 2)
            if current in stages:
                break
            stages.append(current)

        if stages[-1] != min_concurrency:
            stages.append(min_concurrency)

        return stages

    def _result_needs_lower_concurrency(self, result: BrowserAgentRunResult) -> bool:
        if not result.has_errors:
            return False

        message = str(result.final_result or "").lower()
        retryable_indicators = [
            "browser failed to start",
            "timeout",
            "target closed",
            "browser has been closed",
            "too many open files",
            "resource temporarily unavailable",
            "out of memory",
            "cannot allocate memory",
            "net::err_insufficient_resources",
        ]
        return any(indicator in message for indicator in retryable_indicators)

    async def stop_run(self, run_id: str) -> bool:
        """Cancel all active tasks for a run_id."""
        normalized_run_id = self._normalize_run_id(run_id)
        if not normalized_run_id:
            return False

        cancelled_any = False

        # Cancel inner agent tasks
        async with self._active_runs_lock:
            tasks = list(self._active_run_tasks.get(normalized_run_id, []))

        for task in tasks:
            if not task.done():
                task.cancel()
                cancelled_any = True

        # Cancel the background wrapper task
        background_task = self._background_run_tasks.get(normalized_run_id)
        if background_task is not None and not background_task.done():
            background_task.cancel()
            cancelled_any = True

        # Update run store
        previous = self.get_run_status(normalized_run_id) or {}
        if previous:
            self._set_run_status(
                normalized_run_id,
                "cancelled",
                total_tasks=previous.get("total_tasks", 0),
                results=None,
                error="Run was cancelled by user",
            )

        logger.info("Browser-agent stop requested | run_id=%s cancelled=%s", normalized_run_id, cancelled_any)
        return cancelled_any or bool(previous)

    async def _register_active_run(
        self,
        run_id: str,
        tasks: List[asyncio.Task[BrowserAgentRunResult]],
    ) -> None:
        async with self._active_runs_lock:
            self._active_run_tasks[run_id] = tasks

    async def _unregister_active_run(self, run_id: str) -> None:
        async with self._active_runs_lock:
            self._active_run_tasks.pop(run_id, None)

    # ── Background run management ──────────────────────────────────────

    def start_run(self, request: BrowserAgentRunRequest, run_id: str) -> dict:
        """Start a browser agent run in the background. Returns immediately.

        Raises BrowserAgentBusyError if another run is already active.
        """
        normalized_run_id = self._normalize_run_id(run_id)
        if not normalized_run_id:
            raise BrowserAgentExecutionError("run_id must not be empty.")

        existing_task = self._background_run_tasks.get(normalized_run_id)
        if existing_task is not None and not existing_task.done():
            raise BrowserAgentBusyError(
                f"Run is already in progress for run_id={normalized_run_id}. "
                "Stop it first or wait for it to finish."
            )

        previous = self._run_store.get(normalized_run_id, {})
        payload = self._set_run_status(
            normalized_run_id,
            "running",
            total_tasks=previous.get("total_tasks", 0),
            results=None,
            error=None,
        ) or {
            "run_id": normalized_run_id,
            "status": "running",
            "total_tasks": previous.get("total_tasks", 0),
            "results": None,
            "error": None,
        }

        self._background_run_tasks[normalized_run_id] = asyncio.create_task(
            self._execute_run_background(request, normalized_run_id)
        )
        logger.info("Browser-agent background run started | run_id=%s", normalized_run_id)
        return payload

    def get_background_run_task(self, run_id: str) -> Optional[asyncio.Task[None]]:
        return self._background_run_tasks.get(self._normalize_run_id(run_id))

    async def _execute_run_background(self, request: BrowserAgentRunRequest, run_id: str) -> None:
        """Background task: execute agent, post-process results, store in _run_store."""
        timeout = getattr(self._settings, "BROWSER_AGENT_RUN_TIMEOUT", 0)
        run_context_token = _ACTIVE_BROWSER_AGENT_RUN_ID.set(run_id)
        try:
            self._append_run_log(run_id, f"Background execution started | run_id={run_id}")
            if timeout and timeout > 0:
                results = await asyncio.wait_for(
                    self.run(request, run_id=run_id),
                    timeout=timeout,
                )
            else:
                results = await self.run(request, run_id=run_id)

            processed = self._post_process_results(request, results, run_id=run_id)
            has_errors = any(
                bool(item.get("has_errors")) or not bool(item.get("is_successful"))
                for item in processed
            )

            if has_errors:
                runtime_stats = self._get_run_runtime_stats(run_id)
                self._set_run_status(
                    run_id,
                    "failed",
                    results=processed,
                    error="One or more browser-agent runs failed.",
                    runtime=runtime_stats,
                )
                logger.warning(
                    "Background run finished with errors | run_id=%s results=%d",
                    run_id,
                    len(processed),
                )
                self._append_run_log(
                    run_id,
                    f"Background execution finished with errors | run_id={run_id} results={len(processed)}",
                )
            else:
                runtime_stats = self._get_run_runtime_stats(run_id)
                self._set_run_status(
                    run_id,
                    "completed",
                    results=processed,
                    error=None,
                    runtime=runtime_stats,
                )
                logger.info("Background run completed | run_id=%s results=%d", run_id, len(processed))
                self._append_run_log(
                    run_id,
                    f"Background execution completed | run_id={run_id} results={len(processed)}",
                )

        except asyncio.TimeoutError:
            timeout_error = f"Run timed out after {timeout} seconds"
            fallback_results = self._build_failed_results_for_request(
                request=request,
                run_id=run_id,
                final_result=timeout_error,
            )
            runtime_stats = self._get_run_runtime_stats(run_id)
            self._set_run_status(
                run_id,
                "failed",
                results=fallback_results,
                error=timeout_error,
                runtime=runtime_stats,
            )
            logger.warning("Background run timed out | run_id=%s timeout=%ds", run_id, timeout)
            self._append_run_log(run_id, f"Background execution timed out | run_id={run_id} timeout={timeout}s")

        except asyncio.CancelledError:
            if self._run_store.get(run_id, {}).get("status") != "cancelled":
                runtime_stats = self._get_run_runtime_stats(run_id)
                self._set_run_status(
                    run_id,
                    "cancelled",
                    results=None,
                    error="Run was cancelled",
                    runtime=runtime_stats,
                )
            logger.info("Background run cancelled | run_id=%s", run_id)
            self._append_run_log(run_id, f"Background execution cancelled | run_id={run_id}")

        except Exception as exc:
            fallback_results = self._build_failed_results_for_request(
                request=request,
                run_id=run_id,
                final_result=str(exc),
            )
            runtime_stats = self._get_run_runtime_stats(run_id)
            self._set_run_status(
                run_id,
                "failed",
                results=fallback_results,
                error=str(exc),
                runtime=runtime_stats,
            )
            logger.exception("Background run failed | run_id=%s", run_id)
            self._append_run_log(run_id, f"Background execution exception | run_id={run_id} error={exc}")

        finally:
            self._background_run_tasks.pop(run_id, None)
            self._pop_run_screenshot_url_prefix(run_id)
            self._clear_run_runtime_stats(run_id)
            _ACTIVE_BROWSER_AGENT_RUN_ID.reset(run_context_token)

    def get_run_status(self, run_id: str) -> Optional[dict]:
        """Return the current status dict for a run, or None if not found."""
        normalized_run_id = self._normalize_run_id(run_id)
        if not normalized_run_id:
            return None

        status = self._run_store.get(normalized_run_id)
        if status is not None:
            status.setdefault("logs", self._get_run_logs(normalized_run_id))
            return status
        persisted = self._read_run_status(normalized_run_id)
        if persisted is not None:
            persisted.setdefault("logs", self._get_run_logs(normalized_run_id))
        return persisted

    def _post_process_results(
        self,
        request: BrowserAgentRunRequest,
        results: List[BrowserAgentRunResult],
        run_id: str,
    ) -> list:
        """Transform raw BrowserAgentRunResult list into serialisable dicts for the API."""
        from datetime import datetime, timezone

        screenshot_url_prefix = self._get_run_screenshot_url_prefix(run_id)

        now_utc = datetime.now(timezone.utc).isoformat()
        processed: list = []

        for result in results:
            raw_payload = result.history_payload if isinstance(result.history_payload, dict) else {}
            existing_metadata = result.metadata if isinstance(result.metadata, dict) else {}

            metadata = {
                "id": raw_payload.get("metadata", {}).get("id"),
                "task": {"name": request.task.name, "url": request.task.url},
                "timestamp_utc": now_utc,
                "value": existing_metadata.get("value"),
                "persona": existing_metadata.get("persona"),
            }

            details = raw_payload.get("details", raw_payload)
            screenshot_paths = getattr(result, "screenshot_paths", []) or details.get("screenshots", [])
            history_payload = {
                "screenshots": [
                    self._build_run_screenshot_proxy_url(path_str=path, screenshot_url_prefix=screenshot_url_prefix)
                    for path in screenshot_paths
                ],
                "screenshot_paths": screenshot_paths,
                "step_descriptions": details.get("step_descriptions", []),
                "model_outputs": details.get("model_outputs", None),
                "last_action": details.get("last_action", None),
                "summary": raw_payload.get("summary"),
                "metadata": raw_payload.get("metadata"),
            }

            processed.append({
                "model": result.model,
                "run_index": result.run_index,
                "is_done": result.is_done,
                "is_successful": result.is_successful,
                "has_errors": result.has_errors,
                "number_of_steps": result.number_of_steps,
                "total_duration_seconds": result.total_duration_seconds,
                "final_result": result.final_result,
                "history_path": result.history_path,
                "history_payload": history_payload,
                "screenshot_paths": getattr(result, "screenshot_paths", []) or [],
                "screenshots": [],
                "metadata": metadata,
            })

        return processed

    def _build_failed_results_for_request(
        self,
        *,
        request: BrowserAgentRunRequest,
        run_id: str,
        final_result: str,
    ) -> list:
        failed_results: List[BrowserAgentRunResult] = []
        for persona in request.personas:
            for model_name in request.models:
                for run_index in range(1, request.run_times + 1):
                    failed_results.append(
                        self._build_failed_run_result(
                            model_name=model_name,
                            run_index=run_index,
                            persona=persona,
                            final_result=final_result,
                        )
                    )
        return self._post_process_results(request, failed_results, run_id=run_id)

    # ── End background run management ──────────────────────────────────

    async def _run_with_semaphore(self, semaphore: asyncio.Semaphore, coro: Awaitable) -> Any:
        async with semaphore:
            return await coro

    def _is_api_error(self, error: Exception) -> bool:
        """Check if error is an API error (insufficient balance, API key issue, etc.)."""
        error_str = str(error).lower()
        api_error_indicators = [
            "insufficient balance",
            "error code: 402",
            "invalid_request_error",
            "authentication",
            "api key",
            "unauthorized",
            "forbidden",
            "rate limit",
            "quota",
        ]
        return any(indicator in error_str for indicator in api_error_indicators)

    @staticmethod
    def _find_chrome_executable() -> Optional[str]:
        """Detect available Chrome / Chromium binary.

        Checks (in order):
        1. CHROME_PATH / CHROMIUM_PATH env vars
        2. Common Linux system paths
        3. Playwright-installed Chromium
        4. ``shutil.which`` fallback
        """
        import shutil

        # 1. Environment variables
        for env_var in ("CHROME_PATH", "CHROMIUM_PATH", "BROWSER_PATH"):
            path = os.environ.get(env_var)
            if path and os.path.isfile(path) and os.access(path, os.X_OK):
                return path

        # 2. Common system paths (linux Docker images)
        system_paths = [
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/lib/chromium/chromium",
        ]
        for p in system_paths:
            if os.path.isfile(p) and os.access(p, os.X_OK):
                return p

        # 3. Playwright-managed Chromium
        try:
            from pathlib import Path as _Path
            pw_cache = _Path.home() / ".cache" / "ms-playwright"
            if pw_cache.exists():
                for chrome_dir in sorted(pw_cache.glob("chromium-*/chrome-linux/chrome"), reverse=True):
                    if chrome_dir.is_file() and os.access(str(chrome_dir), os.X_OK):
                        return str(chrome_dir)
        except Exception:
            pass

        # 4. which fallback
        for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
            found = shutil.which(name)
            if found:
                return found

        return None

    def _get_fallback_llm(self, original_model: str):
        """Get fallback Ollama LLM when primary LLM fails."""
        try:
            from .llm_factory import get_browser_use_llm
            fallback_model = self._settings.FALLBACK_LLM_MODEL
            logger.info(f"Attempting fallback to Ollama model: {fallback_model} (original: {original_model})")
            return get_browser_use_llm(model=fallback_model)
        except Exception as e:
            logger.error(f"Failed to create fallback LLM: {str(e)}")
            return None

    async def _run_single(
        self,
        *,
        request: BrowserAgentRunRequest,
        persona: BrowserAgentPersona,
        persona_index: int,
        model_name: str,
        model_index: int,
        run_index: int,
    ) -> BrowserAgentRunResult:
        """Execute a single browser agent run and persist its artifacts."""
        tmp_profile = None
        agent = None
        browser_session = None
        browser_start_timeout = getattr(
            self._settings, "BROWSER_AGENT_BROWSER_START_TIMEOUT", 120
        )
        chrome_executable: Optional[str] = None
        try:
            combined_task = self._compose_agent_task(
                task=request.task,
                content=persona.content,
            )

            # Use the explicitly selected model from the UI
            llm = get_browser_use_llm(model=model_name)

            # Set timeout for BrowserStartEvent to avoid server timeouts
            os.environ["TIMEOUT_BrowserStartEvent"] = str(browser_start_timeout)
            browser_launch_timeout = getattr(
                self._settings, "BROWSER_AGENT_BROWSER_LAUNCH_TIMEOUT", 120
            )
            os.environ["TIMEOUT_BrowserLaunchEvent"] = str(browser_launch_timeout)

            from browser_use import Agent, BrowserSession
            import tempfile

            # Create a temporary profile directory for this run
            tmp_profile = tempfile.mkdtemp(prefix="bu_profile_")

            # Detect the Chromium / Chrome executable path
            # Priority: env var > common system paths
            chrome_executable = self._find_chrome_executable()
            if chrome_executable:
                logger.info(f"Using browser executable: {chrome_executable}")
            else:
                logger.warning(
                    "No explicit Chrome/Chromium binary found; "
                    "browser_use will try to auto-detect."
                )

            # Build BrowserSession kwargs
            browser_kwargs: dict = dict(
                headless=True,
                user_data_dir=tmp_profile,
                storage_state=None,
                keep_alive=False,
                is_local=True,
                use_cloud=False,
                cloud_browser=False,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-setuid-sandbox",
                    "--no-zygote",
                    "--disable-software-rasterizer",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--disable-default-apps",
                    "--disable-sync",
                    "--no-first-run",
                ],
            )
            if chrome_executable:
                browser_kwargs["executable_path"] = chrome_executable

            browser_session = BrowserSession(**browser_kwargs)

            context = self._prepare_run_context(
                model_name=model_name,
            )

            agent = Agent(
                browser_session=browser_session,
                task=combined_task,
                llm=llm,
                use_vision=True,
                save_conversation_path=str(context.screenshots_dir),
                use_judge=False,
                generate_gif=False,
            )

            configured_max_steps = int(getattr(self._settings, "BROWSER_AGENT_MAX_STEPS", self._MAX_AGENT_STEPS_CAP))
            max_steps = max(1, min(configured_max_steps, self._MAX_AGENT_STEPS_CAP))
            history = await self._run_agent_with_compatible_loop(agent, max_steps=max_steps)

            # Log history object details for debugging
            logger.info(f"Agent run completed. History type: {type(history)}, Has screenshots: {hasattr(history, 'screenshots')}")
            
            is_done = self._ensure_bool(self._safe_call(history, "is_done"))
            is_successful = self._ensure_bool(self._safe_call(history, "is_successful"))
            has_errors = self._ensure_bool(self._safe_call(history, "has_errors"))
            number_of_steps = self._ensure_int(self._safe_call(history, "number_of_steps"))
            total_duration_seconds = self._ensure_float(
                self._safe_call(history, "total_duration_seconds")
            )
            final_result = self._to_serializable(self._safe_call(history, "final_result"))
            
            if number_of_steps == 0:
                logger.warning(f"Agent run completed with 0 steps. This may indicate the agent didn't execute properly. is_done: {is_done}, is_successful: {is_successful}, has_errors: {has_errors}")

            summary_payload = {
                "is_done": is_done,
                "is_successful": is_successful,
                "has_errors": has_errors,
                "number_of_steps": number_of_steps,
                "total_duration_seconds": total_duration_seconds,
                "final_result": final_result,
            }

            screenshot_artifacts = self._save_screenshots(history, context)
            history_payload = self._build_history_payload(
                request=request,
                persona=persona,
                model_name=model_name,
                run_index=run_index,
                run_id=context.run_id,
                history=history,
                screenshots=screenshot_artifacts,
                summary=summary_payload,
            )
            context.history_path.write_text(
                json.dumps(history_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            screenshot_paths = [artifact.path for artifact in screenshot_artifacts]

            return BrowserAgentRunResult(
                model=model_name,  # Use the explicitly selected model
                run_index=run_index,
                is_done=is_done,
                is_successful=is_successful,
                has_errors=has_errors,
                number_of_steps=number_of_steps,
                total_duration_seconds=total_duration_seconds,
                final_result=final_result,
                history_path=self._to_relative_path(context.history_path),
                history_payload=history_payload,
                screenshot_paths=[self._to_relative_path(Path(path)) for path in screenshot_paths],
                screenshots=(
                    [
                        BrowserAgentScreenshot(
                            path=self._to_relative_path(Path(artifact.path)),
                            content_base64=artifact.base64_content or "",
                        )
                        for artifact in screenshot_artifacts
                    ]
                    if self._include_screenshots_in_run_response
                    else []
                ),
                metadata={
                    "value": persona.value,
                    "persona": persona.content
                }
            )
        except asyncio.CancelledError:
            logger.info(
                "Browser-agent single run cancelled | task=%s value=%s model=%s run_index=%d",
                request.task.name,
                persona.value,
                model_name,
                run_index,
            )
            raise
        except TimeoutError as exc:
            import traceback
            error_msg = (
                f"Browser failed to start within {browser_start_timeout}s. "
                f"Chrome binary: {chrome_executable or 'auto-detect'}. "
                f"This usually means Chromium is not installed or cannot run in this environment. "
                f"Original error: {exc}"
            )
            logger.error(f"[BROWSER_START_TIMEOUT] {error_msg}\n{traceback.format_exc()}")
            return self._build_failed_run_result(
                model_name=model_name,
                run_index=run_index,
                persona=persona,
                final_result=error_msg,
            )
        except Exception as exc:
            import traceback
            logger.error("Exception in _run_single: %s\n%s", exc, traceback.format_exc())
            return self._build_failed_run_result(
                model_name=model_name,
                run_index=run_index,
                persona=persona,
                final_result=str(exc),
            )
        finally:
            # Close browser-use resources AFTER history/screenshot extraction.
            await self._close_agent_resources(agent)

            # Clean up temporary profile directory
            if tmp_profile and os.path.isdir(tmp_profile):
                try:
                    import shutil
                    shutil.rmtree(tmp_profile, ignore_errors=True)
                except Exception:
                    pass

    def _build_failed_run_result(
        self,
        *,
        model_name: str,
        run_index: int,
        persona: BrowserAgentPersona,
        final_result: str,
    ) -> BrowserAgentRunResult:
        return BrowserAgentRunResult(
            model=model_name,
            run_index=run_index,
            is_done=False,
            is_successful=False,
            has_errors=True,
            number_of_steps=0,
            total_duration_seconds=0.0,
            final_result=final_result,
            history_path="",
            history_payload={},
            screenshot_paths=[],
            screenshots=[],
            metadata={
                "value": persona.value,
                "persona": persona.content,
            },
        )

    async def _close_resource(self, resource: Any, resource_name: str) -> None:
        if resource is None:
            return

        for method_name in ("close", "aclose", "shutdown", "stop", "__aexit__"):
            if not hasattr(resource, method_name):
                continue
            try:
                close_result = getattr(resource, method_name)()
                if asyncio.iscoroutine(close_result):
                    await close_result
            except RuntimeError as exc:
                if "Event loop is closed" not in str(exc):
                    logger.warning("Exception when closing %s (%s): %s", resource_name, method_name, exc)
            except Exception as exc:
                logger.warning("Exception when closing %s (%s): %s", resource_name, method_name, exc)
            break

    async def _close_agent_resources(self, agent: Any) -> None:
        """Best-effort close for agent and underlying browser session."""
        if agent is None:
            return

        await self._close_resource(agent, "agent")

        browser_session = getattr(agent, "browser_session", None)
        await self._close_resource(browser_session, "browser_session")

    def _prepare_run_context(
        self,
        *,
        model_name: str,
    ) -> _RunContext:
        """Initialise output directories for the given run."""

        self._output_dir.mkdir(parents=True, exist_ok=True)

        # Use UUID for run_id to ensure uniqueness and consistent file naming
        run_id = str(uuid.uuid4())

        history_path = self._output_dir / f"{run_id}.json"
        screenshots_dir = self._output_dir / "screenshots" / run_id
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        return _RunContext(run_id=run_id, history_path=history_path, screenshots_dir=screenshots_dir)

    async def _run_agent_with_compatible_loop(self, agent: Any, *, max_steps: int) -> Any:
        """
        Execute the agent ensuring Windows selectors don't block subprocess support.
        """
        if sys.platform.startswith("win"):
            if self._force_threaded_run_on_windows:
                return await asyncio.to_thread(
                    self._run_agent_in_proactor_loop,
                    agent,
                    max_steps,
                    _ACTIVE_BROWSER_AGENT_RUN_ID.get(),
                )

            proactor_cls = getattr(asyncio, "ProactorEventLoop", None)
            selector_cls = getattr(asyncio, "SelectorEventLoop", None)

            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None

            should_offload = False
            if running_loop is not None:
                if proactor_cls and isinstance(running_loop, proactor_cls):
                    should_offload = False
                elif selector_cls and isinstance(running_loop, selector_cls):
                    should_offload = True
                else:
                    qualified_name = f"{running_loop.__class__.__module__}.{running_loop.__class__.__name__}"
                    if "selector" in qualified_name.lower():
                        should_offload = True

            if should_offload:
                return await asyncio.to_thread(
                    self._run_agent_in_proactor_loop,
                    agent,
                    max_steps,
                    _ACTIVE_BROWSER_AGENT_RUN_ID.get(),
                )

            try:
                return await agent.run(max_steps=max_steps)
            except NotImplementedError:
                raise BrowserAgentExecutionError(
                    "Browser agent execution failed due to event-loop incompatibility; no retry has been attempted."
                )

        return await agent.run(max_steps=max_steps)

    def _run_agent_in_proactor_loop(self, agent: Any, max_steps: int, run_id: Optional[str] = None) -> Any:
        """Run the async agent in a dedicated Proactor event loop (Windows-only)."""

        normalized_run_id = (run_id or "").strip()
        previous_run_id = getattr(_ACTIVE_BROWSER_AGENT_THREAD_STATE, "run_id", None)
        if normalized_run_id:
            _ACTIVE_BROWSER_AGENT_THREAD_STATE.run_id = normalized_run_id

        policy = asyncio.WindowsProactorEventLoopPolicy()
        loop = policy.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(agent.run(max_steps=max_steps))
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:  # pragma: no cover - best effort cleanup
                pass
            asyncio.set_event_loop(None)
            loop.close()
            if previous_run_id is None:
                if hasattr(_ACTIVE_BROWSER_AGENT_THREAD_STATE, "run_id"):
                    delattr(_ACTIVE_BROWSER_AGENT_THREAD_STATE, "run_id")
            else:
                _ACTIVE_BROWSER_AGENT_THREAD_STATE.run_id = previous_run_id

    def _save_screenshots(self, history: Any, context: _RunContext) -> List[_ScreenshotArtifact]:
        """Persist screenshots from the agent history and return saved artifacts."""

        if not self._enable_screenshots:
            return []

        artifacts: List[_ScreenshotArtifact] = []

        # Preferred source: browser-use persisted screenshot paths per step.
        screenshot_paths_attr = getattr(history, "screenshot_paths", None)
        if callable(screenshot_paths_attr):
            try:
                path_items = screenshot_paths_attr(return_none_if_not_screenshot=False)
            except TypeError:
                path_items = screenshot_paths_attr()
            except Exception as exc:
                logger.debug(f"Failed to call history.screenshot_paths(): {exc}")
                path_items = None

            if path_items:
                cleaned_paths = [Path(str(p)) for p in path_items if p]
                if self._max_screenshots > 0:
                    cleaned_paths = cleaned_paths[: self._max_screenshots]

                for index, source_path in enumerate(cleaned_paths, start=1):
                    try:
                        if not source_path.exists():
                            continue
                        image_bytes = source_path.read_bytes()
                    except Exception:
                        continue

                    extension = source_path.suffix.lower() if source_path.suffix else ".png"
                    target_path = context.screenshots_dir / f"screenshot_{index:03d}{extension}"
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    target_path.write_bytes(image_bytes)
                    artifacts.append(
                        _ScreenshotArtifact(
                            path=str(target_path),
                            base64_content=(
                                base64.b64encode(image_bytes).decode("utf-8")
                                if self._include_screenshots_in_run_response
                                else None
                            ),
                        )
                    )

                if artifacts:
                    logger.info(f"Saved {len(artifacts)} screenshots from history.screenshot_paths()")
                    return artifacts

        screenshots_attr = getattr(history, "screenshots", None)

        if callable(screenshots_attr):
            try:
                screenshots = screenshots_attr()
            except Exception as exc:
                logger.warning(f"Failed to call history.screenshots(): {exc}")
                screenshots = None
        else:
            screenshots = screenshots_attr

        if not screenshots:
            logger.debug(f"No screenshots found in history object. Type: {type(history)}, Has screenshots attr: {hasattr(history, 'screenshots')}")
            return artifacts

        # Extract rich metadata only when screenshot processing is enabled
        action_descriptions = self._extract_action_descriptions(history) if self._enable_screenshot_processing else {}
        element_bboxes = self._extract_element_bounding_boxes(history) if self._enable_screenshot_processing else {}
        
        if self._max_screenshots > 0:
            screenshots = list(screenshots)[: self._max_screenshots]

        logger.info(f"Processing {len(screenshots)} screenshots with {len(element_bboxes)} bounding boxes available")
        
        for index, screenshot_data in enumerate(screenshots, start=1):
            if not screenshot_data:
                continue

            encoded_str = self._extract_base64_data(screenshot_data)
            if not encoded_str:
                continue

            try:
                image_bytes = base64.b64decode(encoded_str)
            except Exception:
                continue

            # Apply intelligent cropping and add text overlay if PIL is available
            if PIL_AVAILABLE and self._enable_screenshot_processing:
                try:
                    # Get description and bounding box for this step (index-1 because actions are 0-indexed)
                    description = action_descriptions.get(index - 1, None)
                    bbox = element_bboxes.get(index - 1, None)
                    
                    # Crop and add text overlay (use bbox if available)
                    processed_bytes = self._process_screenshot_with_description(
                        image_bytes, 
                        description,
                        step_number=index,
                        bounding_box=bbox
                    )
                    if processed_bytes:
                        image_bytes = processed_bytes
                        if bbox:
                            logger.debug(f"Processed screenshot {index} with element-specific crop and description")
                        else:
                            logger.debug(f"Processed screenshot {index} with smart heuristic crop and description")
                except Exception as e:
                    logger.debug(f"Failed to process screenshot {index}: {e}")

            extension = self._guess_image_extension(screenshot_data)
            target_path = context.screenshots_dir / f"screenshot_{index:03d}{extension}"
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                raise BrowserAgentExecutionError(
                    f"Unable to create screenshot directory '{target_path.parent}': {exc}"
                ) from exc
            target_path.write_bytes(image_bytes)
            artifacts.append(
                _ScreenshotArtifact(
                    path=str(target_path),
                    base64_content=(
                        base64.b64encode(image_bytes).decode("utf-8")
                        if self._include_screenshots_in_run_response
                        else None
                    ),
                )
            )

        return artifacts

    def _extract_history_items(self, history: Any) -> List[Any]:
        if hasattr(history, "history") and isinstance(history.history, list):
            return history.history
        if hasattr(history, "__iter__") and not isinstance(history, (str, bytes)):
            try:
                return list(history)
            except Exception:
                return []
        return []

    def _extract_action_descriptions(self, history: Any) -> dict:
        """
        Extract action descriptions from browser-use history for each step.
        Returns a dict mapping step index to action description.
        """
        descriptions = {}
        
        try:
            # Try to get history items/steps
            history_items = self._extract_history_items(history)
            
            for idx, item in enumerate(history_items):
                description_parts = []
                
                # Extract from state/result
                if hasattr(item, 'state') and hasattr(item.state, 'result'):
                    result = item.state.result
                    if isinstance(result, str):
                        description_parts.append(result[:200])  # Limit length
                
                # Extract from model_output
                if hasattr(item, 'model_output'):
                    output = item.model_output
                    if hasattr(output, 'current_state') and hasattr(output.current_state, 'evaluation_previous_goal'):
                        eval_text = output.current_state.evaluation_previous_goal
                        if eval_text and isinstance(eval_text, str):
                            description_parts.append(eval_text[:200])
                    if hasattr(output, 'action') and output.action:
                        action_str = str(output.action)[:150]
                        description_parts.append(f"Action: {action_str}")
                
                # Combine description parts
                if description_parts:
                    descriptions[idx] = " | ".join(description_parts)
                    
        except Exception as e:
            logger.debug(f"Failed to extract action descriptions: {e}")
        
        return descriptions

    def _extract_element_bounding_boxes(self, history: Any) -> dict:
        """
        Extract element bounding boxes from browser-use history for each step.
        Returns a dict mapping step index to bounding box dict {x, y, width, height}.
        """
        bounding_boxes = {}
        
        try:
            # Get history items/steps
            history_items = self._extract_history_items(history)
            
            logger.info(f"Extracting bounding boxes from {len(history_items)} history items")
            
            for idx, item in enumerate(history_items):
                try:
                    # Extract interacted_element list from state
                    # state.interacted_element is a list[DOMInteractedElement | None]
                    if not hasattr(item, 'state') or not hasattr(item.state, 'interacted_element'):
                        logger.debug(f"Step {idx}: No state.interacted_element attribute")
                        continue
                    
                    interacted_elements = item.state.interacted_element
                    if not interacted_elements or not isinstance(interacted_elements, list):
                        logger.debug(f"Step {idx}: interacted_element is not a list or is empty")
                        continue
                    
                    # Get the first non-None interacted element (there may be multiple actions per step)
                    interacted_elem = None
                    for elem in interacted_elements:
                        if elem is not None:
                            interacted_elem = elem
                            break
                    
                    if not interacted_elem:
                        logger.debug(f"Step {idx}: All interacted_elements are None")
                        continue
                    
                    # Extract bounds from DOMInteractedElement
                    if not hasattr(interacted_elem, 'bounds') or not interacted_elem.bounds:
                        logger.debug(f"Step {idx}: interacted_element exists but has no bounds")
                        continue
                    
                    bounds = interacted_elem.bounds
                    
                    # DOMRect has x, y, width, height
                    if hasattr(bounds, 'x') and hasattr(bounds, 'y') and hasattr(bounds, 'width') and hasattr(bounds, 'height'):
                        bbox = {
                            'x': float(bounds.x),
                            'y': float(bounds.y),
                            'width': float(bounds.width),
                            'height': float(bounds.height)
                        }
                        
                        # Validate bbox has positive dimensions
                        if bbox['width'] > 0 and bbox['height'] > 0:
                            bounding_boxes[idx] = bbox
                            logger.info(f"Step {idx}: Extracted bbox x={bbox['x']:.1f}, y={bbox['y']:.1f}, w={bbox['width']:.1f}, h={bbox['height']:.1f}")
                        else:
                            logger.debug(f"Step {idx}: Invalid bbox dimensions (w={bbox['width']}, h={bbox['height']})")
                    else:
                        logger.debug(f"Step {idx}: bounds object missing required attributes")
                        
                except Exception as e:
                    logger.debug(f"Step {idx}: Failed to extract bbox: {e}")
                    continue
                        
        except Exception as e:
            logger.warning(f"Failed to extract element bounding boxes: {e}", exc_info=True)
        
        logger.info(f"Successfully extracted {len(bounding_boxes)} bounding boxes from {len(history_items)} steps")
        return bounding_boxes

    def _process_screenshot_with_description(
        self, 
        image_bytes: bytes, 
        description: Optional[str],
        step_number: int,
        bounding_box: Optional[dict] = None
    ) -> Optional[bytes]:
        """
        Process screenshot: crop intelligently and overlay text description.
        If bounding_box is provided, crop to element region; otherwise use smart heuristic.
        """
        if not PIL_AVAILABLE:
            logger.warning(f"Step {step_number}: PIL not available, skipping processing")
            return None

        try:
            # Open image
            image = Image.open(io.BytesIO(image_bytes))
            width, height = image.size
            logger.debug(f"Step {step_number}: Screenshot size: {width}x{height}")

            # Determine crop region
            if bounding_box and all(k in bounding_box for k in ['x', 'y', 'width', 'height']):
                # Element-specific crop with generous padding
                elem_x = bounding_box['x']
                elem_y = bounding_box['y']
                elem_width = bounding_box['width']
                elem_height = bounding_box['height']
                
                # Validate element is within image bounds
                if elem_x < 0 or elem_y < 0 or elem_x + elem_width > width or elem_y + elem_height > height:
                    logger.warning(f"Step {step_number}: Element bbox ({elem_x}, {elem_y}, {elem_width}, {elem_height}) outside image bounds ({width}x{height}), using fallback")
                    bounding_box = None  # Fall through to heuristic
                else:
                    # Add 30% padding on all sides
                    padding_h = int(elem_width * 0.3)
                    padding_v = int(elem_height * 0.3)
                    
                    left = max(0, int(elem_x - padding_h))
                    top = max(0, int(elem_y - padding_v))
                    right = min(width, int(elem_x + elem_width + padding_h))
                    bottom = min(height, int(elem_y + elem_height + padding_v))
                    
                    # Ensure we have a valid crop region
                    if right <= left or bottom <= top:
                        logger.warning(f"Step {step_number}: Invalid crop region (left={left}, top={top}, right={right}, bottom={bottom}), using fallback")
                        bounding_box = None  # Fall through to heuristic
                    else:
                        logger.info(f"Step {step_number}: ✓ Using element-specific crop: elem=({elem_x:.0f},{elem_y:.0f},{elem_width:.0f}x{elem_height:.0f}) → crop=({left},{top},{right},{bottom})")
            
            if not bounding_box:
                # Smart heuristic crop (fallback)
                if bounding_box is None:
                    reason = "No interacted_element for step"
                else:
                    reason = "Bounding box invalid for step"
                    
                crop_height = int(height * 0.65)
                crop_width = int(width * 0.70)
                
                left = max(0, (width - crop_width) // 2)
                top = 0
                right = left + crop_width
                bottom = top + crop_height
                
                logger.info(f"Step {step_number}: → {reason} → using fallback heuristic crop (top-middle 65%x70%)")

            cropped = image.crop((left, top, right, bottom))
            logger.info(f"Step {step_number}: Cropping completed → {cropped.size[0]}x{cropped.size[1]}")
            
            # DO NOT add text overlay - descriptions are shown in tooltips instead
            # The trajectory visualization displays clean cropped screenshots
            # Text descriptions are available via the tooltip system in the frontend
            
            # Convert back to bytes
            output = io.BytesIO()
            cropped.save(output, format="PNG")
            logger.info(f"Step {step_number}: Final screenshot generated (clean crop, no overlay)")
            return output.getvalue()

        except Exception as e:
            logger.error(f"Step {step_number}: Error processing screenshot: {e}", exc_info=True)
            return None

    def _add_text_overlay(self, image: Any, description: str, step_number: int) -> Any:
        """
        Add a text overlay banner at the top of the screenshot with the action description.
        """
        if not PIL_AVAILABLE or not ImageDraw or not ImageFont:
            return image
        
        try:
            # Create a new image with extra space at top for text
            img_width, img_height = image.size
            banner_height = 80  # Height of text banner
            
            # Create new image with banner space
            new_img = Image.new('RGB', (img_width, img_height + banner_height), color=(40, 44, 52))
            
            # Paste original image below banner
            new_img.paste(image, (0, banner_height))
            
            # Draw on the new image
            draw = ImageDraw.Draw(new_img)
            
            # Try to load a font, fall back to default if not available
            try:
                font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
                font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
            except Exception:
                try:
                    # Try alternative font paths
                    font_large = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
                    font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 13)
                except Exception:
                    # Fall back to default font
                    font_large = ImageFont.load_default()
                    font_small = ImageFont.load_default()
            
            # Draw step number
            step_text = f"Step {step_number}"
            draw.text((10, 10), step_text, fill=(97, 218, 251), font=font_large)
            
            # Draw description (truncate if too long, wrap if needed)
            max_chars = 80
            if len(description) > max_chars:
                description = description[:max_chars-3] + "..."
            
            draw.text((10, 35), description, fill=(229, 231, 235), font=font_small)
            
            # Draw a separator line
            draw.line([(0, banner_height-2), (img_width, banner_height-2)], fill=(97, 218, 251), width=2)
            
            return new_img
            
        except Exception as e:
            logger.debug(f"Failed to add text overlay: {e}")
            return image

    def _crop_screenshot_intelligently(self, image_bytes: bytes) -> Optional[bytes]:
        """
        Intelligently crop a screenshot to focus on the top-middle 60-70% of the image.
        This improves trajectory view readability by removing excessive whitespace and
        focusing on the main content area where interactive elements typically appear.
        """
        if not PIL_AVAILABLE:
            return None

        try:
            # Open image
            image = Image.open(io.BytesIO(image_bytes))
            width, height = image.size

            # Crop to top-middle 60-70% of the screenshot
            # This removes bottom whitespace and focuses on the main content area
            crop_height = int(height * 0.65)  # 65% of height
            crop_width = int(width * 0.70)    # 70% of width, centered
            
            # Center horizontally, start from top
            left = max(0, (width - crop_width) // 2)
            top = 0
            right = left + crop_width
            bottom = top + crop_height

            # Crop the image
            cropped = image.crop((left, top, right, bottom))
            
            # Convert back to bytes
            output = io.BytesIO()
            cropped.save(output, format="PNG")
            return output.getvalue()

        except Exception as e:
            logger.debug(f"Error in intelligent cropping: {e}")
            return None

    def _build_history_payload(
        self,
        *,
        request: BrowserAgentRunRequest,
        persona: BrowserAgentPersona,
        model_name: str,
        run_index: int,
        run_id: str,
        history: Any,
        screenshots: List[_ScreenshotArtifact],
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        """Construct a JSON-serialisable payload describing the run."""

        # Extract step-level descriptions for each screenshot
        action_descriptions = self._extract_action_descriptions(history)
        step_descriptions = [
            action_descriptions.get(i, None) for i in range(len(screenshots))
        ]

        return {
            "metadata": {
                "id": run_id,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "task": request.task.model_dump(exclude_none=True),
                "persona": persona.model_dump(exclude_none=True),
                "model": model_name,
                "run_index": run_index,
            },
            "summary": {
                "is_done": self._ensure_bool(summary.get("is_done")),
                "is_successful": self._ensure_bool(summary.get("is_successful")),
                "has_errors": self._ensure_bool(summary.get("has_errors")),
                "number_of_steps": self._ensure_int(summary.get("number_of_steps")),
                "total_duration_seconds": self._ensure_float(
                    summary.get("total_duration_seconds")
                ),
                "final_result": self._to_serializable(summary.get("final_result")),
            },
            "details": {
                "screenshots": [
                    self._to_relative_path(Path(artifact.path)) for artifact in screenshots
                ],
                "step_descriptions": step_descriptions,  # Add per-step descriptions
                "model_outputs": self._to_serializable(self._safe_call(history, "model_outputs")),
                "last_action": self._to_serializable(self._safe_call(history, "last_action")),
                "structured_output": self._to_serializable(
                    getattr(history, "structured_output", None)
                ),
            },
        }

    def _compose_agent_task(
        self,
        *,
        task: BrowserAgentTask,
        content: str,
    ) -> str:
        """Build the full agent prompt from the request details."""

        persona = (content or "").strip()
        url = (task.url or "").strip()
        name = (task.name or "").strip()
        description = (task.description or "").strip()

        # Build a clear, well-formatted task prompt
        # If description exists, use it as the main instruction (it's more detailed)
        # Otherwise, use the name as the instruction
        if description:
            # Description is the main instruction, name is just a label
            task_instruction = description
            if name and name.lower() not in description.lower():
                # Only add name if it's not already mentioned in description
                task_instruction = f"{name}: {description}"
        elif name:
            task_instruction = name
        else:
            task_instruction = "Complete the task"

        task_prompt = task_instruction
        if url:
            task_prompt = f"{task_prompt} (Website: {url})"

        prompt = f"Complete this task based on the following persona: {task_prompt}"
        if persona:
            prompt = f"{prompt}\nPersona: {persona}"
        return prompt

    def _extract_base64_data(self, screenshot_data: Any) -> str:
        """Best-effort extraction of base64 payload from screenshot blobs."""

        if isinstance(screenshot_data, (bytes, bytearray)):
            return base64.b64encode(screenshot_data).decode("utf-8")

        if isinstance(screenshot_data, str):
            header, _, encoded = screenshot_data.partition(",")
            return encoded or screenshot_data

        if isinstance(screenshot_data, dict):
            for key in ("data", "content", "image"):
                value = screenshot_data.get(key)
                if isinstance(value, str):
                    return value

        return str(screenshot_data)

    def _guess_image_extension(self, screenshot_data: Any) -> str:
        """Infer image extension from data URI headers if available."""

        if isinstance(screenshot_data, str):
            header, _, _ = screenshot_data.partition(",")
            header_lower = header.lower()
            if "jpeg" in header_lower or "jpg" in header_lower:
                return ".jpg"
            if "webp" in header_lower:
                return ".webp"
        return ".png"

    def _to_serializable(self, obj: Any) -> Any:
        """Convert nested structures into JSON-serialisable primitives."""

        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        if isinstance(obj, (list, tuple, set)):
            return [self._to_serializable(item) for item in obj]
        if isinstance(obj, dict):
            return {str(key): self._to_serializable(value) for key, value in obj.items()}
        if hasattr(obj, "model_dump"):
            try:
                return self._to_serializable(obj.model_dump())
            except Exception:  # pragma: no cover - best effort fallback
                pass
        if hasattr(obj, "dict"):
            try:
                return self._to_serializable(obj.dict())
            except Exception:  # pragma: no cover - best effort fallback
                pass
        if hasattr(obj, "__dict__"):
            return {
                key: self._to_serializable(value)
                for key, value in vars(obj).items()
                if not key.startswith("_")
            }
        return str(obj)

    def _safe_call(self, obj: Any, attr: str) -> Any:
        """Call an attribute if it is callable, returning None otherwise."""

        target = getattr(obj, attr, None)
        if callable(target):
            try:
                return target()
            except Exception:  # pragma: no cover - ignore runtime issues
                return None
        return target

    def _to_relative_path(self, path: Path) -> str:
        """Return a path relative to the current working directory when possible."""

        try:
            return str(path.resolve().relative_to(Path(os.getcwd()).resolve()))
        except ValueError:
            return str(path.resolve())

    def _ensure_bool(self, value: Any) -> bool:
        """Coerce arbitrary values into a boolean with a safe default."""

        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "y", "on"}:
                return True
            if normalized in {"false", "0", "no", "n", "off", ""}:
                return False
        if value is None:
            return False
        try:
            return bool(value)
        except Exception:
            return False

    def _ensure_int(self, value: Any) -> int:
        """Coerce values to an integer with zero as fallback."""

        if isinstance(value, int):
            return value
        if value is None:
            return 0
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _ensure_float(self, value: Any) -> float:
        """Coerce values to a float with 0.0 as fallback."""

        if isinstance(value, float):
            return value
        if isinstance(value, int):
            return float(value)
        if value is None:
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
