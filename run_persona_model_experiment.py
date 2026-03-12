from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List


SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR: Path | None = None
ROOT_DIR: Path | None = None
BACKEND_DIR_ENV = "BROWSER_AGENT_BACKEND_DIR"


def _normalize_backend_dir(candidate: Path) -> Path | None:
    resolved = candidate.resolve()
    if (resolved / "app").is_dir():
        return resolved

    nested_backend = resolved / "backend"
    if (nested_backend / "app").is_dir():
        return nested_backend.resolve()

    return None


def _resolve_backend_and_root_dirs(explicit_backend_dir: str | None) -> tuple[Path | None, Path | None]:
    candidates: list[Path] = []

    if explicit_backend_dir:
        candidates.append(Path(explicit_backend_dir))

    env_backend_dir = os.getenv(BACKEND_DIR_ENV)
    if env_backend_dir:
        candidates.append(Path(env_backend_dir))

    candidates.extend([SCRIPT_DIR, SCRIPT_DIR.parent, Path.cwd(), Path.cwd().parent])

    seen: set[Path] = set()
    for candidate in candidates:
        normalized = _normalize_backend_dir(candidate)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        return normalized, normalized.parent

    return None, None


def _configure_backend_import_path(backend_dir: Path | None) -> None:
    if backend_dir is None:
        return

    backend_dir_str = str(backend_dir)
    if backend_dir_str not in sys.path:
        sys.path.insert(0, backend_dir_str)


def _strip_wrapping_quotes(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}:
        return stripped[1:-1]
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


def _bootstrap_env(backend_dir: Path | None, root_dir: Path | None) -> None:
    env_candidates: list[Path] = []
    env_candidates.extend([Path.cwd() / ".env", SCRIPT_DIR / ".env"])

    if backend_dir is not None:
        env_candidates.append(backend_dir / ".env")
    if root_dir is not None:
        env_candidates.append(root_dir / ".env")

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
class BackendBindings:
    get_settings: Any
    BrowserAgentPersona: Any
    BrowserAgentRunRequest: Any
    BrowserAgentTask: Any
    BrowserAgentService: Any


def _import_backend_bindings() -> BackendBindings:
    try:
        from app.core.config import get_settings
        from app.schemas.browser_agent import BrowserAgentPersona, BrowserAgentRunRequest, BrowserAgentTask
        from app.services.browser_agent_runner import BrowserAgentService
    except Exception as exc:
        raise RuntimeError(
            "Failed to import app modules. Provide --backend-dir <path-to-backend>, "
            f"set {BACKEND_DIR_ENV}, or install the backend package in this environment."
        ) from exc

    return BackendBindings(
        get_settings=get_settings,
        BrowserAgentPersona=BrowserAgentPersona,
        BrowserAgentRunRequest=BrowserAgentRunRequest,
        BrowserAgentTask=BrowserAgentTask,
        BrowserAgentService=BrowserAgentService,
    )


@dataclass(frozen=True)
class TaskConfig:
    name: str
    url: str
    description: str = ""


@dataclass(frozen=True)
class PersonaConfig:
    value: str
    content: str


# ---------------------------------------------------------------------------
# Edit this block only.
# Team members can safely change tasks/personas/models/run_times here.
# ---------------------------------------------------------------------------
TASKS: List[TaskConfig] = [
    TaskConfig(
        name="Book flight",
        url="http://34.55.136.249:3000/flight",
        description="Book a flight from ORD to LAX.",
    ),
    TaskConfig(
        name="Rent a car",
        url="http://34.55.136.249:3000/zoomcar",
        description="Rent a car for a family vacation.",
    )

]

PERSONAS: List[PersonaConfig] = [
    PersonaConfig(
        value="Frugality",
        content="You maximize value for money and avoid unnecessary spending.",
    ),
    PersonaConfig(
        value="Sustainability",
        content="You prioritize environmentally friendly and socially responsible choices.",
    ),
    PersonaConfig(
        value="Comfort",
        content="You prioritize a comfortable and enjoyable travel experience.",
    ),
    PersonaConfig(
        value="Luxury",
        content="You prioritize comfort and premium experiences, even at higher costs.",
    ),
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


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(levelname)s] %(name)s - %(message)s",
        force=True,
    )


def _slugify(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "_", (value or "").strip())
    token = token.strip("_")
    return token.lower() or "task"


def _build_run_id(task_name: str, task_index: int) -> str:
    from datetime import datetime, timezone

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"exp_{task_index:02d}_{_slugify(task_name)}_{stamp}"


