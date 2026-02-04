"""API routes for executing browser-use agent tasks."""
from __future__ import annotations

import logging
import base64
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..schemas.browser_agent import BrowserAgentRunRequest, BrowserAgentRunResponse
from ..services.browser_agent_runner import (
    BrowserAgentExecutionError,
    BrowserAgentService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/browser-agent", tags=["browser-agent"])
_service = BrowserAgentService()


@router.post(
    "/run",
    response_model=BrowserAgentRunResponse,
    summary="Execute a browser-use automation task",
)
async def run_browser_agent(request: BrowserAgentRunRequest) -> BrowserAgentRunResponse:
    """Run the browser agent with the supplied parameters and persist outputs."""

    logger.info(
        "Browser-agent run request received | task_name=%s url=%s personas=%d models=%d run_times=%d",
        request.task.name,
        request.task.url,
        len(request.personas),
        len(request.models),
        request.run_times,
    )

    from datetime import datetime, timezone
    try:
        results = await _service.run(request)
    except BrowserAgentExecutionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Add metadata field
    now_utc = datetime.now(timezone.utc).isoformat()
    new_results = []
    for result in results:
        # Normalize service history payload (service places actual content under "details")
        raw_payload = result.history_payload if isinstance(result.history_payload, dict) else {}

        # Capture persona info from existing result.metadata
        existing_metadata = result.metadata if isinstance(result.metadata, dict) else {}
        persona_content = existing_metadata.get("persona")
        persona_value = existing_metadata.get("value")

        # Set metadata
        result.metadata = {
            "id": raw_payload.get("metadata", {}).get("id"),
            "task": {
                "name": request.task.name,
                "url": request.task.url
            },
            "timestamp_utc": now_utc,
            "value": persona_value,
            "persona": persona_content
        }

        details = raw_payload.get("details", raw_payload)

        # screenshots in details are usually paths; prefer result.screenshot_paths for accurate values
        history_payload = {
            "screenshots": details.get("screenshots", []) or [p for p in getattr(result, "screenshot_paths", [])],
            "screenshot_paths": getattr(result, "screenshot_paths", []) or details.get("screenshots", []),
            "step_descriptions": details.get("step_descriptions", []),  # Include per-step descriptions
            "model_outputs": details.get("model_outputs", None),
            "last_action": details.get("last_action", None),
            # keep summary/metadata from the persisted payload when available
            "summary": raw_payload.get("summary"),
            "metadata": raw_payload.get("metadata"),
        }

        # Build inline base64 screenshots list from available paths
        inline_screenshots: list[str] = []
        candidate_paths = history_payload.get("screenshot_paths") or history_payload.get("screenshots") or []
        for rel_path in candidate_paths:
            try:
                rel_path_str = str(rel_path)
                file_path = Path(rel_path_str)
                # try a couple of sensible fallbacks if the path isn't already absolute
                if not file_path.exists():
                    file_path = Path.cwd() / rel_path_str
                if not file_path.exists() and hasattr(result, "history_path"):
                    # try relative to history file directory
                    try:
                        file_path = Path(result.history_path).resolve().parent / rel_path_str
                    except Exception:
                        pass

                if not file_path.exists():
                    logger.warning("Screenshot file not found, skipping: %s", rel_path_str)
                    continue

                with file_path.open("rb") as fh:
                    b = fh.read()
                b64 = base64.b64encode(b).decode("ascii")
                # Only include the base64 string inside history_payload["screenshots"] as requested
                inline_screenshots.append(b64)
            except Exception as exc:
                logger.exception("Failed to read/encode screenshot %s: %s", rel_path, exc)
                continue

        # Put the inline base64 images into the history payload (replace paths)
        history_payload["screenshots"] = inline_screenshots

        # Build new result structure
        new_result = {
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
            "screenshots": [
                {
                    "path": screenshot.path,
                    "content_base64": screenshot.content_base64,
                }
                for screenshot in getattr(result, "screenshots", [])
            ],
            "metadata": result.metadata
        }
        new_results.append(new_result)

    response = BrowserAgentRunResponse(results=new_results)
    logger.info(
        "Browser-agent run response ready | task_name=%s total_results=%d",
        request.task.name,
        len(new_results),
    )
    return response
