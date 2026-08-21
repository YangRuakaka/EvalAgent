"""Orchestrate the four Dan-10 preliminary judge configurations."""

from __future__ import annotations

import argparse
import concurrent.futures
import subprocess
import sys
from pathlib import Path


EXPERIMENT_DIR = Path(__file__).resolve().parent
ROOT = EXPERIMENT_DIR.parents[2]
INPUT_DIR = EXPERIMENT_DIR / "inputs"
RESULTS_DIR = EXPERIMENT_DIR / "results"
AGENTIC_RUNNER = ROOT / "technical_evaluation" / "pipelines" / "run_march_binary_agentic_judge.py"
BASELINE_RUNNER = ROOT / "technical_evaluation" / "pipelines" / "run_baseline_llm_judge.py"
SMOKE_CASE = "HOT-03-B"


def _commands(smoke: bool) -> dict[str, list[str]]:
    commands: dict[str, list[str]] = {}
    for system_id, model in (
        ("agentic_gpt5", "gpt-5"),
        ("agentic_deepseek", "deepseek-chat"),
    ):
        command = [
            sys.executable,
            str(AGENTIC_RUNNER),
            "--input-dir",
            str(INPUT_DIR),
            "--output-dir",
            str(RESULTS_DIR / system_id),
            "--judge-model",
            model,
            "--max-attempts",
            "3",
            "--retry-delay",
            "5",
            "--resume",
        ]
        if smoke:
            command.extend(["--case", SMOKE_CASE])
        commands[system_id] = command

    commands["baseline_both"] = [
        sys.executable,
        str(BASELINE_RUNNER),
        "--dataset-dir",
        str(INPUT_DIR),
        "--results-dir",
        str(RESULTS_DIR / "baseline"),
        "--json-pattern",
        f"{SMOKE_CASE}.json" if smoke else "*.json",
        "--judge-models",
        "gpt-5",
        "deepseek-chat",
        "--run-tag",
        "march_binary_dan10",
        "--fixed-batch-id",
        "smoke" if smoke else "full10",
        "--request-max-concurrency",
        "1" if smoke else "2",
        "--max-chars-per-field",
        "700",
        "--skip-existing",
    ]
    return commands


def _run_one(system_id: str, command: list[str], phase: str) -> tuple[str, int]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    log_dir = RESULTS_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / f"{phase}_{system_id}.stdout.log").write_text(
        completed.stdout,
        encoding="utf-8",
    )
    (log_dir / f"{phase}_{system_id}.stderr.log").write_text(
        completed.stderr,
        encoding="utf-8",
    )
    print(f"[{phase}] {system_id}: exit={completed.returncode}", flush=True)
    if completed.stdout:
        print(completed.stdout[-4000:], flush=True)
    if completed.stderr:
        print(completed.stderr[-4000:], file=sys.stderr, flush=True)
    return system_id, completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument(
        "--system",
        choices=["agentic_gpt5", "agentic_deepseek", "baseline_both"],
        action="append",
        dest="systems",
        help="Run only selected system group(s); may be repeated.",
    )
    args = parser.parse_args()
    phase = "smoke" if args.smoke else "full10"
    commands = _commands(args.smoke)
    if args.systems:
        selected = set(args.systems)
        commands = {
            system_id: command
            for system_id, command in commands.items()
            if system_id in selected
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [
            pool.submit(_run_one, system_id, command, phase)
            for system_id, command in commands.items()
        ]
        results = [future.result() for future in futures]
    return 0 if all(code == 0 for _, code in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
