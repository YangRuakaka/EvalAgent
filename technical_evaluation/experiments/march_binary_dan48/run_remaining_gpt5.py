"""Resume the two GPT-5 configurations from the completed Dan-10 pilot seed."""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path


EXPERIMENT_DIR = Path(__file__).resolve().parent
ROOT = EXPERIMENT_DIR.parents[2]
INPUT_DIR = EXPERIMENT_DIR / "inputs"
RESULTS_DIR = EXPERIMENT_DIR / "results"
LOG_DIR = RESULTS_DIR / "logs"


COMMANDS = {
    "agentic_gpt5": [
        sys.executable,
        "-u",
        str(ROOT / "technical_evaluation" / "pipelines" / "run_march_binary_agentic_judge.py"),
        "--input-dir",
        str(INPUT_DIR),
        "--output-dir",
        str(RESULTS_DIR / "agentic_gpt5"),
        "--judge-model",
        "gpt-5",
        "--max-attempts",
        "3",
        "--retry-delay",
        "5",
        "--resume",
    ],
    "baseline_gpt5": [
        sys.executable,
        "-u",
        str(ROOT / "technical_evaluation" / "pipelines" / "run_baseline_llm_judge.py"),
        "--dataset-dir",
        str(INPUT_DIR),
        "--results-dir",
        str(RESULTS_DIR / "baseline"),
        "--json-pattern",
        "*.json",
        "--judge-model",
        "gpt-5",
        "--run-tag",
        "march_binary_dan10",
        "--fixed-batch-id",
        "full48_gpt5",
        "--request-max-concurrency",
        "2",
        "--max-chars-per-field",
        "700",
        "--skip-existing",
    ],
}


def _stream_process(system_id: str, command: list[str]) -> tuple[str, int]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"remaining38_{system_id}.log"
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    assert process.stdout is not None
    with log_path.open("w", encoding="utf-8") as log_file:
        for line in process.stdout:
            log_file.write(line)
            log_file.flush()
            print(f"[{system_id}] {line}", end="", flush=True)
    return system_id, process.wait()


def main() -> int:
    results: list[tuple[str, int]] = []
    lock = threading.Lock()

    def run(system_id: str, command: list[str]) -> None:
        result = _stream_process(system_id, command)
        with lock:
            results.append(result)

    threads = [
        threading.Thread(target=run, args=(system_id, command), daemon=False)
        for system_id, command in COMMANDS.items()
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    for system_id, exit_code in sorted(results):
        print(f"[RESULT] {system_id}: exit={exit_code}", flush=True)
    return 0 if len(results) == len(COMMANDS) and all(code == 0 for _, code in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
