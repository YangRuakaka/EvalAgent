"""API routes exposing cached history logs."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..core.normalizers import to_bool, to_float, to_int, to_str, to_str_list
from ..schemas.history_logs import HistoryLogPayload, HistoryLogsListResponse
from ..services.history_logs_reader import HistoryLogsService, HistoryLogsServiceError

router = APIRouter(prefix="/history-logs", tags=["history-logs"])
_service = HistoryLogsService()


@router.get(
    "",
    response_model=HistoryLogsListResponse,
    summary="List cached history log payloads (custom format)",
)
async def list_history_logs() -> HistoryLogsListResponse:
    """Return all cached history logs in the new custom format for frontend consumption."""
    try:
        logs = _service.list_logs()
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
