"""Schema definitions for serving cached history logs via API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict


class HistoryLogDetails(BaseModel):
    """Detailed payload captured for a single agent run."""

    screenshots: List[Optional[str]] = Field(
        default_factory=list,
        description=(
            "Ordered base64-encoded screenshot payloads without data URI prefixes. "
            "Entries may be null when the original file could not be located."
        ),
    )
    screenshot_paths: List[str] = Field(
        default_factory=list,
        description="Relative paths to the screenshots as recorded in the history file.",
    )
    missing_screenshots: List[str] = Field(
        default_factory=list,
        description="List of screenshot paths that were referenced but not found on disk.",
    )
    model_outputs: Any = Field(default=None, description="Raw model outputs from the agent run.")
    last_action: Any = Field(default=None, description="Last recorded action for the agent run.")
    structured_output: Any = Field(
        default=None, description="Structured output emitted by the agent, when available."
    )
    step_descriptions: List[Optional[str]] = Field(
        default_factory=list,
        description="Description of each step performed by the agent."
    )

    model_config = ConfigDict(extra="allow")


class HistoryLogTask(BaseModel):
    name: str
    url: str


class HistoryLogMetadata(BaseModel):
    id: str
    task: HistoryLogTask
    timestamp_utc: str
    value: str
    persona: str


class HistoryLogHistoryPayload(BaseModel):
    screenshots: List[Optional[str]]
    screenshot_paths: List[str]
    step_descriptions: List[str]
    model_outputs: Any
    last_action: Any


class HistoryLogEntry(BaseModel):
    model: str
    run_index: int
    is_done: bool
    is_successful: bool
    has_errors: bool
    number_of_steps: int
    total_duration_seconds: float
    final_result: Any
    history_path: str
    history_payload: HistoryLogHistoryPayload
    metadata: HistoryLogMetadata


class HistoryLogPayload(BaseModel):
    """High-level representation of a cached agent execution history."""

    filename: str = Field(..., description="Originating JSON filename within the history cache directory.")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata section copied from the stored history payload.",
    )
    summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Run summary section copied from the stored history payload.",
    )
    details: HistoryLogDetails

    model_config = ConfigDict(extra="allow")


class HistoryLogsListResponse(BaseModel):
    """Response payload for listing all cached history logs."""

    results: List[HistoryLogEntry] = Field(
        default_factory=list,
        description="List of history log entries with persona, model, run results, and metadata.",
    )

    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "example": {
                "results": [
                    {
                        "persona": {
                            "content": "You are a frugal shopper..."
                        },
                        "model": "gpt-4",
                        "run_index": 1,
                        "is_done": True,
                        "is_successful": True,
                        "has_errors": False,
                        "number_of_steps": 5,
                        "total_duration_seconds": 12.5,
                        "final_result": "Bought milk for $2.99",
                        "history_path": "buy_milk_Frugality_20251218_200526_run66.json",
                        "history_payload": {
                            "screenshots": ["base64string..."],
                            "screenshot_paths": ["screenshots/run1/step1.png"],
                            "step_descriptions": ["Opened browser", "Navigated to shop"],
                            "model_outputs": {},
                            "last_action": {"type": "click", "selector": "#buy-btn"}
                        },
                        "metadata": {
                            "id": "buy_milk_Frugality_20251218_200526_run66",
                            "task": {
                                "name": "Buy milk",
                                "url": "http://example.com"
                            },
                            "timestamp_utc": "2025-12-18T20:05:26",
                            "value": "Frugality",
                            "persona": "You are a frugal shopper..."
                        }
                    }
                ]
            }
        }
    )
