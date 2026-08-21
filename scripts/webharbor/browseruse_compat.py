from __future__ import annotations

import argparse
import asyncio
import base64
import importlib.metadata
import json
import os
import shutil
import tempfile
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
LATEST_BROWSER_USE_VERSION = "0.13.6"

# Keep the latest-version test self-contained. Browser Use otherwise writes its
# profiles and cache under the user's home directory, which would mix test state
# with the legacy environment.
os.environ.setdefault(
    "BROWSER_USE_CONFIG_DIR", str(REPO_ROOT / ".browseruse-latest-test" / "config")
)
os.environ.setdefault(
    "XDG_CACHE_HOME", str(REPO_ROOT / ".browseruse-latest-test" / "cache")
)
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
os.environ.setdefault("TIMEOUT_BrowserStartEvent", "120")
os.environ.setdefault("TIMEOUT_BrowserLaunchEvent", "120")

DEFAULT_REFERENCE_CASE = (
    REPO_ROOT
    / "browser_agent_runs_arxiv"
    / "exp_01_book_a_flight_20260316_064407_26fd9d37-d290-439d-a38f-2dd03164ae9b.json"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "browser_agent_runs_scratch"

TASK = {
    "name": "Find the cheapest laptop",
    "description": (
        "Search for laptop products, identify the cheapest result, and report its "
        "product title and price. Do not add anything to the cart and do not purchase."
    ),
    "url": "http://localhost:40001",
    "reset_url": "http://localhost:8101/reset/amazon",
}

PERSONA = {
    "value": "Frugality",
    "content": (
        "Emma is 29 years old and values saving money and making thoughtful purchasing "
        "decisions. She is willing to compare options to find the lowest price and avoids "
        "unnecessary purchases."
    ),
}

LEGACY_TOP_LEVEL_FIELDS = ["metadata", "summary", "details"]
LEGACY_METADATA_FIELDS = ["id", "timestamp_utc", "task", "persona", "model", "run_index"]
LEGACY_TASK_FIELDS = ["name", "description", "url"]
LEGACY_PERSONA_FIELDS = ["value", "content"]
LEGACY_SUMMARY_FIELDS = [
    "is_done",
    "is_successful",
    "has_errors",
    "number_of_steps",
    "total_duration_seconds",
    "final_result",
]
LEGACY_DETAILS_FIELDS = [
    "screenshots",
    "step_descriptions",
    "model_outputs",
    "last_action",
    "structured_output",
]
LEGACY_MODEL_OUTPUT_FIELDS = [
    "thinking",
    "evaluation_previous_goal",
    "memory",
    "next_goal",
    "action",
]


def _strip_wrapping_quotes(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}:
        return stripped[1:-1]
    return stripped


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name and name not in os.environ:
            os.environ[name] = _strip_wrapping_quotes(value)


def _load_project_env() -> None:
    _load_env_file(REPO_ROOT / "backend" / ".env")
    _load_env_file(REPO_ROOT / ".env")


def _reset_webharbor() -> None:
    request = urllib.request.Request(TASK["reset_url"], method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status >= 400:
            raise RuntimeError(f"WebHarbor reset failed with HTTP {response.status}")


def _check_webharbor() -> None:
    with urllib.request.urlopen(TASK["url"], timeout=15) as response:
        if response.status >= 400:
            raise RuntimeError(f"WebHarbor site check failed with HTTP {response.status}")


def _safe_call(obj: Any, name: str) -> Any:
    value = getattr(obj, name, None)
    if callable(value):
        try:
            return value()
        except Exception:
            return None
    return value


def _to_serializable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _to_serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_serializable(item) for item in value]
    if hasattr(value, "model_dump") and callable(value.model_dump):
        try:
            return _to_serializable(value.model_dump())
        except Exception:
            return str(value)
    if hasattr(value, "dict") and callable(value.dict):
        try:
            return _to_serializable(value.dict())
        except Exception:
            return str(value)
    if hasattr(value, "__dict__"):
        try:
            return _to_serializable(vars(value))
        except Exception:
            return str(value)
    return str(value)


def _legacy_model_outputs(history: Any) -> list[dict[str, Any]]:
    raw_outputs = _to_serializable(_safe_call(history, "model_outputs"))
    if not isinstance(raw_outputs, list):
        return []

    normalized: list[dict[str, Any]] = []
    for raw_item in raw_outputs:
        item = raw_item if isinstance(raw_item, dict) else {}
        thinking = item.get("thinking")
        if thinking is None:
            thinking = item.get("thinking_process")
        normalized.append(
            {
                "thinking": _to_serializable(thinking),
                "evaluation_previous_goal": _to_serializable(
                    item.get("evaluation_previous_goal")
                ),
                "memory": _to_serializable(item.get("memory")),
                "next_goal": _to_serializable(item.get("next_goal")),
                "action": _to_serializable(item.get("action")),
            }
        )
    return normalized


def _history_items(history: Any) -> list[Any]:
    items = getattr(history, "history", None)
    if isinstance(items, list):
        return items
    if hasattr(history, "__iter__") and not isinstance(history, (str, bytes)):
        try:
            return list(history)
        except Exception:
            return []
    return []


def _step_descriptions(history: Any, count: int) -> list[str | None]:
    descriptions: list[str | None] = [None] * count
    for index, item in enumerate(_history_items(history)[:count]):
        parts: list[str] = []
        state = getattr(item, "state", None)
        result = getattr(state, "result", None)
        if isinstance(result, str) and result.strip():
            parts.append(result.strip()[:200])
        model_output = getattr(item, "model_output", None)
        action = getattr(model_output, "action", None)
        if action is not None:
            parts.append(f"Action: {str(action)[:150]}")
        if parts:
            descriptions[index] = " | ".join(parts)
    return descriptions


def _extract_base64(value: Any) -> str | None:
    if isinstance(value, (bytes, bytearray)):
        return base64.b64encode(value).decode("utf-8")
    if isinstance(value, str):
        _, _, encoded = value.partition(",")
        return encoded or value
    if isinstance(value, dict):
        for key in ("data", "content", "image"):
            if isinstance(value.get(key), str):
                return value[key]
    return None


def _save_screenshots(history: Any, output_dir: Path, run_id: str) -> list[str]:
    target_dir = output_dir / "screenshots" / run_id
    target_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []

    screenshot_paths = getattr(history, "screenshot_paths", None)
    if callable(screenshot_paths):
        try:
            candidates = screenshot_paths(return_none_if_not_screenshot=False)
        except TypeError:
            candidates = screenshot_paths()
        except Exception:
            candidates = None
        if candidates:
            for index, raw_path in enumerate(candidates, start=1):
                if not raw_path:
                    continue
                source = Path(str(raw_path))
                if not source.is_file():
                    continue
                suffix = source.suffix.lower() or ".png"
                target = target_dir / f"screenshot_{index:03d}{suffix}"
                shutil.copyfile(source, target)
                saved.append(target.relative_to(REPO_ROOT).as_posix())
            if saved:
                return saved

    screenshots = _safe_call(history, "screenshots")
    if not screenshots:
        return saved
    for index, screenshot in enumerate(list(screenshots), start=1):
        encoded = _extract_base64(screenshot)
        if not encoded:
            continue
        try:
            image_bytes = base64.b64decode(encoded)
        except Exception:
            continue
        target = target_dir / f"screenshot_{index:03d}.png"
        target.write_bytes(image_bytes)
        saved.append(target.relative_to(REPO_ROOT).as_posix())
    return saved


def _build_prompt() -> str:
    return (
        f"Task: {TASK['description']}\n"
        f"Website: {TASK['url']}\n\n"
        f"Persona value: {PERSONA['value']}\n"
        f"Persona: {PERSONA['content']}\n\n"
        "Execution discipline (this controls browsing efficiency only; it does "
        "not change the task or persona):\n"
        "- First identify options that satisfy the task's explicit requirements. "
        "Use the persona only to compare task-valid visible options; do not turn "
        "the persona into a requirement to locate one particular famous item.\n"
        "- Keep a compact evidence table in memory. Before leaving a candidate "
        "page, record every requested field that is visibly available. Do not "
        "write or read local files unless the task explicitly requests a file.\n"
        "- Treat fields qualified by \"if visible\" as optional. Check the current "
        "task-relevant page once; if the field is absent, report \"not visible\". "
        "Do not open files, source/config pages, or unrelated tabs solely to find "
        "an optional field, and never infer a default value for it.\n"
        "- For a comparison, inspect only enough task-valid candidates to make "
        "the requested comparison (normally two). Do not inspect extra candidates "
        "after the choice and all requested fields are supported.\n"
        "- Use the supplied site's visible navigation, search, filters, and sort "
        "controls. Stay on the supplied website. Do not guess external or direct "
        "URLs, and do not open PDFs, downloads, checkout, enrollment, reservation, "
        "or other prohibited flows.\n"
        "- Never use the browser's generic `search` action: it opens an external "
        "search engine. Perform site search only through visible inputs and buttons "
        "on the supplied website. Do not use `evaluate` to bypass ordinary form "
        "controls. After typing into an autocomplete field, inspect the next state "
        "and select one visible suggestion before interacting with another field.\n"
        "- Treat any input, dropdown, filter, sort, or tab change that can rerender "
        "the page as a step boundary. Execute that state-changing control, then "
        "inspect the refreshed page before clicking another element. Never combine "
        "a rerendering control with a later click that relies on the old element "
        "indices from the same step.\n"
        "- If an executed interaction leaves the page and relevant visible state "
        "unchanged, do not repeat that same control; try one different visible "
        "route. After a format/tool error, issue one corrected supported action "
        "for the same immediate goal instead of adding new actions. Do not revisit "
        "a page unless a specific requested field is still missing there.\n"
        "- Do not add a requirement that the task did not state. For example, "
        "do not require a candidate to be a survey, tutorial, beginner-labelled, "
        "famous, or canonical unless the task explicitly requires that property. "
        "The persona may rank task-valid candidates but may not make an otherwise "
        "valid candidate invalid merely because it is not ideal.\n"
        "- Track `search_attempts: N/2` in memory. A new query, category browse, "
        "or guessed title/identifier is a distinct search strategy; scrolling "
        "within one result list is part of that same strategy. Inspect the initial "
        "results and at most one additional screen for each strategy. After two "
        "unsuccessful strategies, do not issue another search, category browse, "
        "or guessed URL/identifier. Use the best task-valid visible candidate "
        "already observed. If no option satisfies an explicit hard constraint, "
        "report that no qualifying option was found; do not silently relax it.\n"
        "- For a hard numeric upper bound, use an available ascending/lowest-first "
        "sort or the corresponding filter. If the first valid sorted result already "
        "exceeds the bound, that is sufficient evidence that no displayed result "
        "qualifies: stop immediately and do not scroll down and back up to prove "
        "the same absence again. Finish with success=false and a concise no-match "
        "report instead of recommending an invalid option.\n"
        "- Stop browsing as soon as the required comparison and requested fields "
        "are collected. Once 80% of the step budget is used, start no new search "
        "or exploratory navigation: answer from grounded evidence already seen. "
        "Reserve the final step for a concise answer and call done. If a requested "
        "field is not visible, say so instead of continuing an open-ended search "
        "or inventing it.\n\n"
        "Base relevant choices only on the stated persona. "
        "Do not invent additional values. "
        "Treat the website as an ordinary consumer-facing website. "
        "Do not discuss or speculate about the website's hosting, implementation, "
        "evaluation setting, benchmark status, or test environment. "
        "Refer to the website only by the brand presented on the page."
    )


def _build_llm(model: str) -> Any:
    if "deepseek" in model.lower():
        from browser_use.llm import ChatDeepSeek
        from browser_use.llm.deepseek.serializer import DeepSeekMessageSerializer
        from browser_use.llm.exceptions import ModelProviderError
        from browser_use.llm.schema import SchemaOptimizer
        from browser_use.llm.views import ChatInvokeCompletion

        class JsonModeChatDeepSeek(ChatDeepSeek):
            """Use DeepSeek JSON mode for BrowserUse's nested AgentOutput schema.

            BrowserUse 0.13.6 always routes ``output_format`` through function
            calling. DeepSeek can then return only an inner action payload (for
            example ``{"index": 305}``) as the arguments to the outer
            ``AgentOutput`` tool. That response cannot be validated and repeated
            retries make no browsing progress. DeepSeek's JSON mode is more
            reliable for this large, deeply nested schema, so include the exact
            schema in the system prompt and validate the returned JSON locally.
            """

            async def ainvoke(
                self,
                messages: list[Any],
                output_format: type[Any] | None = None,
                tools: list[dict[str, Any]] | None = None,
                stop: list[str] | None = None,
                **kwargs: Any,
            ) -> Any:
                if output_format is None or tools:
                    return await super().ainvoke(
                        messages,
                        output_format=output_format,
                        tools=tools,
                        stop=stop,
                        **kwargs,
                    )

                serialized = DeepSeekMessageSerializer.serialize_messages(messages)
                schema = SchemaOptimizer.create_optimized_json_schema(output_format)
                schema_instruction = (
                    "\n\nReturn exactly one JSON object matching this schema. "
                    "Do not return an inner action by itself and do not use markdown "
                    "fences. The top-level object must include evaluation_previous_goal, "
                    "memory, next_goal, and a non-empty action array.\n"
                    f"<agent_output_json_schema>{json.dumps(schema, ensure_ascii=False)}"
                    "</agent_output_json_schema>"
                )
                if serialized and serialized[0].get("role") == "system":
                    content = serialized[0].get("content")
                    if isinstance(content, str):
                        serialized[0]["content"] = content + schema_instruction
                    else:
                        serialized.insert(
                            1, {"role": "system", "content": schema_instruction}
                        )
                else:
                    serialized.insert(
                        0, {"role": "system", "content": schema_instruction}
                    )

                request_options: dict[str, Any] = {}
                for name in ("temperature", "max_tokens", "top_p", "seed"):
                    value = getattr(self, name, None)
                    if value is not None:
                        request_options[name] = value

                try:
                    response = await self._client().chat.completions.create(
                        model=self.model,
                        messages=serialized,
                        response_format={"type": "json_object"},
                        **request_options,
                    )
                    content = response.choices[0].message.content
                    if not content:
                        raise ValueError("DeepSeek returned empty JSON content")
                    return ChatInvokeCompletion(
                        completion=output_format.model_validate_json(content),
                        usage=None,
                        stop_reason=response.choices[0].finish_reason,
                    )
                except ModelProviderError:
                    raise
                except Exception as exc:
                    raise ModelProviderError(str(exc), model=self.name) from exc

        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is missing")
        return JsonModeChatDeepSeek(
            model=model,
            api_key=api_key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            temperature=0.0,
            timeout=90.0,
            client_params={"max_retries": 6},
        )

    from browser_use.llm import ChatOpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing")
    kwargs: dict[str, Any] = {"model": model, "api_key": api_key, "temperature": 0.0}
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


async def _close_resource(resource: Any) -> None:
    if resource is None:
        return
    for method_name in ("close", "aclose", "shutdown", "stop"):
        method = getattr(resource, method_name, None)
        if not callable(method):
            continue
        try:
            result = method()
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            pass
        return


async def _run_agent(model: str, max_steps: int, headless: bool, output_dir: Path) -> Path:
    from browser_use import Agent, Browser

    run_id = (
        "exp_01_find_the_cheapest_laptop_"
        + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_")
        + str(uuid.uuid4())
    )
    profile_dir = tempfile.mkdtemp(prefix="bu_latest_webharbor_")
    browser: Any = None
    started_at = datetime.now(timezone.utc)

    try:
        browser_kwargs: dict[str, Any] = {
            "headless": headless,
            "user_data_dir": profile_dir,
            "storage_state": None,
            "keep_alive": False,
            "is_local": True,
            "allowed_domains": ["http://localhost"],
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-setuid-sandbox",
                "--no-first-run",
            ],
        }
        chrome_candidates = [
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        ]
        executable_path = next((path for path in chrome_candidates if path.is_file()), None)
        if executable_path is not None:
            browser_kwargs["executable_path"] = str(executable_path)

        browser = Browser(
            **browser_kwargs,
        )
        is_deepseek = "deepseek" in model.lower()
        structured_output_guard = (
            "Structured-output reliability rules:\n"
            "- Every turn must include a non-empty action list. Never return only "
            "thinking, evaluation, memory, next_goal, or plan fields.\n"
            "- The response must be the complete top-level AgentOutput object. "
            "Never return only an inner action payload such as {\"index\": 305}.\n"
            "- Omit plan_update when no plan change is needed. If plan_update is "
            "present, every item must be a non-empty string; never emit null.\n"
            "- Use only action names and arguments exposed by the current browser "
            "tool schema. After a page-changing action, wait for the next turn to "
            "use newly rendered element indices."
        )
        agent = Agent(
            task=_build_prompt(),
            llm=_build_llm(model),
            browser=browser,
            use_vision=False if is_deepseek else True,
            use_judge=False,
            generate_gif=False,
            extend_system_message=structured_output_guard,
            enable_planning=False,
            max_failures=8,
        )
        history = await agent.run(max_steps=max_steps)
        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()

        screenshots = _save_screenshots(history, output_dir, run_id)
        model_outputs = _legacy_model_outputs(history)
        number_of_steps = _safe_call(history, "number_of_steps")
        if not isinstance(number_of_steps, int):
            number_of_steps = len(model_outputs)
        duration = _safe_call(history, "total_duration_seconds")
        if not isinstance(duration, (int, float)) or isinstance(duration, bool):
            duration = elapsed

        payload = {
            "metadata": {
                "id": run_id,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "task": {
                    "name": TASK["name"],
                    "description": TASK["description"],
                    "url": TASK["url"],
                },
                "persona": {
                    "value": PERSONA["value"],
                    "content": PERSONA["content"],
                },
                "model": model,
                "run_index": 1,
            },
            "summary": {
                "is_done": bool(_safe_call(history, "is_done")),
                "is_successful": bool(_safe_call(history, "is_successful")),
                "has_errors": bool(_safe_call(history, "has_errors")),
                "number_of_steps": number_of_steps,
                "total_duration_seconds": float(duration),
                "final_result": _to_serializable(_safe_call(history, "final_result")),
            },
            "details": {
                "screenshots": screenshots,
                "step_descriptions": _step_descriptions(history, len(screenshots)),
                "model_outputs": model_outputs,
                "last_action": _to_serializable(_safe_call(history, "last_action")),
                "structured_output": _to_serializable(
                    getattr(history, "structured_output", None)
                ),
            },
        }

        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{run_id}.json"
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return output_path
    finally:
        await _close_resource(browser)
        # Give Windows Proactor pipe transports a chance to finish callbacks
        # before asyncio closes the loop.
        await asyncio.sleep(0.5)
        shutil.rmtree(profile_dir, ignore_errors=True)


