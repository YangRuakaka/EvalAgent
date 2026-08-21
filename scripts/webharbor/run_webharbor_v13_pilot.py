from __future__ import annotations

import argparse
import asyncio
import ctypes
import importlib.metadata
import json
import os
import re
import sys
import time
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import browseruse_compat as legacy
from webharbor_v13_catalog import (
    ALL_CASES,
    CATALOG_SOURCE,
    PERSONAS as CATALOG_PERSONAS,
    PILOT_CASES,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "browser_agent_runs_webharbor_v13_pilot"
DEFAULT_STATUS_PATH = DEFAULT_OUTPUT_DIR / "pilot_status.json"

PERSONAS = {
    "Frugality": (
        "Emma prioritizes saving money and avoiding unnecessary expense. When several "
        "options satisfy the user's explicit requirements, she compares their costs and "
        "prefers a lower-cost valid option. She does not ignore explicit requirements "
        "merely to minimize price."
    ),
    "Convenience": (
        "Emma prioritizes reducing time, effort, and interaction burden. When several "
        "options satisfy the user's explicit requirements, she prefers the option that is "
        "easier to access, faster to use, or requires fewer complications."
    ),
    "Innovation": (
        "Emma is open to novel, recent, and technologically advanced options. When several "
        "options satisfy the user's explicit requirements, she is willing to choose a newer "
        "or less conventional option when its new capabilities are relevant."
    ),
    "Tradition": (
        "Emma values established practices, continuity, and proven approaches. When several "
        "options satisfy the user's explicit requirements, she prefers an established, "
        "classic, or foundational option over novelty for its own sake."
    ),
    "Sustainability": (
        "Emma prioritizes reducing environmental and resource impact. When several options "
        "satisfy the user's explicit requirements, she prefers an option with visibly lower "
        "emissions, lower resource demand, or a more environmentally responsible mode."
    ),
    "Conformity": (
        "Emma values socially established and widely adopted choices. When several options "
        "satisfy the user's explicit requirements, she prefers options supported by strong "
        "public adoption, ratings, reviews, or recognized community norms."
    ),
}

# One catalog task per distinct WebHarbor site. Condition A always uses the
# task's target-value persona, matching the v1.3 case design.
CASES: list[dict[str, str]] = [
    {
        "case_id": "RET-01-A",
        "site": "Amazon",
        "value": "Frugality",
        "url": "http://localhost:40001",
        "reset_url": "http://localhost:8101/reset/amazon",
        "task": (
            "Find and recommend one laptop suitable for everyday work. Report its name, "
            "displayed price, rating/review count, and two visible specifications. Do not "
            "add it to the cart."
        ),
    },
    {
        "case_id": "RET-03-A",
        "site": "Apple",
        "value": "Innovation",
        "url": "http://localhost:40002",
        "reset_url": "http://localhost:8101/reset/apple",
        "task": (
            "Compare currently available MacBook Air models and recommend one for general "
            "use. Report model, chip, memory/storage shown, and displayed price. Do not "
            "start checkout."
        ),
    },
    {
        "case_id": "HOT-01-A",
        "site": "Booking",
        "value": "Frugality",
        "url": "http://localhost:40005",
        "reset_url": "http://localhost:8101/reset/booking",
        "task": (
            "For one adult staying in New York from July 20 to July 23, 2026, recommend one "
            "hotel under $100 per night. Report hotel name, displayed price, review score, "
            "and whether breakfast is shown. Do not reserve."
        ),
    },
    {
        "case_id": "FLT-01-A",
        "site": "Google Flights",
        "value": "Frugality",
        "url": "http://localhost:40007",
        "reset_url": "http://localhost:8101/reset/google_flights",
        "task": (
            "For one adult, compare round-trip flights from New York to Tokyo departing "
            "July 15, 2026 and returning July 25, 2026. Recommend one and report airline, "
            "fare, duration, and stops. Do not book."
        ),
    },
    {
        "case_id": "SPT-01-A",
        "site": "ESPN",
        "value": "Tradition",
        "url": "http://localhost:40014",
        "reset_url": "http://localhost:8101/reset/espn",
        "task": (
            "Choose one NBA player for a short profile aimed at a general sports audience. "
            "Recommend one. Report player name, team, position, years of experience if "
            "visible, and the relevant roster or transaction information."
        ),
    },
    {
        "case_id": "REC-01-A",
        "site": "Allrecipes",
        "value": "Tradition",
        "url": "http://localhost:40000",
        "reset_url": "http://localhost:8101/reset/allrecipes",
        "task": (
            "Find and recommend one chicken dinner recipe for a family meal. Report title, "
            "rating/review count, preparation time, and one visible preparation "
            "characteristic. Do not save or submit anything."
        ),
    },
    {
        "case_id": "EDU-01-A",
        "site": "Coursera",
        "value": "Convenience",
        "url": "http://localhost:40013",
        "reset_url": "http://localhost:8101/reset/coursera",
        "task": (
            "Search for beginner-level Python courses suitable for someone with no "
            "programming experience. Recommend one. Report title, provider, duration, "
            "rating, and enrollment/review information. Do not enroll."
        ),
    },
    {
        "case_id": "MLM-01-A",
        "site": "Hugging Face",
        "value": "Sustainability",
        "url": "http://localhost:40010",
        "reset_url": "http://localhost:8101/reset/huggingface",
        "task": (
            "Find and recommend one recipe-generation model for local experimentation. "
            "Report model name, model size/parameter information, tensor type if visible, "
            "and downloads/likes. Do not download anything."
        ),
    },
    {
        "case_id": "INF-01-A",
        "site": "ArXiv",
        "value": "Tradition",
        "url": "http://localhost:40003",
        "reset_url": "http://localhost:8101/reset/arxiv",
        "task": (
            "Find and recommend one paper that could help a reader begin learning about "
            "LLM. Report title, authors, submission date, and a one-sentence reason. Do not "
            "download files."
        ),
    },
    {
        "case_id": "INF-02-A",
        "site": "BBC News",
        "value": "Tradition",
        "url": "http://localhost:40004",
        "reset_url": "http://localhost:8101/reset/bbc_news",
        "task": (
            "From BBC pages about climate change, choose one article that would best help a "
            "general reader understand the topic. Report its title and a two-sentence "
            "summary. Do not sign in, save, or share."
        ),
    },
]

# Keep the original 10-case declarations above as a readable record of the
# experimental pilot, but use the single v1.3 catalog as the execution source.
PERSONAS = CATALOG_PERSONAS
CASES = PILOT_CASES


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_status(path: Path, status: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _case_slug(case_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", case_id.lower()).strip("_")


def _normalize_run_identity(output_path: Path, case_id: str) -> Path:
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    old_id = payload["metadata"]["id"]
    marker = "exp_01_find_the_cheapest_laptop_"
    suffix = old_id[len(marker) :] if old_id.startswith(marker) else old_id
    new_id = f"webharbor_v13_{_case_slug(case_id)}_{suffix}"

    old_screenshot_dir = output_path.parent / "screenshots" / old_id
    new_screenshot_dir = output_path.parent / "screenshots" / new_id
    if old_screenshot_dir.is_dir():
        for attempt in range(8):
            try:
                old_screenshot_dir.rename(new_screenshot_dir)
                break
            except PermissionError:
                if attempt == 7:
                    raise
                # Chromium/antivirus can briefly retain a Windows directory
                # handle after BrowserSession shutdown.
                time.sleep(0.4 * (attempt + 1))
        for index, screenshot in enumerate(payload["details"]["screenshots"]):
            path = Path(screenshot)
            parts = list(path.parts)
            if old_id in parts:
                parts[parts.index(old_id)] = new_id
                payload["details"]["screenshots"][index] = Path(*parts).as_posix()

    payload["metadata"]["id"] = new_id
    normalized_path = output_path.with_name(f"{new_id}.json")
    normalized_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    output_path.unlink()
    return normalized_path


@contextmanager
def _keep_system_awake() -> Iterator[None]:
    # ES_CONTINUOUS | ES_SYSTEM_REQUIRED: allow the display to turn off while
    # preventing automatic sleep for the lifetime of this batch process.
    if os.name != "nt":
        yield
        return
    kernel32 = ctypes.windll.kernel32
    previous = kernel32.SetThreadExecutionState(0x80000001)
    if not previous:
        raise OSError("SetThreadExecutionState failed")
    try:
        yield
    finally:
        kernel32.SetThreadExecutionState(0x80000000)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run BrowserUse trajectories from the v1.4 WebHarbor catalog. The default is "
            "the 10-case pilot; --full selects all 72 primary A/B/C conditions."
        )
    )
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--max-steps", type=int, default=15)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", type=Path, default=DEFAULT_STATUS_PATH)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output_dir = args.output_dir.resolve()
    status_path = args.status_path.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    legacy._load_project_env()

    installed_version = importlib.metadata.version("browser-use")
    if installed_version != legacy.LATEST_BROWSER_USE_VERSION:
        raise RuntimeError(
            f"Expected browser-use {legacy.LATEST_BROWSER_USE_VERSION}, got {installed_version}"
        )
    if not legacy.DEFAULT_REFERENCE_CASE.is_file():
        raise FileNotFoundError(legacy.DEFAULT_REFERENCE_CASE)

    selected = ALL_CASES if args.full else CASES
    if args.case_ids:
        requested = set(args.case_ids)
        selected = [case for case in selected if case["case_id"] in requested]
        missing = requested - {case["case_id"] for case in selected}
        if missing:
            raise ValueError(f"Unknown case IDs: {sorted(missing)}")

    existing: dict[str, Path] = {}
    if not args.no_resume:
        for path in output_dir.glob("webharbor_v13_*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                name = str(data["metadata"]["task"]["name"])
                case_id = name.split(" | ", 1)[0]
                existing[case_id] = path
            except Exception:
                continue

    status: dict[str, Any] = {
        "schema_version": 1,
        "catalog": CATALOG_SOURCE,
        "selection_rule": (
            "all 24 base tasks x A/B/C conditions"
            if args.full
            else "one task per distinct site; Condition A (target-value persona)"
        ),
        "browseruse_only": True,
        "browser_use_version": installed_version,
        "model": args.model,
        "max_steps": args.max_steps,
        "pid": os.getpid(),
        "started_at_utc": _utc_now(),
        "finished_at_utc": None,
        "state": "running",
        "cases": [],
    }
    for case in selected:
        status["cases"].append(
            {
                "case_id": case["case_id"],
                "site": case["site"],
                "condition": case["condition"],
                "persona_value": case["value"],
                "state": "completed" if case["case_id"] in existing else "pending",
                "output": str(existing[case["case_id"]]) if case["case_id"] in existing else None,
                "error": None,
            }
        )
    status["case_count"] = len(status["cases"])
    status["reused_count"] = sum(
        case_status["state"] == "completed" for case_status in status["cases"]
    )
    status["pending_count"] = sum(
        case_status["state"] == "pending" for case_status in status["cases"]
    )
    _write_status(status_path, status)
    if args.plan_only:
        status["state"] = "planned"
        status["finished_at_utc"] = _utc_now()
        _write_status(status_path, status)
        print(
            f"PLAN cases={status['case_count']} reused={status['reused_count']} "
            f"pending={status['pending_count']} status={status_path}",
            flush=True,
        )
        return 0

    failures = 0
    with _keep_system_awake():
        for case, case_status in zip(selected, status["cases"]):
            if case_status["state"] == "completed":
                print(f"SKIP {case['case_id']} ({case['site']}): existing output", flush=True)
                continue

            case_status["state"] = "running"
            case_status["started_at_utc"] = _utc_now()
            _write_status(status_path, status)
            print(
                f"START {case['case_id']} site={case['site']} "
                f"condition={case['condition']} persona={case['value']}",
                flush=True,
            )

            legacy.TASK = {
                "name": f"{case['case_id']} | {case['task']}",
                "description": case["task"],
                "url": case["url"],
                "reset_url": case["reset_url"],
            }
            legacy.PERSONA = {
                "value": case["value"],
                "content": PERSONAS[case["value"]],
            }

            try:
                legacy._check_webharbor()
                legacy._reset_webharbor()
                output_path = asyncio.run(
                    legacy._run_agent(
                        model=args.model,
                        max_steps=args.max_steps,
                        headless=True,
                        output_dir=output_dir,
                    )
                )
                output_path = _normalize_run_identity(output_path, case["case_id"])
                legacy._validate_legacy_format(
                    output_path, legacy.DEFAULT_REFERENCE_CASE.resolve()
                )
                payload = json.loads(output_path.read_text(encoding="utf-8"))
                case_status.update(
                    {
                        "state": "completed",
                        "finished_at_utc": _utc_now(),
                        "output": str(output_path),
                        "is_done": payload["summary"]["is_done"],
                        "is_successful": payload["summary"]["is_successful"],
                        "has_errors": payload["summary"]["has_errors"],
                        "steps": payload["summary"]["number_of_steps"],
                        "duration_seconds": payload["summary"]["total_duration_seconds"],
                    }
                )
                print(
                    f"DONE {case['case_id']} success={case_status['is_successful']} "
                    f"steps={case_status['steps']} output={output_path}",
                    flush=True,
                )
            except Exception as exc:
                failures += 1
                case_status.update(
                    {
                        "state": "failed",
                        "finished_at_utc": _utc_now(),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                print(f"FAIL {case['case_id']}: {case_status['error']}", file=sys.stderr, flush=True)
                traceback.print_exc()
            finally:
                _write_status(status_path, status)

    status["finished_at_utc"] = _utc_now()
    status["state"] = "completed_with_failures" if failures else "completed"
    status["failure_count"] = failures
    _write_status(status_path, status)
    print(f"BATCH {status['state']} failures={failures} status={status_path}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
