"""API routes for executing browser-use agent tasks."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException

from ..schemas.browser_agent import (
    BrowserAgentRunRequest,
    BrowserAgentRunStartResponse,
    BrowserAgentStopRequest,
    BrowserAgentStopResponse,
)
from ..services.browser_agent_runner import (
    BrowserAgentBusyError,
    BrowserAgentService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/browser-agent", tags=["browser-agent"])
_service = BrowserAgentService()


@router.post(
    "/run",
    response_model=BrowserAgentRunStartResponse,
    summary="Start a browser-use automation task (non-blocking)",
)
async def run_browser_agent(request: BrowserAgentRunRequest) -> BrowserAgentRunStartResponse:
    """Start the browser agent in the background.

    Returns immediately with a run_id. Poll ``/status/{run_id}`` for results.
    """
    run_id = (request.run_id or str(uuid.uuid4())).strip()
    total_tasks = len(request.personas) * len(request.models) * request.run_times

    logger.info(
        "Browser-agent run request | run_id=%s task=%s url=%s personas=%d models=%d run_times=%d total_tasks=%d",
        run_id,
        request.task.name,
        request.task.url,
        len(request.personas),
        len(request.models),
        request.run_times,
        total_tasks,
    )

    try:
        _service.start_run(request, run_id=run_id)
    except BrowserAgentBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return BrowserAgentRunStartResponse(
        run_id=run_id,
        status="running",
        total_tasks=total_tasks,
    )


@router.get(
    "/status/{run_id}",
    summary="Poll for browser agent run status and results",
)
async def get_run_status(run_id: str):
    """Return the current status of a browser agent run.

    Returns results when ``status`` is ``completed``.
    """
    status = _service.get_run_status(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return status


@router.post(
    "/stop",
    response_model=BrowserAgentStopResponse,
    summary="Stop an in-flight browser-use automation task",
)
async def stop_browser_agent(request: BrowserAgentStopRequest) -> BrowserAgentStopResponse:
    """Stop an active browser agent run by run_id."""
    stopped = await _service.stop_run(request.run_id)
    message = (
        "Stop signal sent to active browser-agent run."
        if stopped
        else "No active browser-agent run found for this run_id."
    )
    logger.info("Browser-agent stop requested | run_id=%s stopped=%s", request.run_id, stopped)
    return BrowserAgentStopResponse(run_id=request.run_id, stopped=stopped, message=message)
