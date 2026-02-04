"""Schema definitions for browser agent execution endpoints."""
from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field, ConfigDict


class BrowserAgentTask(BaseModel):
    """Describes a browser automation task for the agent to complete."""

    name: str = Field(..., description="Human readable task name.")
    description: str = Field(default="", description="Detailed task description explaining what the agent should do.")
    url: str = Field(..., description="Target website or entry point for the agent.")

    model_config = ConfigDict(extra="forbid")


class BrowserAgentPersona(BaseModel):
    """Represents a persona variant applied to the browser agent."""

    value: str = Field(..., description="Identifier or label for the persona variant.")
    content: str = Field(..., description="Full persona prompt injected ahead of the task description.")

    model_config = ConfigDict(extra="forbid")


class BrowserAgentRunRequest(BaseModel):
    """Incoming request payload for one or more browser agent runs."""

    task: BrowserAgentTask
    personas: List[BrowserAgentPersona] = Field(
        ...,
        alias="persona",
        min_length=1,
        description="Collection of persona variants to apply when constructing prompts.",
    )
    models: List[str] = Field(
        ...,
        alias="model",
        min_length=1,
        description="One or more LLM model identifiers to execute against the task.",
    )
    run_times: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Number of sequential iterations per persona/model combination.",
    )

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class BrowserAgentScreenshot(BaseModel):
    """Screenshot artifact captured during a browser agent run."""

    path: str = Field(..., description="Relative path to the persisted screenshot on disk.")
    content_base64: str = Field(
        ..., description="Screenshot image encoded as a base64 string without data URI headers."
    )

    model_config = ConfigDict(extra="forbid")


class BrowserAgentRunResult(BaseModel):
    """Summarised result for a single persona/model browser agent run."""

    model: str = Field(..., description="LLM model identifier executed for this run.")
    run_index: int = Field(
        ...,
        description="1-based iteration counter for this persona/model combination.",
    )
    is_done: bool
    is_successful: bool
    has_errors: bool
    number_of_steps: int
    total_duration_seconds: float
    final_result: Any
    history_path: str
    history_payload: Dict[str, Any] = Field(
        ..., description="Structured history payload that was also written to the history file."
    )
    screenshot_paths: List[str]
    screenshots: List[BrowserAgentScreenshot] = Field(
        default_factory=list,
        description="Inline screenshot artifacts for immediate consumption by API clients.",
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Metadata including task name, url, and timestamp_utc."
    )


class BrowserAgentRunResponse(BaseModel):
    """Aggregated response containing all requested runs."""

    results: List[BrowserAgentRunResult]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "results": [
                    {
                        "persona": {
                            "value": "Frugality",
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
                            "screenshots": ["base64string"],
                            "screenshot_paths": ["path/to/screenshot.png"],
                            "step_descriptions": ["Opened browser", "Navigated to shop"],
                            "model_outputs": {},
                            "last_action": {"type": "click", "selector": "#buy-btn"}
                        },
                        "screenshot_paths": ["path/to/screenshot.png"],
                        "screenshots": [
                            {
                                "path": "path/to/screenshot.png",
                                "content_base64": "base64string"
                            }
                        ],
                        "metadata": {
                            "task_name": "Buy milk",
                            "url": "http://example.com",
                            "timestamp_utc": "2025-12-18T20:05:26"
                        }
                    }
                ]
            }
        }
    )
