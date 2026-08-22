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
from urllib.parse import urlparse


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
os.environ.setdefault(
    "PLAYWRIGHT_BROWSERS_PATH",
    str(REPO_ROOT / ".browseruse-latest-test" / "ms-playwright"),
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


def _find_browser_executable() -> Path | None:
    """Find a system browser or the repository-isolated Playwright browser."""

    static_candidates = [
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]
    playwright_root = Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"])
    isolated_candidates = [
        *sorted(
            playwright_root.glob(
                "chromium-*/chrome-mac*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
            ),
            reverse=True,
        ),
        *sorted(
            playwright_root.glob(
                "chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium"
            ),
            reverse=True,
        ),
        *sorted(
            playwright_root.glob(
                "chromium_headless_shell-*/chrome-headless-shell-mac*/chrome-headless-shell"
            ),
            reverse=True,
        ),
        *sorted(
            playwright_root.glob("chromium-*/chrome-linux*/chrome"), reverse=True
        ),
        *sorted(
            playwright_root.glob("chromium-*/chrome-win*/chrome.exe"), reverse=True
        ),
    ]
    return next(
        (path for path in [*static_candidates, *isolated_candidates] if path.is_file()),
        None,
    )


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
        "Execution discipline (this does not add requirements to the task):\n"
        "- Complete exactly the stated task. Do not invent candidate quotas, required "
        "fields, hard constraints, or output formats that the task does not state.\n"
        "- Use the persona as the sole preference for choosing among task-valid options, "
        "not as a new hard eligibility requirement.\n"
        "- Base the choice only on information visibly available on the supplied website. "
        "Do not infer missing facts or use external search. Treat hidden or non-rendered "
        "page data as unavailable. Before answering, verify the exact chosen title and "
        "every quoted number in a rendered page you actually viewed, and copy them "
        "verbatim.\n"
        "- Use ordinary visible navigation and stay on the supplied website. Do not guess "
        "or construct direct item URLs, and do not perform any prohibited action.\n"
        "- Avoid repeated or redundant exploration. Inspect only enough options to make a "
        "grounded choice, then stop. Once 80% of the step budget is used, start no new "
        "exploration; reserve the final step for the answer and call done.\n"
        "- In the final answer, state the chosen option and briefly explain how visible "
        "evidence supports the persona-guided choice."
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
    kwargs: dict[str, Any] = {
        "model": model,
        "api_key": api_key,
        "temperature": 0.0,
        "max_completion_tokens": 16384,
        "timeout": 180.0,
    }
    if model.lower().startswith("gpt-5.5"):
        kwargs["reasoning_effort"] = "low"
    elif model.lower().startswith(("gpt-5", "o1", "o3", "o4")):
        kwargs["reasoning_effort"] = "minimal"
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
        task_url = urlparse(TASK["url"])
        allowed_origin = f"{task_url.scheme}://{task_url.hostname}"
        browser_kwargs: dict[str, Any] = {
            "headless": headless,
            "user_data_dir": profile_dir,
            "storage_state": None,
            "keep_alive": False,
            "is_local": True,
            "allowed_domains": [allowed_origin],
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-setuid-sandbox",
                "--no-first-run",
            ],
        }
        executable_path = _find_browser_executable()
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
            llm_timeout=180,
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
