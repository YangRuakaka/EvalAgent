"""API routes exposing cached history logs."""
from __future__ import annotations

import logging
import mimetypes
import re

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from ..core.config import settings
from ..core.normalizers import to_bool, to_float, to_int, to_str, to_str_list
from ..core.storage_paths import normalize_cache_dataset
from ..schemas.history_logs import HistoryLogsListResponse
from ..services.history_logs_reader import HistoryLogsService, HistoryLogsServiceError
from ..services.screenshot_hash_backfill import run_backfill

router = APIRouter(prefix="/history-logs", tags=["history-logs"])
_service = HistoryLogsService()
logger = logging.getLogger(__name__)


def _resolve_request_scheme(request: Request) -> str:
    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").strip().lower()
    if forwarded_proto:
        first = forwarded_proto.split(",", maxsplit=1)[0].strip()
        if first in {"http", "https"}:
            return first

    scheme = (request.url.scheme or "").strip().lower()
    return scheme if scheme in {"http", "https"} else "https"


def _force_url_scheme(url: str, scheme: str) -> str:
    if scheme not in {"http", "https"}:
        return url

    if url.startswith("http://"):
        return f"{scheme}://{url[len('http://') :]}"
    if url.startswith("https://"):
        return f"{scheme}://{url[len('https://') :]}"
    return url


def _origin_is_allowed(origin: str) -> bool:
    candidate = str(origin or "").strip()
    if not candidate:
        return False

    allow_origins = [str(item).strip() for item in (settings.CORS_ALLOW_ORIGINS or []) if str(item).strip()]
    if candidate in allow_origins:
        return True

    for pattern in (settings.CORS_ALLOW_ORIGIN_REGEX, settings.CORS_ALLOW_LOCALHOST_REGEX):
        raw_pattern = str(pattern or "").strip()
        if not raw_pattern:
            continue
        try:
            if re.fullmatch(raw_pattern, candidate):
                return True
        except re.error:
            continue

    return False


def _build_cors_headers(request: Request) -> dict[str, str]:
    origin = (request.headers.get("origin") or "").strip()
    if not _origin_is_allowed(origin):
        return {"Vary": "Origin"}

    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
        "Vary": "Origin",
    }


def _parse_preload_datasets(raw_value: str) -> list[str]:
    candidates = [item.strip() for item in str(raw_value or "").split(",") if item.strip()]
    if not candidates:
        candidates = ["data1"]

    normalized: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        try:
            dataset_key = normalize_cache_dataset(item)
        except ValueError:
            continue

        if dataset_key in seen:
            continue

        seen.add(dataset_key)
        normalized.append(dataset_key)

    return normalized or ["data1"]


def preload_history_logs_cache() -> dict[str, object]:
    preload_mode = str(settings.HISTORY_LOGS_PRELOAD_SCREENSHOT_MODE or "proxy").strip().lower()
    if preload_mode not in {"inline", "proxy", "none"}:
        preload_mode = "proxy"

    datasets = _parse_preload_datasets(settings.HISTORY_LOGS_PRELOAD_DATASETS)
    url_prefix = f"{settings.API_V1_PREFIX}/history-logs/screenshot"

    backfill_summary: dict[str, object] | None = None
    if settings.HISTORY_LOGS_PRELOAD_WRITE_MISSING_HASHES:
        try:
            backfill_result = run_backfill(
                write_changes=True,
                datasets=datasets,
                overwrite_existing=False,
                verbose=False,
            )
            backfill_summary = dict(backfill_result.get("summary") or {})
        except Exception as exc:  # pragma: no cover - startup edge case
            logger.exception("history logs hash backfill failed before preload")
            backfill_summary = {"ok": False, "error": str(exc)}

    warmed_counts: dict[str, int] = {}
    errors: dict[str, str] = {}
    for dataset_key in datasets:
        try:
            logs = _service.list_logs(
                dataset=dataset_key,
                screenshot_mode=preload_mode,
                screenshot_url_prefix=url_prefix,
            )
            warmed_counts[dataset_key] = len(logs)
        except Exception as exc:  # pragma: no cover - startup edge case
            errors[dataset_key] = str(exc)

    result: dict[str, object] = {
        "mode": preload_mode,
        "datasets": datasets,
        "warmed_counts": warmed_counts,
        "errors": errors,
    }
    if backfill_summary is not None:
        result["backfill"] = backfill_summary

    return result


def _build_screenshot_url_prefix(request: Request) -> str:
    configured_base = (settings.PUBLIC_API_BASE_URL or "").strip()
    request_scheme = _resolve_request_scheme(request)

    if configured_base:
        normalized_base = _force_url_scheme(configured_base.rstrip("/"), request_scheme)
        if normalized_base.endswith(settings.API_V1_PREFIX):
            return f"{normalized_base}/history-logs/screenshot"
        return f"{normalized_base}{settings.API_V1_PREFIX}/history-logs/screenshot"

    generated = str(request.url_for("get_history_log_screenshot"))
    return _force_url_scheme(generated, request_scheme)