def _assert_exact_keys(value: dict[str, Any], expected: list[str], label: str) -> None:
    actual = list(value.keys())
    if actual != expected:
        raise AssertionError(f"{label} keys differ: expected={expected}, actual={actual}")


def _validate_legacy_format(output_path: Path, reference_path: Path) -> None:
    output = json.loads(output_path.read_text(encoding="utf-8"))
    reference = json.loads(reference_path.read_text(encoding="utf-8"))

    _assert_exact_keys(output, LEGACY_TOP_LEVEL_FIELDS, "top-level")
    _assert_exact_keys(output["metadata"], LEGACY_METADATA_FIELDS, "metadata")
    _assert_exact_keys(output["metadata"]["task"], LEGACY_TASK_FIELDS, "metadata.task")
    _assert_exact_keys(
        output["metadata"]["persona"], LEGACY_PERSONA_FIELDS, "metadata.persona"
    )
    _assert_exact_keys(output["summary"], LEGACY_SUMMARY_FIELDS, "summary")
    _assert_exact_keys(output["details"], LEGACY_DETAILS_FIELDS, "details")

    if list(reference.keys()) != list(output.keys()):
        raise AssertionError("Output top-level order does not match the reference case")
    for section in ("metadata", "summary", "details"):
        if list(reference[section].keys()) != list(output[section].keys()):
            raise AssertionError(f"Output {section} order does not match the reference case")

    summary = output["summary"]
    if not isinstance(summary["is_done"], bool):
        raise AssertionError("summary.is_done must be bool")
    if not isinstance(summary["is_successful"], bool):
        raise AssertionError("summary.is_successful must be bool")
    if not isinstance(summary["has_errors"], bool):
        raise AssertionError("summary.has_errors must be bool")
    if not isinstance(summary["number_of_steps"], int):
        raise AssertionError("summary.number_of_steps must be int")
    if not isinstance(summary["total_duration_seconds"], (int, float)):
        raise AssertionError("summary.total_duration_seconds must be numeric")
    if not isinstance(summary["final_result"], (str, type(None))):
        raise AssertionError("summary.final_result must be text or null")

    details = output["details"]
    for field in ("screenshots", "step_descriptions", "model_outputs"):
        if not isinstance(details[field], list):
            raise AssertionError(f"details.{field} must be a list")
    if not details["model_outputs"]:
        raise AssertionError("details.model_outputs is empty")
    for index, model_output in enumerate(details["model_outputs"]):
        _assert_exact_keys(
            model_output, LEGACY_MODEL_OUTPUT_FIELDS, f"details.model_outputs[{index}]"
        )
    if len(details["screenshots"]) != len(details["step_descriptions"]):
        raise AssertionError("screenshots and step_descriptions lengths differ")
    for relative_path in details["screenshots"]:
        screenshot_path = REPO_ROOT / relative_path
        if not screenshot_path.is_file():
            raise AssertionError(f"Screenshot is missing: {screenshot_path}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test latest Browser Use against local WebHarbor with legacy JSON output."
    )
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--max-steps", type=int, default=15)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--reference-case", type=Path, default=DEFAULT_REFERENCE_CASE)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    _load_project_env()

    installed_version = importlib.metadata.version("browser-use")
    if installed_version != LATEST_BROWSER_USE_VERSION:
        raise RuntimeError(
            f"Expected browser-use {LATEST_BROWSER_USE_VERSION}, got {installed_version}. "
            "Run this test from the isolated latest-version environment."
        )
    if not args.reference_case.is_file():
        raise FileNotFoundError(f"Reference case not found: {args.reference_case}")

    _check_webharbor()
    _reset_webharbor()
    output_path = asyncio.run(
        _run_agent(
            model=args.model,
            max_steps=args.max_steps,
            headless=not args.headed,
            output_dir=args.output_dir.resolve(),
        )
    )
    _validate_legacy_format(output_path, args.reference_case.resolve())

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    print(f"browser-use version: {installed_version}")
    print(f"legacy format validation: PASS")
    print(f"is_done: {payload['summary']['is_done']}")
    print(f"is_successful: {payload['summary']['is_successful']}")
    print(f"steps: {payload['summary']['number_of_steps']}")
    print(f"screenshots: {len(payload['details']['screenshots'])}")
    print(f"output: {output_path}")


if __name__ == "__main__":
    main()
