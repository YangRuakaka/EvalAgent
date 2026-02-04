"""API routes exposing cached history logs."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

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

            metadata = {
                "id": run_id,
                "task": {
                    "name": task.get("name", ""),
                    "url": task.get("url", "")
                },
                "timestamp_utc": log.metadata.get("timestamp_utc", ""),
                "value": log.metadata.get("value", ""),
                "persona": persona_content
            }

            details = log.details.model_dump() if hasattr(log.details, "model_dump") else log.details.dict()
            history_payload = {
                "screenshots": details.get("screenshots", []),
                "screenshot_paths": details.get("screenshot_paths", []),
                "step_descriptions": details.get("step_descriptions", []),  # Include per-step descriptions
                "model_outputs": details.get("model_outputs", None),
                "last_action": details.get("last_action", None)
            }

            result = {
                "model": log.metadata.get("model", ""),
                "run_index": log.metadata.get("run_index", 0),
                "is_done": log.summary.get("is_done", False),
                "is_successful": log.summary.get("is_successful", False),
                "has_errors": log.summary.get("has_errors", False),
                "number_of_steps": log.summary.get("number_of_steps", 0),
                "total_duration_seconds": log.summary.get("total_duration_seconds", 0),
                "final_result": log.summary.get("final_result", ""),
                "history_path": log.filename,
                "history_payload": history_payload,
                "metadata": metadata
            }
            results.append(result)
        return HistoryLogsListResponse(results=results)
    except HistoryLogsServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