@router.get(
    "",
    response_model=HistoryLogsListResponse,
    summary="List cached history log payloads (custom format)",
)
async def list_history_logs(
    request: Request,
    dataset: str = Query(
        "data1",
        description="Select cache dataset bucket: data1, data2, or data3.",
        pattern=r"^(data[123]|[123])$",
    ),
    data_source: str | None = Query(
        None,
        alias="data_source",
        description="Backward-compatible alias for dataset (data1, data2, data3).",
        pattern=r"^(data[123]|[123])$",
    ),
    screenshot_mode: str = Query(
        "proxy",
        description="Screenshot payload mode: inline (base64 data URI), proxy (URL), or none.",
        pattern=r"^(inline|proxy|none)$",
    ),
) -> HistoryLogsListResponse:
    """Return all cached history logs in the new custom format for frontend consumption."""
    try:
        selected_dataset = data_source if data_source else dataset
        screenshot_url_prefix = _build_screenshot_url_prefix(request)
        logs = _service.list_logs(
            dataset=selected_dataset,
            screenshot_mode=screenshot_mode,
            screenshot_url_prefix=screenshot_url_prefix,
        )
        results = []
        for log in logs:
            raw_persona = log.metadata.get("persona", "")
            persona_content = ""
            if isinstance(raw_persona, dict):
                persona_content = raw_persona.get("content", "")
            else:
                persona_content = str(raw_persona)

            task = log.metadata.get("task", {})
            if not isinstance(task, dict):
                task = {"name": str(task), "url": ""}
            
            # Determine ID
            run_id = log.metadata.get("id")
            if not run_id and log.filename:
                # Fallback to filename without extension for legacy logs
                run_id = log.filename.rsplit('.', 1)[0]
            if not run_id:
                run_id = "unknown"

            metadata = {
                "id": to_str(run_id, "unknown"),
                "task": {
                    "name": to_str(task.get("name", "")),
                    "url": to_str(task.get("url", ""))
                },
                "timestamp_utc": to_str(log.metadata.get("timestamp_utc", "")),
                "value": to_str(log.metadata.get("value", "")),
                "persona": to_str(persona_content)
            }

            details = log.details.model_dump() if hasattr(log.details, "model_dump") else log.details.dict()
            history_payload = {
                "screenshots": details.get("screenshots", []),
                "screenshot_paths": details.get("screenshot_paths", []),
                "screenshot_hashes": details.get("screenshot_hashes", []),
                "step_descriptions": to_str_list(details.get("step_descriptions", [])),
                "model_outputs": details.get("model_outputs", None),
                "last_action": details.get("last_action", None)
            }

            result = {
                "model": to_str(log.metadata.get("model", "")),
                "run_index": to_int(log.metadata.get("run_index", 0)),
                "is_done": to_bool(log.summary.get("is_done", False)),
                "is_successful": to_bool(log.summary.get("is_successful", False)),
                "has_errors": to_bool(log.summary.get("has_errors", False)),
                "number_of_steps": to_int(log.summary.get("number_of_steps", 0)),
                "total_duration_seconds": to_float(log.summary.get("total_duration_seconds", 0)),
                "final_result": log.summary.get("final_result", ""),
                "history_path": to_str(log.filename),
                "history_payload": history_payload,
                "metadata": metadata
            }
            results.append(result)
        return HistoryLogsListResponse(results=results)
    except HistoryLogsServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/screenshot",
    summary="Serve cached screenshot file",
)
async def get_history_log_screenshot(
    request: Request,
    path: str = Query(..., description="Screenshot path from history payload."),
    dataset: str = Query(
        "data1",
        description="Select cache dataset bucket: data1, data2, or data3.",
        pattern=r"^(data[123]|[123])$",
    ),
    data_source: str | None = Query(
        None,
        alias="data_source",
        description="Backward-compatible alias for dataset (data1, data2, data3).",
        pattern=r"^(data[123]|[123])$",
    ),
):
    try:
        selected_dataset = data_source if data_source else dataset
        screenshot_file = _service.resolve_screenshot_file(path_str=path, dataset=selected_dataset)
        if not screenshot_file:
            raise HTTPException(status_code=404, detail="Screenshot not found")

        media_type, _ = mimetypes.guess_type(str(screenshot_file))
        response_headers = {
            "Cache-Control": "public, max-age=86400",
            **_build_cors_headers(request),
        }
        return FileResponse(
            path=screenshot_file,
            media_type=media_type or "application/octet-stream",
            headers=response_headers,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
