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
        def as_str(value, default: str = "") -> str:
            if value is None:
                return default
            return str(value)

        def as_int(value, default: int = 0) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        def as_float(value, default: float = 0.0) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        def as_bool(value, default: bool = False) -> bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"true", "1", "yes", "y", "on"}:
                    return True
                if lowered in {"false", "0", "no", "n", "off"}:
                    return False
                return default
            if isinstance(value, (int, float)):
                return bool(value)
            return default

        def as_str_list(value) -> list[str]:
            if value is None:
                return []
            if not isinstance(value, list):
                return [as_str(value)]
            return [as_str(item) for item in value if item is not None]

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
                "id": as_str(run_id, "unknown"),
                "task": {
                    "name": as_str(task.get("name", "")),
                    "url": as_str(task.get("url", ""))
                },
                "timestamp_utc": as_str(log.metadata.get("timestamp_utc", "")),
                "value": as_str(log.metadata.get("value", "")),
                "persona": as_str(persona_content)
            }

            details = log.details.model_dump() if hasattr(log.details, "model_dump") else log.details.dict()
            history_payload = {
                "screenshots": details.get("screenshots", []),
                "screenshot_paths": details.get("screenshot_paths", []),
                "step_descriptions": as_str_list(details.get("step_descriptions", [])),
                "model_outputs": details.get("model_outputs", None),
                "last_action": details.get("last_action", None)
            }

            result = {
                "model": as_str(log.metadata.get("model", "")),
                "run_index": as_int(log.metadata.get("run_index", 0)),
                "is_done": as_bool(log.summary.get("is_done", False)),
                "is_successful": as_bool(log.summary.get("is_successful", False)),
                "has_errors": as_bool(log.summary.get("has_errors", False)),
                "number_of_steps": as_int(log.summary.get("number_of_steps", 0)),
                "total_duration_seconds": as_float(log.summary.get("total_duration_seconds", 0)),
                "final_result": log.summary.get("final_result", ""),
                "history_path": as_str(log.filename),
                "history_payload": history_payload,
                "metadata": metadata
            }
            results.append(result)
        return HistoryLogsListResponse(results=results)
    except HistoryLogsServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
