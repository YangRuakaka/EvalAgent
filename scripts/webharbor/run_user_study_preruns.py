"""Run the three CHI extension cases under four personas each.

Outputs are written to a staging tree with the same data1/data2/data3 layout
used by EvalAgent.  Existing backend/history_logs data are never modified.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import os
import re
import shutil
import socket
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import browseruse_compat as legacy
from user_study_prerun_catalog import DATASETS, iter_runs


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "browser_agent_runs_userstudy_preruns_v1"
DEFAULT_STATUS_PATH = DEFAULT_OUTPUT_ROOT / "run_status.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporary, path)


def _stable_id(run: dict[str, Any]) -> str:
    return f"userstudy_{_slug(run['case_id'])}_{run['run_index']:02d}_{run['persona']['persona_id']}"


def _stable_output_path(output_root: Path, run: dict[str, Any]) -> Path:
    return output_root / run["dataset"] / f"{_stable_id(run)}.json"


def _is_reusable(path: Path, run: dict[str, Any], model: str) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        summary = payload["summary"]
        metadata = payload["metadata"]
        persona = metadata["persona"]
        return bool(
            summary["is_done"]
            and summary["is_successful"]
            and not summary["has_errors"]
            and metadata["model"] == model
            and metadata["task"]["description"] == run["task"]
            and persona["value"] == run["persona"]["value"]
            and persona["content"] == run["persona"]["content"]
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError):
        return False


def _archive_existing(target: Path, attempt_dir: Path) -> None:
    if not target.exists():
        return
    archive_dir = attempt_dir / "replaced"
    archive_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(target), str(archive_dir / target.name))


def _promote_attempt(
    attempt_path: Path,
    output_root: Path,
    run: dict[str, Any],
) -> Path:
    """Convert one BrowserUse output into a stable EvalAgent dataset file."""

    payload = json.loads(attempt_path.read_text(encoding="utf-8"))
    dataset_dir = output_root / run["dataset"]
    attempt_dir = attempt_path.parent
    old_id = str(payload["metadata"]["id"])
    new_id = _stable_id(run)

    old_screenshot_dir = attempt_dir / "screenshots" / old_id
    new_screenshot_dir = dataset_dir / "screenshots" / new_id
    if new_screenshot_dir.exists():
        archived_screenshots = attempt_dir / "replaced" / new_screenshot_dir.name
        archived_screenshots.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(new_screenshot_dir), str(archived_screenshots))
    if old_screenshot_dir.is_dir():
        new_screenshot_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_screenshot_dir), str(new_screenshot_dir))

    screenshot_paths: list[str] = []
    for index, _ in enumerate(payload["details"]["screenshots"], start=1):
        candidates = sorted(new_screenshot_dir.glob(f"screenshot_{index:03d}.*"))
        if candidates:
            screenshot_paths.append(candidates[0].relative_to(REPO_ROOT).as_posix())
    payload["details"]["screenshots"] = screenshot_paths
    payload["details"]["step_descriptions"] = payload["details"][
        "step_descriptions"
    ][: len(screenshot_paths)]

    payload["metadata"].update(
        {
            "id": new_id,
            "task": {
                "name": f"{run['case_id']} | {run['task_name']}",
                "description": run["task"],
                "url": run["url"],
            },
            "persona": {
                "value": run["persona"]["value"],
                "content": run["persona"]["content"],
            },
            "run_index": run["run_index"],
        }
    )

    target = _stable_output_path(output_root, run)
    _archive_existing(target, attempt_dir)
    _write_json(target, payload)
    legacy._validate_legacy_format(target, legacy.DEFAULT_REFERENCE_CASE.resolve())
    return target


def _select_runs(args: argparse.Namespace) -> list[dict[str, Any]]:
    runs = iter_runs()
    if args.dataset:
        allowed = set(args.dataset)
        runs = [run for run in runs if run["dataset"] in allowed]
    if args.case:
        requested = set(args.case)
        runs = [run for run in runs if run["run_id"] in requested]
        missing = requested - {run["run_id"] for run in runs}
        if missing:
            raise ValueError(f"Unknown or filtered run IDs: {sorted(missing)}")
    if args.webharbor_host:
        runs = [
            {
                **run,
                "url": _replace_url_host(run["url"], args.webharbor_host),
                "reset_url": _replace_url_host(
                    run["reset_url"], args.webharbor_host
                ),
            }
            for run in runs
        ]
    return runs


def _replace_url_host(url: str, host_override: str) -> str:
    """Replace localhost while preserving each WebHarbor service port/path."""

    source = urlparse(url)
    override_text = (
        host_override if "://" in host_override else f"{source.scheme}://{host_override}"
    )
    override = urlparse(override_text)
    if not override.hostname:
        raise ValueError(f"Invalid --webharbor-host: {host_override}")
    hostname = (
        f"[{override.hostname}]" if ":" in override.hostname else override.hostname
    )
    port = source.port
    netloc = f"{hostname}:{port}" if port is not None else hostname
    return urlunparse(
        (
            override.scheme or source.scheme,
            netloc,
            source.path,
            source.params,
            source.query,
            source.fragment,
        )
    )


def _plan_payload(args: argparse.Namespace, runs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "purpose": "CHI user-study extension: three new domains, four personas each",
        "model": args.model,
        "max_steps": args.max_steps,
        "output_root": str(args.output_root.resolve()),
        "experimental_controls": {
            "fixed_within_dataset": [
                "task",
                "website snapshot",
                "model",
                "max_steps",
                "browser tools",
            ],
            "varied_within_dataset": ["persona value", "persona description"],
            "evalagent_preset": (
                "Not encoded in these runs; Preset A/B/C is selected later in the UI."
            ),
        },
        "datasets": [
            {
                "dataset": dataset["dataset"],
                "case_id": dataset["case_id"],
                "domain": dataset["domain"],
                "site": dataset["site"],
                "url": next(
                    run["url"]
                    for run in runs
                    if run["dataset"] == dataset["dataset"]
                ),
                "reset_url": next(
                    run["reset_url"]
                    for run in runs
                    if run["dataset"] == dataset["dataset"]
                ),
                "task_name": dataset["task_name"],
                "task": dataset["task"],
                "personas": [
                    {
                        "run_id": next(
                            run["run_id"]
                            for run in runs
                            if run["dataset"] == dataset["dataset"]
                            and run["persona"]["persona_id"] == persona["persona_id"]
                        ),
                        **persona,
                    }
                    for persona in dataset["personas"]
                    if any(
                        run["dataset"] == dataset["dataset"]
                        and run["persona"]["persona_id"] == persona["persona_id"]
                        for run in runs
                    )
                ],
            }
            for dataset in DATASETS
            if any(run["dataset"] == dataset["dataset"] for run in runs)
        ],
    }


def _preflight(model: str, runs: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    try:
        version = importlib.metadata.version("browser-use")
        if version != legacy.LATEST_BROWSER_USE_VERSION:
            errors.append(
                f"browser-use must be {legacy.LATEST_BROWSER_USE_VERSION}; found {version}"
            )
    except importlib.metadata.PackageNotFoundError:
        errors.append("browser-use is not installed in this Python environment")

    if not legacy.DEFAULT_REFERENCE_CASE.is_file():
        errors.append(f"reference case is missing: {legacy.DEFAULT_REFERENCE_CASE}")

    if legacy._find_browser_executable() is None:
        errors.append(
            "no Chrome/Chromium executable found; install Playwright Chromium into "
            f"{os.environ.get('PLAYWRIGHT_BROWSERS_PATH')}"
        )

    legacy._load_project_env()
    key_name = "DEEPSEEK_API_KEY" if "deepseek" in model.lower() else "OPENAI_API_KEY"
    api_key = os.getenv(key_name)
    if not api_key:
        errors.append(f"{key_name} is missing (put it in backend/.env; do not paste it in chat)")
    elif key_name == "OPENAI_API_KEY":
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, timeout=15.0, max_retries=0)
            client.models.list()
        except Exception as exc:
            status = getattr(exc, "status_code", "unknown")
            errors.append(
                "OPENAI_API_KEY validation failed before browser launch: "
                f"{type(exc).__name__} (HTTP status: {status})"
            )

    checked_urls: set[str] = set()
    for run in runs:
        if run["url"] in checked_urls:
            continue
        checked_urls.add(run["url"])
        legacy.TASK = {
            "name": run["task_name"],
            "description": run["task"],
            "url": run["url"],
            "reset_url": run["reset_url"],
        }
        try:
            legacy._check_webharbor()
        except Exception as exc:
            errors.append(f"{run['site']} unavailable at {run['url']}: {type(exc).__name__}: {exc}")

    checked_reset_ports: set[tuple[str, int]] = set()
    for run in runs:
        parsed = urlparse(run["reset_url"])
        host = parsed.hostname or "localhost"
        port = parsed.port or 80
        address = (host, port)
        if address in checked_reset_ports:
            continue
        checked_reset_ports.add(address)
        try:
            with socket.create_connection(address, timeout=3):
                pass
        except OSError as exc:
            errors.append(
                f"WebHarbor reset service unavailable at {host}:{port}: "
                f"{type(exc).__name__}: {exc}"
            )
    return errors


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run 3 new-domain x 4-persona pre-runs into an EvalAgent staging tree."
    )
    parser.add_argument("--model", default="gpt-4.1")
    parser.add_argument("--max-steps", type=int, default=25)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--status-path", type=Path, default=DEFAULT_STATUS_PATH)
    parser.add_argument(
        "--webharbor-host",
        help=(
            "Remote WebHarbor hostname or origin, e.g. 203.0.113.10 or "
            "http://webharbor.example. Existing service ports and paths are preserved."
        ),
    )
    parser.add_argument(
        "--dataset", action="append", choices=["data1", "data2", "data3"]
    )
    parser.add_argument("--case", action="append", help="Exact run_id from --plan-only")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    args.output_root = args.output_root.resolve()
    args.status_path = args.status_path.resolve()
    runs = _select_runs(args)
    plan = _plan_payload(args, runs)
    _write_json(args.output_root / "run_plan.json", plan)

    if args.plan_only:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    preflight_errors = _preflight(args.model, runs)
    if args.preflight or preflight_errors:
        if preflight_errors:
            print("PREFLIGHT FAILED", file=sys.stderr)
            for error in preflight_errors:
                print(f"- {error}", file=sys.stderr)
            return 1
        print("PREFLIGHT PASS")
        return 0

    statuses: list[dict[str, Any]] = []
    for run in runs:
        target = _stable_output_path(args.output_root, run)
        reused = not args.no_resume and _is_reusable(target, run, args.model)
        statuses.append(
            {
                "run_id": run["run_id"],
                "dataset": run["dataset"],
                "domain": run["domain"],
                "persona": run["persona"]["value"],
                "state": "completed" if reused else "pending",
                "output": str(target) if reused else None,
                "error": None,
            }
        )

    status: dict[str, Any] = {
        "schema_version": 1,
        "model": args.model,
        "max_steps": args.max_steps,
        "started_at_utc": _utc_now(),
        "finished_at_utc": None,
        "state": "running",
        "runs": statuses,
    }
    _write_json(args.status_path, status)

    failures = 0
    for run, run_status in zip(runs, statuses):
        if run_status["state"] == "completed":
            print(f"SKIP {run['run_id']}: reusable successful output", flush=True)
            continue

        run_status["state"] = "running"
        run_status["started_at_utc"] = _utc_now()
        _write_json(args.status_path, status)
        print(
            f"START {run['run_id']} dataset={run['dataset']} "
            f"site={run['site']} persona={run['persona']['value']}",
            flush=True,
        )

        legacy.TASK = {
            "name": f"{run['case_id']} | {run['task_name']}",
            "description": run["task"],
            "url": run["url"],
            "reset_url": run["reset_url"],
        }
        legacy.PERSONA = {
            "value": run["persona"]["value"],
            "content": run["persona"]["content"],
        }
        attempt_dir = (
            args.output_root
            / ".attempts"
            / run["run_id"]
            / datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        )

        try:
            legacy._check_webharbor()
            legacy._reset_webharbor()
            attempt_path = asyncio.run(
                legacy._run_agent(
                    model=args.model,
                    max_steps=args.max_steps,
                    headless=True,
                    output_dir=attempt_dir,
                )
            )
            output_path = _promote_attempt(attempt_path, args.output_root, run)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            summary = payload["summary"]
            passed = bool(
                summary["is_done"]
                and summary["is_successful"]
                and not summary["has_errors"]
            )
            if not passed:
                failures += 1
            run_status.update(
                {
                    "state": "completed" if passed else "needs_review",
                    "finished_at_utc": _utc_now(),
                    "output": str(output_path),
                    "is_done": summary["is_done"],
                    "is_successful": summary["is_successful"],
                    "has_errors": summary["has_errors"],
                    "steps": summary["number_of_steps"],
                    "duration_seconds": summary["total_duration_seconds"],
                }
            )
            print(
                f"DONE {run['run_id']} pass={passed} steps={summary['number_of_steps']} "
                f"output={output_path}",
                flush=True,
            )
        except Exception as exc:
            failures += 1
            run_status.update(
                {
                    "state": "failed",
                    "finished_at_utc": _utc_now(),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            print(f"FAIL {run['run_id']}: {run_status['error']}", file=sys.stderr, flush=True)
            traceback.print_exc()
        finally:
            _write_json(args.status_path, status)

    status["finished_at_utc"] = _utc_now()
    status["failure_count"] = failures
    status["state"] = "completed" if failures == 0 else "completed_with_failures"
    _write_json(args.status_path, status)
    print(f"BATCH {status['state']} failures={failures} status={args.status_path}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
