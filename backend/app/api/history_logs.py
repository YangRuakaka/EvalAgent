"""API routes exposing cached history logs."""
from __future__ import annotations

import mimetypes

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from ..core.config import settings
from ..core.normalizers import to_bool, to_float, to_int, to_str, to_str_list
from ..schemas.history_logs import HistoryLogsListResponse
from ..services.history_logs_reader import HistoryLogsService, HistoryLogsServiceError

router = APIRouter(prefix="/history-logs", tags=["history-logs"])
_service = HistoryLogsService()


def _build_screenshot_url_prefix(request: Request) -> str:
    configured_base = (settings.PUBLIC_API_BASE_URL or "").strip()
    if configured_base:
        normalized_base = configured_base.rstrip("/")
        if normalized_base.endswith(settings.API_V1_PREFIX):
            return f"{normalized_base}/history-logs/screenshot"
        return f"{normalized_base}{settings.API_V1_PREFIX}/history-logs/screenshot"

    return str(request.url_for("get_history_log_screenshot"))


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
        "inline",
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
        return FileResponse(
            path=screenshot_file,
            media_type=media_type or "application/octet-stream",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
