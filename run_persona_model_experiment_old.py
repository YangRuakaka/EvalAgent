from __future__ import annotations

import argparse
import asyncio
import base64
import importlib
import inspect
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional


SCRIPT_DIR = Path(__file__).resolve().parent

# Directly set provider key here if you do not want to use .env.
# Leave empty or placeholder to fall back to environment variables.
HARDCODED_DEEPSEEK_API_KEY = ""
HARDCODED_OPENAI_API_KEY = ""

def _strip_wrapping_quotes(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}:
        return stripped[1:-1]
    return stripped


def _normalize_hardcoded_key(value: str | None) -> str | None:
    if value is None:
        return None

    stripped = value.strip()
    if not stripped:
        return None

    if stripped.startswith("<PUT_YOUR_") and stripped.endswith("_HERE>"):
        return None

    return stripped


def _load_env_file(env_path: Path, override: bool = False) -> int:
    if not env_path.exists() or not env_path.is_file():
        return 0

    loaded = 0
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue

        if not override and key in os.environ:
            continue

        os.environ[key] = _strip_wrapping_quotes(value)
        loaded += 1

    return loaded


def _bootstrap_env() -> None:
    env_candidates = [
        Path.cwd() / "backend" / ".env",
        SCRIPT_DIR / "backend" / ".env",
        Path.cwd() / ".env",
        SCRIPT_DIR / ".env",
    ]

    loaded = 0
    seen: set[Path] = set()
    for env_path in env_candidates:
        resolved = env_path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        loaded += _load_env_file(resolved, override=False)

    if loaded > 0:
        print(f"[INFO] Loaded {loaded} env vars from .env files")


@dataclass(frozen=True)
class TaskConfig:
    name: str
    url: str
    description: str = ""


@dataclass(frozen=True)
class PersonaConfig:
    value: str
    content: str


@dataclass(frozen=True)
class StandaloneSettings:
    output_dir: Path
    max_steps: int
    enable_screenshots: bool
    max_screenshots: int
    force_threaded_run_on_windows: bool
    llm_temperature: float
    deepseek_api_key: Optional[str]
    openai_api_key: Optional[str]
    anthropic_api_key: Optional[str]
    gemini_api_key: Optional[str]
    deepseek_base_url: str
    llm_base_url: Optional[str]
    openai_base_url: Optional[str]
    anthropic_base_url: Optional[str]
    gemini_base_url: Optional[str]
    ollama_base_url: str
    browser_start_timeout_seconds: float
    browser_action_timeout_seconds: float
    browser_navigation_timeout_seconds: float
    browser_navigation_complete_timeout_seconds: float
    browser_state_request_timeout_seconds: float
    browser_wait_timeout_seconds: float
    browser_save_storage_timeout_seconds: float
    resource_close_timeout_seconds: float
    enable_click_timeout_fallback_patch: bool
    patched_click_handler_timeout_seconds: float
    enable_browser_state_timeout_fallback_patch: bool
    patched_browser_state_handler_timeout_seconds: float
    agent_max_failures: int
    agent_final_response_after_failure: bool
    agent_use_thinking: bool

    @staticmethod
    def from_env(output_dir_override: str | None = None) -> "StandaloneSettings":
        output_raw = (output_dir_override or os.getenv("BROWSER_AGENT_RUN_OUTPUT_DIR") or "").strip()
        if output_raw:
            output_dir = Path(output_raw).expanduser()
            if not output_dir.is_absolute():
                output_dir = (Path.cwd() / output_dir).resolve()
        else:
            output_dir = (SCRIPT_DIR / "browser_agent_runs").resolve()

        return StandaloneSettings(
            output_dir=output_dir,
            max_steps=_env_int("BROWSER_AGENT_MAX_STEPS", default=20, min_value=1),
            enable_screenshots=_env_bool("BROWSER_AGENT_ENABLE_SCREENSHOTS", default=True),
            # 0 means unlimited screenshots; any positive value caps saved screenshots.
            max_screenshots=_env_int("BROWSER_AGENT_MAX_SCREENSHOTS", default=0, min_value=0),
            force_threaded_run_on_windows=_env_bool(
                "BROWSER_AGENT_FORCE_THREADED_RUN_ON_WINDOWS",
                default=True,
            ),
            llm_temperature=_env_float("DEFAULT_LLM_TEMPERATURE", default=0.0),
            deepseek_api_key=(
                _normalize_hardcoded_key(HARDCODED_DEEPSEEK_API_KEY)
                or _env_optional("DEEPSEEK_API_KEY")
            ),
            openai_api_key=(
                _normalize_hardcoded_key(HARDCODED_OPENAI_API_KEY)
                or _env_optional("OPENAI_API_KEY")
            ),
            anthropic_api_key=_env_optional("ANTHROPIC_API_KEY"),
            gemini_api_key=_env_optional("GEMINI_API_KEY"),
            deepseek_base_url=(os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").strip(),
            llm_base_url=_env_optional("LLM_BASE_URL"),
            openai_base_url=_env_optional("OPENAI_BASE_URL"),
            anthropic_base_url=_env_optional("ANTHROPIC_BASE_URL"),
            gemini_base_url=_env_optional("GEMINI_BASE_URL"),
            ollama_base_url=(os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").strip(),
            browser_start_timeout_seconds=_env_float(
                "BROWSER_AGENT_BROWSER_START_TIMEOUT_SECONDS",
                default=120.0,
            ),
            browser_action_timeout_seconds=_env_float(
                "BROWSER_AGENT_ACTION_TIMEOUT_SECONDS",
                default=60.0,
            ),
            browser_navigation_timeout_seconds=_env_float(
                "BROWSER_AGENT_NAVIGATION_TIMEOUT_SECONDS",
                default=60.0,
            ),
            browser_navigation_complete_timeout_seconds=_env_float(
                "BROWSER_AGENT_NAVIGATION_COMPLETE_TIMEOUT_SECONDS",
                default=90.0,
            ),
            browser_state_request_timeout_seconds=_env_float(
                "BROWSER_AGENT_BROWSER_STATE_REQUEST_TIMEOUT_SECONDS",
                default=90.0,
            ),
            browser_wait_timeout_seconds=_env_float(
                "BROWSER_AGENT_WAIT_EVENT_TIMEOUT_SECONDS",
                default=90.0,
            ),
            browser_save_storage_timeout_seconds=_env_float(
                "BROWSER_AGENT_SAVE_STORAGE_TIMEOUT_SECONDS",
                default=45.0,
            ),
            resource_close_timeout_seconds=_env_float(
                "BROWSER_AGENT_RESOURCE_CLOSE_TIMEOUT_SECONDS",
                default=8.0,
            ),
            enable_click_timeout_fallback_patch=_env_bool(
                "BROWSER_AGENT_ENABLE_CLICK_TIMEOUT_FALLBACK_PATCH",
                default=True,
            ),
            patched_click_handler_timeout_seconds=_env_float(
                "BROWSER_AGENT_PATCHED_CLICK_HANDLER_TIMEOUT_SECONDS",
                default=20.0,
            ),
            enable_browser_state_timeout_fallback_patch=_env_bool(
                "BROWSER_AGENT_ENABLE_BROWSER_STATE_TIMEOUT_FALLBACK_PATCH",
                default=True,
            ),
            patched_browser_state_handler_timeout_seconds=_env_float(
                "BROWSER_AGENT_PATCHED_BROWSER_STATE_HANDLER_TIMEOUT_SECONDS",
                default=35.0,
            ),
            agent_max_failures=_env_int("BROWSER_AGENT_MAX_FAILURES", default=3, min_value=1),
            agent_final_response_after_failure=_env_bool(
                "BROWSER_AGENT_FINAL_RESPONSE_AFTER_FAILURE",
                default=False,
            ),
            # Disable browser-use planning/thinking by default to avoid plan-style behavior.
            agent_use_thinking=_env_bool(
                "BROWSER_AGENT_USE_THINKING",
                default=False,
            ),
        )


@dataclass(frozen=True)
class ScreenshotArtifact:
    path: str
    base64_content: str | None = None


@dataclass(frozen=True)
class RunContext:
    run_id: str
    history_path: Path
    screenshots_dir: Path


@dataclass(frozen=True)
class RunResult:
    model: str
    run_index: int
    is_done: bool
    is_successful: bool
    has_errors: bool
    number_of_steps: int
    total_duration_seconds: float
    final_result: Any
    history_path: str


# ---------------------------------------------------------------------------
# Edit this block only.
# Team members can safely change tasks/personas/models/run_times here.
# ---------------------------------------------------------------------------
TASKS: List[TaskConfig] = [
    # TaskConfig(
    #     name="Book Shoes Online",
    #     url="http://34.55.136.249:3000/RiverBuy",
    #     description="Buy a pair of shoes.",
    # ),http://localhost:3000/
    TaskConfig(
        name="Book Shoes Online",
        url="http://34.55.136.249:3000/RiverBuy",
        description="Buy a pair of shoes.",
    ),
    # TaskConfig(
    #     name="Rent a car",
    #     url="http://34.55.136.249:3000/zoomcar",
    #     description="Rent a car for a family vacation.",
    # ),
]

PERSONAS: List[PersonaConfig] = [
    # PersonaConfig(
    #     value="Frugality",
    #     content="Emma is 29 years old and values saving money and making thoughtful purchasing decisions. She is willing to spend time researching and comparing options to find the best deals and discounts. She prefers budget-friendly choices and is cautious about unnecessary expenses.",
    # ),
    # PersonaConfig(
    #     value="Sustainability",
    #     content="You prioritize environmentally friendly and socially responsible choices.",
    # ),
    PersonaConfig(
        value="Comfort",
        content="You prioritize a comfortable and enjoyable travel experience.",
    ),
    # PersonaConfig(
    #     value="Luxury",
    #     content="You prioritize comfort and premium experiences, even at higher costs.",
    # ),
    # PersonaConfig(
    #     value="Innovation",
    #     content="Emma is 29 years old and works as a software engineer. She likes to stay updated with the latest technology trends and enjoys trying out new gadgets and services. She values efficiency and is open to using innovative solutions that can enhance her travel experience.",
    # ),
]

MODELS: List[str] = [
    "deepseek-chat",
]

RUN_TIMES: int = 1
# ---------------------------------------------------------------------------


EXPECTED_TOP_LEVEL_FIELDS = ["metadata", "summary", "details"]
EXPECTED_METADATA_FIELDS = ["id", "timestamp_utc", "task", "persona", "model", "run_index"]
EXPECTED_SUMMARY_FIELDS = [
    "is_done",
    "is_successful",
    "has_errors",
    "number_of_steps",
    "total_duration_seconds",
    "final_result",
]
EXPECTED_DETAILS_FIELDS = [
    "screenshots",
    "step_descriptions",
    "model_outputs",
    "last_action",
    "structured_output",
]


def _env_optional(name: str) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def _env_int(name: str, default: int, min_value: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        parsed = int(raw.strip())
    except ValueError:
        return default
    return parsed if parsed >= min_value else min_value


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw.strip())
    except ValueError:
        return default


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(levelname)s] %(name)s - %(message)s",
        force=True,
    )


