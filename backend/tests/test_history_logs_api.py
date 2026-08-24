import asyncio
from types import SimpleNamespace

from app.api import history_logs


class _Details:
    def model_dump(self):
        return {
            "screenshots": [],
            "screenshot_paths": [],
            "screenshot_hashes": [],
            "step_descriptions": [],
            "model_outputs": [],
            "last_action": None,
        }


def test_list_history_logs_uses_nested_persona_value(monkeypatch):
    log = SimpleNamespace(
        metadata={
            "id": "run-1",
            "task": {"name": "Task", "url": "http://example.test", "description": ""},
            "timestamp_utc": "2026-08-24T00:00:00+00:00",
            "persona": {"value": "Innovation", "content": "A persona"},
            "model": "test-model",
            "run_index": 1,
        },
        summary={
            "is_done": True,
            "is_successful": True,
            "has_errors": False,
            "number_of_steps": 6,
            "total_duration_seconds": 1.0,
            "final_result": "Done",
        },
        details=_Details(),
        filename="run-1.json",
    )
    monkeypatch.setattr(history_logs._service, "list_logs", lambda **_kwargs: [log])
    request = SimpleNamespace(
        headers={},
        url=SimpleNamespace(scheme="http"),
        url_for=lambda _name: "http://example.test/api/v1/history-logs/screenshot",
    )

    response = asyncio.run(
        history_logs.list_history_logs(
            request,
            dataset="data1",
            data_source=None,
            screenshot_mode="none",
        )
    )

    assert response.results[0].metadata.value == "Innovation"
    assert response.results[0].metadata.persona == "A persona"


def test_list_history_logs_prefers_explicit_metadata_value(monkeypatch):
    log = SimpleNamespace(
        metadata={
            "id": "run-2",
            "task": {"name": "Task", "url": "http://example.test", "description": ""},
            "timestamp_utc": "2026-08-24T00:00:00+00:00",
            "value": "Explicit Value",
            "persona": {"value": "Nested Value", "content": "A persona"},
            "model": "test-model",
            "run_index": 1,
        },
        summary={
            "is_done": True,
            "is_successful": True,
            "has_errors": False,
            "number_of_steps": 6,
            "total_duration_seconds": 1.0,
            "final_result": "Done",
        },
        details=_Details(),
        filename="run-2.json",
    )
    monkeypatch.setattr(history_logs._service, "list_logs", lambda **_kwargs: [log])
    request = SimpleNamespace(
        headers={},
        url=SimpleNamespace(scheme="http"),
        url_for=lambda _name: "http://example.test/api/v1/history-logs/screenshot",
    )

    response = asyncio.run(
        history_logs.list_history_logs(
            request,
            dataset="data1",
            data_source=None,
            screenshot_mode="none",
        )
    )

    assert response.results[0].metadata.value == "Explicit Value"