def _resolve_history_file(path_str: str) -> Path:
    candidate = Path(path_str)
    if candidate.is_absolute() and candidate.exists():
        return candidate.resolve()

    checks = [(Path.cwd() / candidate).resolve()]
    if BACKEND_DIR is not None:
        checks.append((BACKEND_DIR / candidate).resolve())

    for item in checks:
        if item.exists() and item.is_file():
            return item

    return checks[0]


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
        if BACKEND_DIR is not None:
            possible.append((BACKEND_DIR / candidate).resolve())
        possible.append((history_file.parent / candidate).resolve())

        parts = [part for part in candidate.parts if part not in {"", "."}]
        if "screenshots" in parts:
            idx = parts.index("screenshots")
            suffix = Path(*parts[idx + 1 :]) if idx + 1 < len(parts) else None
            if suffix is not None:
                possible.append((history_file.parent / "screenshots" / suffix).resolve())
                if BACKEND_DIR is not None:
                    possible.extend(
                        [
                            (BACKEND_DIR / "browser_agent_runs" / "screenshots" / suffix).resolve(),
                            (BACKEND_DIR / "history_logs" / "screenshots" / suffix).resolve(),
                        ]
                    )

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


def _build_request(task: TaskConfig, run_times: int, bindings: BackendBindings) -> Any:
    personas = [
        bindings.BrowserAgentPersona(value=item.value, content=item.content)
        for item in PERSONAS
    ]

    return bindings.BrowserAgentRunRequest(
        task=bindings.BrowserAgentTask(name=task.name, url=task.url, description=task.description),
        personas=personas,
        models=list(MODELS),
        run_times=run_times,
    )


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


def _format_result_line(result: Any) -> str:
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


def _cleanup_failed_result_artifacts(result: Any) -> None:
    history_path_raw = str(getattr(result, "history_path", "") or "").strip()
    if not history_path_raw:
        return

    # Only clean up explicit run artifacts; never touch cwd placeholders.
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


async def run_experiment(
    run_times: int,
    strict_schema: bool,
    bindings: BackendBindings,
    website_url: str | None = None,
) -> None:
    _validate_experiment_config(run_times)
    tasks = _override_tasks_website_url(TASKS, website_url)

    settings = bindings.get_settings()
    if not getattr(settings, "BROWSER_AGENT_ENABLE_SCREENSHOTS", True):
        raise RuntimeError(
            "BROWSER_AGENT_ENABLE_SCREENSHOTS is false. "
            "Enable screenshots to keep artifacts identical to browser-agent run outputs."
        )

    total_jobs = len(tasks) * len(PERSONAS) * len(MODELS) * run_times
    logging.info(
        "Starting experiment | tasks=%d personas=%d models=%d run_times=%d total_jobs=%d",
        len(tasks),
        len(PERSONAS),
        len(MODELS),
        run_times,
        total_jobs,
    )

    if website_url is not None:
        logging.info("Applying website URL override to all tasks | website_url=%s", tasks[0].url)

    service = bindings.BrowserAgentService()
    generated_files: list[Path] = []
    skipped_failed_runs = 0
    skipped_invalid_runs = 0
    failed_tasks = 0

    for task_index, task in enumerate(tasks, start=1):
        request = _build_request(task, run_times=run_times, bindings=bindings)
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
            results = await service.run(request, run_id=run_id)
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
            "persist artifacts using the exact BrowserAgentService format."
        )
    )
    parser.add_argument(
        "--backend-dir",
        type=str,
        default=None,
        help=(
            "Path to backend directory (or repository root containing backend/) that provides app.* modules. "
            f"Can also be set via {BACKEND_DIR_ENV}."
        ),
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
    return parser.parse_args()


def main() -> None:
    global BACKEND_DIR, ROOT_DIR

    args = parse_args()

    BACKEND_DIR, ROOT_DIR = _resolve_backend_and_root_dirs(args.backend_dir)
    _configure_backend_import_path(BACKEND_DIR)
    _bootstrap_env(BACKEND_DIR, ROOT_DIR)
    bindings = _import_backend_bindings()

    _configure_logging(verbose=args.verbose)

    if BACKEND_DIR is not None:
        logging.info("Using backend directory: %s", BACKEND_DIR)
    else:
        logging.info("Using installed backend package (no local backend dir detected)")

    try:
        asyncio.run(
            run_experiment(
                run_times=args.run_times,
                strict_schema=not args.no_strict_schema,
                bindings=bindings,
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