def _filter_kwargs_for_callable(
    callable_obj: Any,
    kwargs: dict[str, Any],
    *,
    callable_name: str,
) -> dict[str, Any]:
    try:
        signature = inspect.signature(callable_obj)
    except Exception:
        return kwargs

    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
        return kwargs

    accepted = {
        name
        for name, param in signature.parameters.items()
        if param.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    filtered = {key: value for key, value in kwargs.items() if key in accepted}

    dropped = sorted(set(kwargs) - set(filtered))
    if dropped:
        logging.warning("Dropping unsupported kwargs for %s: %s", callable_name, dropped)

    return filtered


def _slugify(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "_", (value or "").strip())
    token = token.strip("_")
    return token.lower() or "task"


def _build_run_id(task_name: str, task_index: int) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"exp_{task_index:02d}_{_slugify(task_name)}_{stamp}"


def _to_portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except Exception:
        return str(resolved)


def _resolve_history_file(path_str: str) -> Path:
    candidate = Path(path_str)
    if candidate.is_absolute():
        return candidate.resolve()
    return (Path.cwd() / candidate).resolve()


def _resolve_screenshot_file(path_str: str, history_file: Path) -> Path | None:
    raw = str(path_str or "").replace("\\", "/").strip()
    if not raw:
        return None

    candidate = Path(raw)
    possible: list[Path] = []

    if candidate.is_absolute():
        possible.append(candidate.resolve())
    else:
        possible.append((Path.cwd() / candidate).resolve())
        possible.append((history_file.parent / candidate).resolve())

        parts = [part for part in candidate.parts if part not in {"", "."}]
        if "screenshots" in parts:
            idx = parts.index("screenshots")
            suffix = Path(*parts[idx + 1 :]) if idx + 1 < len(parts) else None
            if suffix is not None:
                possible.append((history_file.parent / "screenshots" / suffix).resolve())

    seen: set[Path] = set()
    for path_item in possible:
        if path_item in seen:
            continue
        seen.add(path_item)
        if path_item.exists() and path_item.is_file():
            return path_item

    return None


def _expect_exact_fields(payload: dict, expected_keys: list[str], section_name: str) -> None:
    actual = list(payload.keys())
    if actual != expected_keys:
        raise ValueError(
            f"{section_name} fields mismatch. expected={expected_keys}, actual={actual}"
        )


def _validate_history_json(history_file: Path) -> dict:
    payload = json.loads(history_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid JSON object: {history_file}")

    _expect_exact_fields(payload, EXPECTED_TOP_LEVEL_FIELDS, "top-level")

    metadata = payload.get("metadata")
    summary = payload.get("summary")
    details = payload.get("details")

    if not isinstance(metadata, dict):
        raise ValueError(f"metadata must be an object: {history_file}")
    if not isinstance(summary, dict):
        raise ValueError(f"summary must be an object: {history_file}")
    if not isinstance(details, dict):
        raise ValueError(f"details must be an object: {history_file}")

    _expect_exact_fields(metadata, EXPECTED_METADATA_FIELDS, "metadata")
    _expect_exact_fields(summary, EXPECTED_SUMMARY_FIELDS, "summary")
    _expect_exact_fields(details, EXPECTED_DETAILS_FIELDS, "details")

    screenshots = details.get("screenshots", [])
    if not isinstance(screenshots, list):
        raise ValueError(f"details.screenshots must be a list: {history_file}")

    missing: list[str] = []
    for path_str in screenshots:
        resolved = _resolve_screenshot_file(str(path_str), history_file)
        if resolved is None:
            missing.append(str(path_str))

    if missing:
        raise ValueError(
            "Screenshot files missing for history JSON "
            f"{history_file}. Missing entries: {missing}"
        )

    return payload


def _validate_experiment_config(run_times: int) -> None:
    if not TASKS:
        raise ValueError("TASKS is empty. Add at least one task.")
    if not PERSONAS:
        raise ValueError("PERSONAS is empty. Add at least one persona.")
    if not MODELS:
        raise ValueError("MODELS is empty. Add at least one model.")
    if run_times < 1:
        raise ValueError("run_times must be >= 1")
    for task in TASKS:
        if not re.match(r"^https?://", (task.url or "").strip()):
            raise ValueError(
                f"Invalid task URL for '{task.name}': {task.url}. URL must start with http:// or https://"
            )


def _override_tasks_website_url(tasks: list[TaskConfig], website_url: str | None) -> list[TaskConfig]:
    if website_url is None:
        return tasks

    normalized_url = website_url.strip()
    if not normalized_url:
        raise ValueError("--website-url cannot be empty")

    return [
        TaskConfig(name=task.name, url=normalized_url, description=task.description)
        for task in tasks
    ]


def _format_result_line(result: RunResult) -> str:
    final_result = str(result.final_result or "").replace("\n", " ").strip()
    if len(final_result) > 120:
        final_result = final_result[:117] + "..."
    return (
        f"model={result.model} run_index={result.run_index} "
        f"done={result.is_done} success={result.is_successful} errors={result.has_errors} "
        f"steps={result.number_of_steps} duration={result.total_duration_seconds:.2f}s "
        f"history_path={result.history_path} final_result={final_result}"
    )


def _cleanup_history_artifacts(history_file: Path) -> list[Path]:
    removed: list[Path] = []

    if history_file.exists() and history_file.is_file():
        history_file.unlink(missing_ok=True)
        removed.append(history_file)

    screenshot_dir = history_file.parent / "screenshots" / history_file.stem
    if screenshot_dir.exists() and screenshot_dir.is_dir():
        shutil.rmtree(screenshot_dir, ignore_errors=True)
        removed.append(screenshot_dir)

    return removed


def _cleanup_failed_result_artifacts(result: RunResult) -> None:
    history_path_raw = str(getattr(result, "history_path", "") or "").strip()
    if not history_path_raw:
        return

    if history_path_raw in {".", "./", ".\\"}:
        return

    history_file = _resolve_history_file(history_path_raw)
    removed_paths = _cleanup_history_artifacts(history_file)
    if removed_paths:
        logging.warning(
            "Cleaned failed run artifacts | history_path=%s removed=%s",
            history_path_raw,
            [str(path) for path in removed_paths],
        )


class StandaloneBrowserAgentService:
    _click_patch_applied: bool = False
    _browser_state_patch_applied: bool = False

    def __init__(self, settings: StandaloneSettings) -> None:
        self._settings = settings
        self._output_dir = settings.output_dir.resolve()
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._apply_browser_use_timeout_overrides()
        self._browser_executable_path = self._resolve_browser_executable_path()

        # Older browser-use versions may try auto-install inside a 30s event timeout.
        # Pre-install Chromium once at startup if needed to avoid runtime timeouts.
        if not self._browser_executable_path:
            self._preinstall_playwright_chromium()
            self._browser_executable_path = self._resolve_browser_executable_path()

        if self._browser_executable_path:
            logging.info("Using browser executable path: %s", self._browser_executable_path)
        else:
            logging.warning(
                "No browser executable path resolved; browser-use may try runtime auto-install and timeout. "
                "Set BROWSER_AGENT_BROWSER_EXECUTABLE_PATH to force a local browser binary."
            )

    def _apply_browser_use_timeout_overrides(self) -> None:
        timeout_env_defaults = {
            "TIMEOUT_BrowserStartEvent": self._settings.browser_start_timeout_seconds,
            "TIMEOUT_ClickElementEvent": self._settings.browser_action_timeout_seconds,
            "TIMEOUT_TypeTextEvent": self._settings.browser_action_timeout_seconds,
            "TIMEOUT_ScrollEvent": self._settings.browser_action_timeout_seconds,
            "TIMEOUT_SendKeysEvent": self._settings.browser_action_timeout_seconds,
            "TIMEOUT_NavigateToUrlEvent": self._settings.browser_navigation_timeout_seconds,
            "TIMEOUT_NavigationCompleteEvent": self._settings.browser_navigation_complete_timeout_seconds,
            "TIMEOUT_BrowserStateRequestEvent": self._settings.browser_state_request_timeout_seconds,
            "TIMEOUT_WaitEvent": self._settings.browser_wait_timeout_seconds,
            "TIMEOUT_SaveStorageStateEvent": self._settings.browser_save_storage_timeout_seconds,
        }

        applied_values: dict[str, str] = {}
        for env_name, default_seconds in timeout_env_defaults.items():
            existing = (os.getenv(env_name) or "").strip()
            if existing:
                applied_values[env_name] = existing
                continue
            value = str(default_seconds)
            os.environ[env_name] = value
            applied_values[env_name] = value

        logging.info(
            "browser-use timeouts | start=%ss action=%ss navigation=%ss navigation_complete=%ss browser_state=%ss wait=%ss save_storage=%ss close_timeout=%ss max_failures=%s final_response_after_failure=%s",
            applied_values["TIMEOUT_BrowserStartEvent"],
            applied_values["TIMEOUT_ClickElementEvent"],
            applied_values["TIMEOUT_NavigateToUrlEvent"],
            applied_values["TIMEOUT_NavigationCompleteEvent"],
            applied_values["TIMEOUT_BrowserStateRequestEvent"],
            applied_values["TIMEOUT_WaitEvent"],
            applied_values["TIMEOUT_SaveStorageStateEvent"],
            self._settings.resource_close_timeout_seconds,
            self._settings.agent_max_failures,
            self._settings.agent_final_response_after_failure,
        )
        logging.info(
            "browser-use behavior | use_thinking=%s",
            self._settings.agent_use_thinking,
        )

    def _resolve_browser_executable_path(self) -> str | None:
        def _is_executable_file(path: Path) -> bool:
            return path.exists() and path.is_file() and os.access(path, os.X_OK)

        # 1) Explicit override for this script.
        override = (os.getenv("BROWSER_AGENT_BROWSER_EXECUTABLE_PATH") or "").strip()
        if override:
            override_path = Path(override).expanduser()
            if _is_executable_file(override_path):
                return str(override_path.resolve())
            logging.warning(
                "Ignoring invalid BROWSER_AGENT_BROWSER_EXECUTABLE_PATH (not executable file): %s",
                override,
            )

        # 2) Compatible env vars used by other runners/tools.
        for env_var in ("CHROME_PATH", "CHROMIUM_PATH", "BROWSER_PATH"):
            env_path_raw = (os.getenv(env_var) or "").strip()
            if not env_path_raw:
                continue
            env_path = Path(env_path_raw).expanduser()
            if _is_executable_file(env_path):
                return str(env_path.resolve())

        # 3) Common system paths (Linux + macOS).
        system_paths = [
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/lib/chromium/chromium",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            str(
                Path.home()
                / "Applications/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
            ),
            str(Path.home() / "Applications/Chromium.app/Contents/MacOS/Chromium"),
        ]
        for raw_path in system_paths:
            candidate = Path(raw_path)
            if _is_executable_file(candidate):
                return str(candidate.resolve())

        # 4) Playwright cache paths (including macOS variants).
        pw_cache_candidates = [
            Path.home() / ".cache" / "ms-playwright",
            Path.home() / "Library" / "Caches" / "ms-playwright",
        ]
        browser_patterns = [
            "chromium-*/chrome-linux/chrome",
            "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
            "chromium-*/chrome-mac/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
            "chromium-*/chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium",
            "chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
            "chromium-*/chrome-mac-x64/Chromium.app/Contents/MacOS/Chromium",
            "chromium-*/chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
            "chromium-*/chrome-win/chrome.exe",
            "chromium_headless_shell-*/chrome-headless-shell-linux/headless_shell",
            "chromium_headless_shell-*/chrome-headless-shell-mac/chrome-headless-shell",
            "chromium_headless_shell-*/chrome-headless-shell-mac-arm64/chrome-headless-shell",
            "chromium_headless_shell-*/chrome-headless-shell-mac-x64/chrome-headless-shell",
            "chromium_headless_shell-*/chrome-headless-shell-win64/chrome-headless-shell.exe",
        ]
        for pw_cache in pw_cache_candidates:
            if not pw_cache.exists():
                continue
            for pattern in browser_patterns:
                for chrome_bin in sorted(pw_cache.glob(pattern), reverse=True):
                    if _is_executable_file(chrome_bin):
                        return str(chrome_bin.resolve())

        # 5) shutil.which fallback.
        for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
            found = shutil.which(name)
            if found:
                found_path = Path(found)
                if _is_executable_file(found_path):
                    return str(found_path.resolve())

        # 6) Playwright API probe as last attempt.
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                candidate = Path(playwright.chromium.executable_path)
                if _is_executable_file(candidate):
                    return str(candidate.resolve())
        except Exception as exc:
            logging.debug("Could not resolve Playwright Chromium executable path via API probe: %s", exc)

        return None

    def _preinstall_playwright_chromium(self) -> None:
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
        except Exception as exc:
            logging.warning("Pre-installing Playwright Chromium failed before run: %s", exc)
            return

        if completed.returncode != 0:
            stderr_tail = (completed.stderr or "").strip()[-600:]
            logging.warning(
                "Playwright Chromium pre-install exited with code %s. stderr_tail=%s",
                completed.returncode,
                stderr_tail,
            )
            return

        logging.info("Playwright Chromium pre-install finished successfully.")

    async def run_task(
        self,
        *,
        task: TaskConfig,
        personas: list[PersonaConfig],
        models: list[str],
        run_times: int,
        task_run_id: str,
    ) -> list[RunResult]:
        results: list[RunResult] = []
        for persona in personas:
            for model_name in models:
                for run_index in range(1, run_times + 1):
                    result = await self._run_single(
                        task=task,
                        persona=persona,
                        model_name=model_name,
                        run_index=run_index,
                        task_run_id=task_run_id,
                    )
                    results.append(result)
        return results

    def validate_model_credentials(self, models: list[str]) -> None:
        missing: list[tuple[str, str]] = []
        for model_name in models:
            provider = self._resolve_provider_from_model(model_name)
            if provider == "ollama":
                continue
            if not self._api_key_for_provider(provider):
                missing.append((model_name, provider))

        if not missing:
            return

        details = ", ".join(
            [f"model='{model}' provider='{provider}'" for model, provider in missing]
        )
        raise RuntimeError(
            "Missing API keys for configured models. "
            "Set hardcoded provider keys in this file (for example HARDCODED_DEEPSEEK_API_KEY or HARDCODED_OPENAI_API_KEY), "
            "or configure provider env vars. "
            f"Details: {details}"
        )

    async def _run_single(
        self,
        *,
        task: TaskConfig,
        persona: PersonaConfig,
        model_name: str,
        run_index: int,
        task_run_id: str,
    ) -> RunResult:
        agent = None
        tmp_profile: str | None = None

        try:
            llm = self._get_browser_use_llm(model_name)
            from browser_use import Agent, BrowserSession

            self._patch_browser_use_click_handler_if_needed()
            self._patch_browser_use_browser_state_handler_if_needed()

            tmp_profile = tempfile.mkdtemp(prefix="bu_profile_")
            browser_kwargs: dict[str, Any] = {
                "headless": True,
                "user_data_dir": tmp_profile,
                "storage_state": None,
                "keep_alive": False,
                "is_local": True,
                "use_cloud": False,
                "cloud_browser": False,
                "args": [
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-setuid-sandbox",
                    "--no-zygote",
                    "--disable-software-rasterizer",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--disable-default-apps",
                    "--disable-sync",
                    "--no-first-run",
                ],
            }

            if self._browser_executable_path:
                browser_kwargs["executable_path"] = self._browser_executable_path
                logging.debug("Launching BrowserSession with executable_path=%s", self._browser_executable_path)
            else:
                logging.debug("Launching BrowserSession without executable_path override")

            browser_session_kwargs = _filter_kwargs_for_callable(
                BrowserSession,
                browser_kwargs,
                callable_name="BrowserSession.__init__",
            )
            browser_session = BrowserSession(**browser_session_kwargs)
            context = self._prepare_run_context(task_run_id=task_run_id)

            agent_kwargs: dict[str, Any] = {
                "browser_session": browser_session,
                "task": self._compose_agent_task(task=task, content=persona.content),
                "llm": llm,
                "use_vision": True,
                "save_conversation_path": str(context.screenshots_dir),
                "use_judge": False,
                "generate_gif": False,
                "max_failures": self._settings.agent_max_failures,
                "final_response_after_failure": self._settings.agent_final_response_after_failure,
                "use_thinking": self._settings.agent_use_thinking,
            }
            compatible_agent_kwargs = _filter_kwargs_for_callable(
                Agent,
                agent_kwargs,
                callable_name="Agent.__init__",
            )
            agent = Agent(**compatible_agent_kwargs)

            history = await self._run_agent_with_compatible_loop(agent, max_steps=self._settings.max_steps)

            summary_payload = {
                "is_done": self._ensure_bool(self._safe_call(history, "is_done")),
                "is_successful": self._ensure_bool(self._safe_call(history, "is_successful")),
                "has_errors": self._ensure_bool(self._safe_call(history, "has_errors")),
                "number_of_steps": self._ensure_int(self._safe_call(history, "number_of_steps")),
                "total_duration_seconds": self._ensure_float(self._safe_call(history, "total_duration_seconds")),
                "final_result": self._to_serializable(self._safe_call(history, "final_result")),
            }

            screenshot_artifacts = self._save_screenshots(history, context)
            history_payload = self._build_history_payload(
                task=task,
                persona=persona,
                model_name=model_name,
                run_index=run_index,
                run_id=context.run_id,
                history=history,
                screenshots=screenshot_artifacts,
                summary=summary_payload,
            )

            context.history_path.write_text(
                json.dumps(history_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            return RunResult(
                model=model_name,
                run_index=run_index,
                is_done=summary_payload["is_done"],
                is_successful=summary_payload["is_successful"],
                has_errors=summary_payload["has_errors"],
                number_of_steps=summary_payload["number_of_steps"],
                total_duration_seconds=summary_payload["total_duration_seconds"],
                final_result=summary_payload["final_result"],
                history_path=str(context.history_path.resolve()),
            )

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return RunResult(
                model=model_name,
                run_index=run_index,
                is_done=False,
                is_successful=False,
                has_errors=True,
                number_of_steps=0,
                total_duration_seconds=0.0,
                final_result=str(exc),
                history_path="",
            )
        finally:
            await self._close_agent_resources(agent)
            if tmp_profile and os.path.isdir(tmp_profile):
                shutil.rmtree(tmp_profile, ignore_errors=True)

    def _patch_browser_use_click_handler_if_needed(self) -> None:
        if StandaloneBrowserAgentService._click_patch_applied:
            return
        if not self._settings.enable_click_timeout_fallback_patch:
            return

        try:
            from browser_use.browser.watchdogs.default_action_watchdog import DefaultActionWatchdog
        except Exception as exc:
            logging.debug("Skipped click fallback patch: cannot import DefaultActionWatchdog: %s", exc)
            return

        original = getattr(DefaultActionWatchdog, "on_ClickElementEvent", None)
        if original is None:
            return

        timeout_seconds = max(1.0, float(self._settings.patched_click_handler_timeout_seconds))

        async def on_ClickElementEvent(watchdog: Any, event: Any) -> Any:
            try:
                return await asyncio.wait_for(original(watchdog, event), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                watchdog.logger.warning(
                    "[patched-click] on_ClickElementEvent timed out after %.1fs; trying JS click fallback",
                    timeout_seconds,
                )

                node = getattr(event, "node", None)
                backend_node_id = getattr(node, "backend_node_id", None)
                if node is None or backend_node_id is None:
                    return {
                        "patched_js_click": False,
                        "patched_js_click_error": "missing backend_node_id for fallback",
                    }

                # Fallback: perform a direct JS click through CDP with tight per-call timeouts.
                try:
                    cdp_session = await asyncio.wait_for(
                        watchdog.browser_session.cdp_client_for_node(node),
                        timeout=5.0,
                    )
                    resolved = await asyncio.wait_for(
                        cdp_session.cdp_client.send.DOM.resolveNode(
                            params={"backendNodeId": backend_node_id},
                            session_id=cdp_session.session_id,
                        ),
                        timeout=5.0,
                    )

                    object_id = ((resolved or {}).get("object") or {}).get("objectId")
                    if not object_id:
                        raise RuntimeError("patched-click fallback could not resolve objectId")

                    await asyncio.wait_for(
                        cdp_session.cdp_client.send.Runtime.callFunctionOn(
                            params={
                                "functionDeclaration": "function() { this.click(); }",
                                "objectId": object_id,
                            },
                            session_id=cdp_session.session_id,
                        ),
                        timeout=5.0,
                    )

                    return {
                        "patched_js_click": True,
                        "backend_node_id": backend_node_id,
                    }
                except Exception as fallback_exc:
                    watchdog.logger.warning(
                        "[patched-click] JS click fallback failed; returning soft failure to continue run: %s",
                        fallback_exc,
                    )
                    return {
                        "patched_js_click": False,
                        "backend_node_id": backend_node_id,
                        "patched_js_click_error": str(fallback_exc),
                    }

        setattr(DefaultActionWatchdog, "on_ClickElementEvent", on_ClickElementEvent)
        StandaloneBrowserAgentService._click_patch_applied = True
        logging.info(
            "Applied click-timeout fallback patch | enabled=%s timeout=%.1fs",
            self._settings.enable_click_timeout_fallback_patch,
            timeout_seconds,
        )

    def _patch_browser_use_browser_state_handler_if_needed(self) -> None:
        if StandaloneBrowserAgentService._browser_state_patch_applied:
            return
        if not self._settings.enable_browser_state_timeout_fallback_patch:
            return

        try:
            from browser_use.browser.watchdogs.dom_watchdog import DOMWatchdog
            from browser_use.browser.views import BrowserStateSummary, PageInfo
            from browser_use.dom.views import SerializedDOMState
        except Exception as exc:
            logging.debug("Skipped browser-state fallback patch: import failure: %s", exc)
            return

        original = getattr(DOMWatchdog, "on_BrowserStateRequestEvent", None)
        if original is None:
            return

        timeout_seconds = max(5.0, float(self._settings.patched_browser_state_handler_timeout_seconds))

        async def _minimal_browser_state_summary(watchdog: Any, error_text: str) -> Any:
            cached_state = getattr(watchdog.browser_session, "_cached_browser_state_summary", None)
            if cached_state is not None:
                return cached_state

            try:
                page_url = await asyncio.wait_for(watchdog.browser_session.get_current_page_url(), timeout=2.0)
            except Exception:
                page_url = ""

            try:
                tabs_info = await asyncio.wait_for(watchdog.browser_session.get_tabs(), timeout=2.0)
            except Exception:
                tabs_info = []

            return BrowserStateSummary(
                dom_state=SerializedDOMState(_root=None, selector_map={}),
                url=page_url,
                title="Recovered",
                tabs=tabs_info,
                screenshot=None,
                page_info=PageInfo(
                    viewport_width=1280,
                    viewport_height=720,
                    page_width=1280,
                    page_height=720,
                    scroll_x=0,
                    scroll_y=0,
                    pixels_above=0,
                    pixels_below=0,
                    pixels_left=0,
                    pixels_right=0,
                ),
                pixels_above=0,
                pixels_below=0,
                browser_errors=[error_text],
                is_pdf_viewer=False,
                recent_events=None,
                pending_network_requests=[],
                pagination_buttons=[],
            )

        async def on_BrowserStateRequestEvent(watchdog: Any, event: Any) -> Any:
            try:
                return await asyncio.wait_for(original(watchdog, event), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                watchdog.logger.warning(
                    "[patched-browser-state] on_BrowserStateRequestEvent timed out after %.1fs; using recovery state",
                    timeout_seconds,
                )
                return await _minimal_browser_state_summary(
                    watchdog,
                    f"patched-browser-state-timeout-after-{timeout_seconds:.1f}s",
                )
            except Exception as exc:
                watchdog.logger.warning(
                    "[patched-browser-state] on_BrowserStateRequestEvent failed; using recovery state: %s",
                    exc,
                )
                return await _minimal_browser_state_summary(
                    watchdog,
                    f"patched-browser-state-exception:{exc}",
                )

        setattr(DOMWatchdog, "on_BrowserStateRequestEvent", on_BrowserStateRequestEvent)
        StandaloneBrowserAgentService._browser_state_patch_applied = True
        logging.info(
            "Applied browser-state timeout fallback patch | enabled=%s timeout=%.1fs",
            self._settings.enable_browser_state_timeout_fallback_patch,
            timeout_seconds,
        )

    def _prepare_run_context(self, task_run_id: str) -> RunContext:
        run_uuid = str(uuid.uuid4())
        run_id = f"{task_run_id}_{run_uuid}"
        history_path = self._output_dir / f"{run_id}.json"
        screenshots_dir = self._output_dir / "screenshots" / run_id
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        return RunContext(run_id=run_id, history_path=history_path, screenshots_dir=screenshots_dir)

    def _get_browser_use_llm(self, model_name: str) -> Any:
        provider = self._resolve_provider_from_model(model_name)
        class_map = {
            "deepseek": "ChatDeepSeek",
            "openai": "ChatOpenAI",
            "anthropic": "ChatAnthropic",
            "gemini": "ChatGemini",
            "ollama": "ChatOllama",
        }

        class_name = class_map[provider]
        try:
            llm_module = importlib.import_module("browser_use.llm")
            llm_cls = getattr(llm_module, class_name)
        except (ImportError, AttributeError) as exc:
            raise RuntimeError(
                "browser-use LLM adapters are unavailable. Install browser-use with required extras."
            ) from exc

        kwargs: dict[str, Any] = {"model": model_name}
        if provider != "ollama":
            api_key = self._api_key_for_provider(provider)
            if not api_key:
                raise RuntimeError(f"Missing API key for provider '{provider}' and model '{model_name}'.")
            kwargs["api_key"] = api_key
            base_url = self._base_url_for_provider(provider)
            if base_url:
                kwargs["base_url"] = base_url
            kwargs["temperature"] = self._settings.llm_temperature

        llm_kwargs = _filter_kwargs_for_callable(
            llm_cls,
            kwargs,
            callable_name=f"{class_name}.__init__",
        )
        return llm_cls(**llm_kwargs)

    def _resolve_provider_from_model(self, model_name: str) -> str:
        normalized = (model_name or "").strip().lower()
        if "deepseek" in normalized:
            return "deepseek"
        if normalized.startswith("claude"):
            return "anthropic"
        if "gemini" in normalized:
            return "gemini"
        if (
            "ollama" in normalized
            or normalized.startswith("llama")
            or normalized.startswith("mistral")
            or normalized.startswith("phi")
        ):
            return "ollama"
        if normalized.startswith("gpt") or normalized.startswith("o"):
            return "openai"
        return "openai"

    def _api_key_for_provider(self, provider: str) -> str | None:
        if provider == "deepseek":
            return self._settings.deepseek_api_key
        if provider == "openai":
            return self._settings.openai_api_key
        if provider == "anthropic":
            return self._settings.anthropic_api_key
        if provider == "gemini":
            return self._settings.gemini_api_key
        return None

    def _base_url_for_provider(self, provider: str) -> str | None:
        if provider == "deepseek":
            return self._settings.deepseek_base_url
        if provider == "openai":
            return self._settings.openai_base_url or self._settings.llm_base_url
        if provider == "anthropic":
            return self._settings.anthropic_base_url
        if provider == "gemini":
            return self._settings.gemini_base_url
        if provider == "ollama":
            return self._settings.ollama_base_url
        return None

    async def _run_agent_with_compatible_loop(self, agent: Any, *, max_steps: int) -> Any:
        if sys.platform.startswith("win") and self._settings.force_threaded_run_on_windows:
            return await asyncio.to_thread(self._run_agent_in_proactor_loop, agent, max_steps)
        return await agent.run(max_steps=max_steps)

    def _run_agent_in_proactor_loop(self, agent: Any, max_steps: int) -> Any:
        policy = asyncio.WindowsProactorEventLoopPolicy()
        loop = policy.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(agent.run(max_steps=max_steps))
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            asyncio.set_event_loop(None)
            loop.close()

    async def _close_resource(self, resource: Any) -> None:
        if resource is None:
            return
        for method_name in ("close", "aclose", "shutdown", "stop", "__aexit__"):
            if not hasattr(resource, method_name):
                continue
            try:
                close_result = getattr(resource, method_name)()
                if asyncio.iscoroutine(close_result):
                    await asyncio.wait_for(
                        close_result,
                        timeout=self._settings.resource_close_timeout_seconds,
                    )
            except asyncio.TimeoutError:
                logging.debug(
                    "Timed out while closing resource with method=%s timeout=%ss",
                    method_name,
                    self._settings.resource_close_timeout_seconds,
                )
            except Exception:
                pass
            break

    async def _close_agent_resources(self, agent: Any) -> None:
        if agent is None:
            return
        await self._close_resource(agent)
        await self._close_resource(getattr(agent, "browser_session", None))

    def _compose_agent_task(self, *, task: TaskConfig, content: str) -> str:
        persona = (content or "").strip()
        url = (task.url or "").strip()
        name = (task.name or "").strip()
        description = (task.description or "").strip()

        if description:
            task_instruction = description
            if name and name.lower() not in description.lower():
                task_instruction = f"{name}: {description}"
        elif name:
            task_instruction = name
        else:
            task_instruction = "Complete the task"

        task_prompt = task_instruction
        if url:
            task_prompt = f"{task_prompt} (Website: {url})"

        prompt = f"Complete this task based on the following persona: {task_prompt}"
        if persona:
            prompt = f"{prompt}\nPersona: {persona}"
        return prompt

    def _save_screenshots(self, history: Any, context: RunContext) -> list[ScreenshotArtifact]:
        if not self._settings.enable_screenshots:
            return []

        artifacts: list[ScreenshotArtifact] = []

        screenshot_paths_attr = getattr(history, "screenshot_paths", None)
        if callable(screenshot_paths_attr):
            try:
                path_items = screenshot_paths_attr(return_none_if_not_screenshot=False)
            except TypeError:
                path_items = screenshot_paths_attr()
            except Exception:
                path_items = None

            if path_items:
                cleaned_paths = [Path(str(p)) for p in path_items if p]
                if self._settings.max_screenshots > 0:
                    cleaned_paths = cleaned_paths[: self._settings.max_screenshots]

                for index, source_path in enumerate(cleaned_paths, start=1):
                    try:
                        if not source_path.exists():
                            continue
                        image_bytes = source_path.read_bytes()
                    except Exception:
                        continue

                    extension = source_path.suffix.lower() if source_path.suffix else ".png"
                    target_path = context.screenshots_dir / f"screenshot_{index:03d}{extension}"
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    target_path.write_bytes(image_bytes)
                    artifacts.append(ScreenshotArtifact(path=str(target_path), base64_content=None))

                if artifacts:
                    return artifacts

        screenshots_attr = getattr(history, "screenshots", None)
        if callable(screenshots_attr):
            try:
                screenshots = screenshots_attr()
            except Exception:
                screenshots = None
        else:
            screenshots = screenshots_attr

        if not screenshots:
            return artifacts

        screenshot_list = list(screenshots)
        if self._settings.max_screenshots > 0:
            screenshot_list = screenshot_list[: self._settings.max_screenshots]

        for index, screenshot_data in enumerate(screenshot_list, start=1):
            if not screenshot_data:
                continue

            encoded_str = self._extract_base64_data(screenshot_data)
            if not encoded_str:
                continue

            try:
                image_bytes = base64.b64decode(encoded_str)
            except Exception:
                continue

            extension = self._guess_image_extension(screenshot_data)
            target_path = context.screenshots_dir / f"screenshot_{index:03d}{extension}"
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(image_bytes)
            artifacts.append(ScreenshotArtifact(path=str(target_path), base64_content=None))

        return artifacts

    def _extract_base64_data(self, screenshot_data: Any) -> str:
        if isinstance(screenshot_data, (bytes, bytearray)):
            return base64.b64encode(screenshot_data).decode("utf-8")

        if isinstance(screenshot_data, str):
            _, _, encoded = screenshot_data.partition(",")
            return encoded or screenshot_data

        if isinstance(screenshot_data, dict):
            for key in ("data", "content", "image"):
                value = screenshot_data.get(key)
                if isinstance(value, str):
                    return value

        return str(screenshot_data)

    def _guess_image_extension(self, screenshot_data: Any) -> str:
        if isinstance(screenshot_data, str):
            lower = screenshot_data.lower()
            if "image/jpeg" in lower or "image/jpg" in lower:
                return ".jpg"
            if "image/webp" in lower:
                return ".webp"
        return ".png"

    def _extract_history_items(self, history: Any) -> list[Any]:
        if hasattr(history, "history") and isinstance(history.history, list):
            return history.history
        if hasattr(history, "__iter__") and not isinstance(history, (str, bytes)):
            try:
                return list(history)
            except Exception:
                return []
        return []

    def _extract_action_descriptions(self, history: Any, max_items: int) -> list[Any]:
        descriptions: list[Any] = [None] * max_items
        history_items = self._extract_history_items(history)

        for idx, item in enumerate(history_items[:max_items]):
            parts: list[str] = []
            if hasattr(item, "state") and hasattr(item.state, "result"):
                result = item.state.result
                if isinstance(result, str) and result.strip():
                    parts.append(result.strip()[:200])
            if hasattr(item, "model_output"):
                model_output = item.model_output
                action = getattr(model_output, "action", None)
                if action is not None:
                    parts.append(f"Action: {str(action)[:150]}")
            if parts:
                descriptions[idx] = " | ".join(parts)

        return descriptions

    def _build_history_payload(
        self,
        *,
        task: TaskConfig,
        persona: PersonaConfig,
        model_name: str,
        run_index: int,
        run_id: str,
        history: Any,
        screenshots: list[ScreenshotArtifact],
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        step_descriptions = self._extract_action_descriptions(history, max_items=len(screenshots))

        return {
            "metadata": {
                "id": run_id,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "task": {
                    "name": task.name,
                    "description": task.description,
                    "url": task.url,
                },
                "persona": {
                    "value": persona.value,
                    "content": persona.content,
                },
                "model": model_name,
                "run_index": run_index,
            },
            "summary": {
                "is_done": self._ensure_bool(summary.get("is_done")),
                "is_successful": self._ensure_bool(summary.get("is_successful")),
                "has_errors": self._ensure_bool(summary.get("has_errors")),
                "number_of_steps": self._ensure_int(summary.get("number_of_steps")),
                "total_duration_seconds": self._ensure_float(summary.get("total_duration_seconds")),
                "final_result": self._to_serializable(summary.get("final_result")),
            },
            "details": {
                "screenshots": [_to_portable_path(Path(artifact.path)) for artifact in screenshots],
                "step_descriptions": step_descriptions,
                "model_outputs": self._to_serializable(self._safe_call(history, "model_outputs")),
                "last_action": self._to_serializable(self._safe_call(history, "last_action")),
                "structured_output": self._to_serializable(getattr(history, "structured_output", None)),
            },
        }

    def _safe_call(self, obj: Any, method_name: str) -> Any:
        attr = getattr(obj, method_name, None)
        if callable(attr):
            try:
                return attr()
            except Exception:
                return None
        return attr

    def _to_serializable(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(k): self._to_serializable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._to_serializable(item) for item in value]
        if hasattr(value, "model_dump") and callable(getattr(value, "model_dump")):
            try:
                return self._to_serializable(value.model_dump())
            except Exception:
                return str(value)
        if hasattr(value, "dict") and callable(getattr(value, "dict")):
            try:
                return self._to_serializable(value.dict())
            except Exception:
                return str(value)
        if hasattr(value, "__dict__"):
            try:
                return self._to_serializable(vars(value))
            except Exception:
                return str(value)
        return str(value)

    def _ensure_bool(self, value: Any) -> bool:
        return bool(value)

    def _ensure_int(self, value: Any) -> int:
        try:
            return int(value)
        except Exception:
            return 0

    def _ensure_float(self, value: Any) -> float:
        try:
            return float(value)
        except Exception:
            return 0.0


async def run_experiment(
    run_times: int,
    strict_schema: bool,
    settings: StandaloneSettings,
    website_url: str | None = None,
) -> None:
    _validate_experiment_config(run_times)
    tasks = _override_tasks_website_url(TASKS, website_url)

    total_jobs = len(tasks) * len(PERSONAS) * len(MODELS) * run_times
    logging.info(
        "Starting experiment | tasks=%d personas=%d models=%d run_times=%d total_jobs=%d output_dir=%s",
        len(tasks),
        len(PERSONAS),
        len(MODELS),
        run_times,
        total_jobs,
        settings.output_dir,
    )

    if not settings.enable_screenshots:
        logging.warning("BROWSER_AGENT_ENABLE_SCREENSHOTS is false. details.screenshots will be empty.")
    elif settings.max_screenshots > 0:
        logging.info(
            "BROWSER_AGENT_MAX_SCREENSHOTS=%d. Only the first N screenshots per run will be saved.",
            settings.max_screenshots,
        )
    else:
        logging.info("BROWSER_AGENT_MAX_SCREENSHOTS=%d. Screenshot saving is unlimited.", settings.max_screenshots)

    if website_url is not None:
        logging.info("Applying website URL override to all tasks | website_url=%s", tasks[0].url)

    service = StandaloneBrowserAgentService(settings=settings)
    service.validate_model_credentials(MODELS)

    generated_files: list[Path] = []
    skipped_failed_runs = 0
    skipped_invalid_runs = 0
    failed_tasks = 0

    for task_index, task in enumerate(tasks, start=1):
        run_id = _build_run_id(task.name, task_index)

        logging.info(
            "Running task %d/%d | task=%s url=%s run_id=%s",
            task_index,
            len(tasks),
            task.name,
            task.url,
            run_id,
        )

        try:
            results = await service.run_task(
                task=task,
                personas=PERSONAS,
                models=MODELS,
                run_times=run_times,
                task_run_id=run_id,
            )
        except Exception as exc:
            failed_tasks += 1
            logging.exception(
                "Task execution failed, continuing with next task | task=%s run_id=%s error=%s",
                task.name,
                run_id,
                exc,
            )
            continue

        if not results:
            failed_tasks += 1
            logging.warning(
                "No results returned for task, continuing with next task | task=%s run_id=%s",
                task.name,
                run_id,
            )
            continue

        for result in results:
            logging.info(_format_result_line(result))

            if bool(result.has_errors) or not bool(result.is_successful):
                skipped_failed_runs += 1
                _cleanup_failed_result_artifacts(result)
                logging.warning(
                    "Skipping failed run result | task=%s model=%s run_index=%s",
                    task.name,
                    result.model,
                    result.run_index,
                )
                continue

            history_path_raw = str(getattr(result, "history_path", "") or "").strip()
            if not history_path_raw:
                skipped_invalid_runs += 1
                logging.warning(
                    "Skipping result without history_path | task=%s model=%s run_index=%s",
                    task.name,
                    result.model,
                    result.run_index,
                )
                continue

            history_file = _resolve_history_file(history_path_raw)
            if not history_file.exists() or not history_file.is_file():
                skipped_invalid_runs += 1
                logging.warning(
                    "Skipping result with missing history file | task=%s model=%s run_index=%s history_path=%s",
                    task.name,
                    result.model,
                    result.run_index,
                    history_file,
                )
                continue

            if strict_schema:
                try:
                    _validate_history_json(history_file)
                except Exception as exc:
                    skipped_invalid_runs += 1
                    removed_paths = _cleanup_history_artifacts(history_file)
                    logging.warning(
                        "Skipping run due to schema validation failure | task=%s model=%s run_index=%s error=%s removed=%s",
                        task.name,
                        result.model,
                        result.run_index,
                        exc,
                        [str(path) for path in removed_paths],
                    )
                    continue

            generated_files.append(history_file)

    unique_files = sorted({path.resolve() for path in generated_files})
    logging.info(
        "Experiment finished | generated_json_files=%d skipped_failed_runs=%d skipped_invalid_runs=%d failed_tasks=%d",
        len(unique_files),
        skipped_failed_runs,
        skipped_invalid_runs,
        failed_tasks,
    )
    for history_file in unique_files:
        print(str(history_file))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run browser-agent experiments across TASKS x PERSONAS x MODELS and "
            "persist artifacts from this standalone script."
        )
    )
    parser.add_argument(
        "--run-times",
        type=int,
        default=RUN_TIMES,
        help="Override RUN_TIMES from this file.",
    )
    parser.add_argument(
        "--no-strict-schema",
        action="store_true",
        help="Skip strict JSON field validation after each run.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG logging.",
    )
    parser.add_argument(
        "--website-url",
        type=str,
        default=None,
        help="Override TaskConfig.url for all tasks in this run.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for generated JSON and screenshots. Auto-created if missing.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    _bootstrap_env()
    _configure_logging(verbose=args.verbose)

    settings = StandaloneSettings.from_env(output_dir_override=args.output_dir)
    logging.info("Using standalone output directory: %s", settings.output_dir)

    try:
        asyncio.run(
            run_experiment(
                run_times=args.run_times,
                strict_schema=not args.no_strict_schema,
                settings=settings,
                website_url=args.website_url,
            )
        )
    except KeyboardInterrupt:
        logging.warning("Experiment interrupted by user")
    except Exception as exc:
        logging.error("Experiment failed: %s", exc)
        raise


if __name__ == "__main__":
    main()
