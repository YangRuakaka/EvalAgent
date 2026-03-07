"""API routes for executing browser-use agent tasks."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..core.config import get_settings
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
settings = get_settings()

router = APIRouter(prefix="/browser-agent", tags=["browser-agent"])
_service = BrowserAgentService()
_worker_queue: asyncio.Queue[tuple[str, BrowserAgentRunRequest, int]] | None = None
_worker_tasks: list[asyncio.Task] = []
_worker_lock: asyncio.Lock | None = None


async def _worker_loop(worker_name: str) -> None:
    """Consume queued browser-agent runs and execute them with bounded worker concurrency."""
    global _worker_queue

    if _worker_queue is None:
        return

    while True:
        run_id, request, total_tasks = await _worker_queue.get()
        try:
            status = _service.get_run_status(run_id)
            if status and status.get("status") == "cancelled":
                continue

            _service.mark_run_running(run_id=run_id, total_tasks=total_tasks)
            _service.start_run(request, run_id=run_id)

            current_task = _service.get_background_run_task(run_id)
            if current_task is not None:
                await current_task
        except BrowserAgentBusyError:
            logger.warning("Worker %s skipped duplicate running run_id=%s", worker_name, run_id)
            _service.mark_run_failed(run_id=run_id, error="This run_id is already in progress.")
        except asyncio.CancelledError:
            logger.info("Browser-agent worker loop cancelled | worker=%s", worker_name)
            raise
        except Exception as exc:
            logger.exception("Worker failed to execute run | worker=%s run_id=%s", worker_name, run_id)
            _service.mark_run_failed(run_id=run_id, error=str(exc))
        finally:
            _worker_queue.task_done()


async def _ensure_worker_started() -> None:
    """Start the in-process worker task once per process."""
    global _worker_queue, _worker_tasks, _worker_lock

    if _worker_lock is None:
        _worker_lock = asyncio.Lock()

    async with _worker_lock:
        if _worker_queue is None:
            _worker_queue = asyncio.Queue()

        max_parallel_runs = max(1, int(getattr(settings, "BROWSER_AGENT_MAX_PARALLEL_RUNS", 1)))
        alive_workers = [task for task in _worker_tasks if not task.done()]

        if len(alive_workers) < max_parallel_runs:
            for worker_index in range(len(alive_workers), max_parallel_runs):
                worker_name = f"browser-agent-worker-{worker_index + 1}"
                alive_workers.append(asyncio.create_task(_worker_loop(worker_name)))
            _worker_tasks = alive_workers


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

    await _ensure_worker_started()

    if _worker_queue is None:
        raise HTTPException(status_code=500, detail="Worker queue is not initialized")

    _service.register_queued_run(run_id=run_id, total_tasks=total_tasks)
    await _worker_queue.put((run_id, request, total_tasks))

    return BrowserAgentRunStartResponse(
        run_id=run_id,
        status="queued",
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


@router.get(
    "/events/{run_id}",
    summary="Stream browser agent status updates via SSE",
)
async def stream_run_events(run_id: str, request: Request):
    """Stream status updates for a browser-agent run using Server-Sent Events."""
    async def event_generator():
        def _compute_overlap(previous: list[str], current: list[str]) -> int:
            max_overlap = min(len(previous), len(current))
            for overlap in range(max_overlap, 0, -1):
                if previous[-overlap:] == current[:overlap]:
                    return overlap
            return 0

        last_payload = None
        last_logs: list[str] = []
        missing_count = 0
        poll_interval_seconds = max(
            0.1,
            float(getattr(settings, "BROWSER_AGENT_EVENTS_POLL_INTERVAL_SECONDS", 0.25)),
        )
        max_missing_before_error = max(30, int(120 / poll_interval_seconds))
        while True:
            if await request.is_disconnected():
                break

            current_status = _service.get_run_status(run_id)
            if current_status is None:
                missing_count += 1
                if missing_count >= max_missing_before_error:
                    yield "event: error\ndata: {\"error\": \"Run not found\"}\n\n"
                    break
                yield "event: ping\ndata: {}\n\n"
                await asyncio.sleep(poll_interval_seconds)
                continue

            missing_count = 0

            current_logs_raw = current_status.get("logs")
            current_logs = [str(item) for item in current_logs_raw] if isinstance(current_logs_raw, list) else []
            overlap = _compute_overlap(last_logs, current_logs) if last_logs else 0
            new_logs = current_logs if not last_logs else current_logs[overlap:]

            for offset, line in enumerate(new_logs):
                log_index = overlap + offset
                log_payload = json.dumps(
                    {
                        "run_id": run_id,
                        "index": log_index,
                        "line": line,
                    },
                    ensure_ascii=False,
                )
                yield f"event: log\ndata: {log_payload}\n\n"

            last_logs = current_logs

            payload = json.dumps(current_status, ensure_ascii=False)
            if payload != last_payload:
                yield f"event: status\ndata: {payload}\n\n"
                last_payload = payload
            else:
                yield "event: ping\ndata: {}\n\n"

            if current_status.get("status") in {"completed", "failed", "cancelled"}:
                yield f"event: end\ndata: {payload}\n\n"
                break

            await asyncio.sleep(poll_interval_seconds)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
