"""Prepare and run the March-binary Judge over all 72 WebHarbor cases.

GPT-5 is resumed from the completed Dan-48 experiment, so only the 24 cases
without existing GPT results are sent to the API. DeepSeek outputs are kept in
fresh directories so they all come from the same configured provider account.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


EXPERIMENT_DIR = Path(__file__).resolve().parent
ROOT = EXPERIMENT_DIR.parents[2]
INPUT_DIR = EXPERIMENT_DIR / "inputs"
RESULTS_DIR = EXPERIMENT_DIR / "results"
LOG_DIR = RESULTS_DIR / "logs"

MANIFEST_PATH = (
    ROOT
    / "technical_evaluation"
    / "annotation"
    / "webharbor_72_human"
    / "assignment_manifest.json"
)
ANNOTATION_ROOT = MANIFEST_PATH.parent
DAN48_DIR = ROOT / "technical_evaluation" / "experiments" / "march_binary_dan48"
AGENTIC_RUNNER = (
    ROOT / "technical_evaluation" / "pipelines" / "run_march_binary_agentic_judge.py"
)
BASELINE_RUNNER = (
    ROOT / "technical_evaluation" / "pipelines" / "run_baseline_llm_judge.py"
)
MARCH_COMMIT = "2881b03bc19ac4ee6c53c08ec94930348ab59465"
DEEPSEEK_MODEL = "deepseek-v4-flash"


def _copy_inputs(case_ids: list[str]) -> None:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    dan48_inputs = DAN48_DIR / "inputs"
    raw_dirs = [
        ANNOTATION_ROOT / name / "raw_data"
        for name in ("Annalisa", "Simret", "Dan", "Yukun")
    ]

    for case_id in case_ids:
        candidates = [dan48_inputs / f"{case_id}.json"] + [
            directory / f"{case_id}.json" for directory in raw_dirs
        ]
        source = next((path for path in candidates if path.is_file()), None)
        if source is None:
            raise FileNotFoundError(f"No canonical input found for {case_id}")
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
        if str(payload.get("data_id") or "") != case_id:
            raise ValueError(f"Input ID mismatch for {case_id}: {source}")
        required = ("task", "criteria1", "persona", "steps")
        missing = [key for key in required if not payload.get(key)]
        if missing:
            raise ValueError(f"Input {case_id} is missing required fields: {missing}")
        (INPUT_DIR / f"{case_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _seed_completed_gpt_results() -> None:
    source_agentic = DAN48_DIR / "results" / "agentic_gpt5"
    target_agentic = RESULTS_DIR / "agentic_gpt5"
    shutil.copytree(source_agentic, target_agentic, dirs_exist_ok=True)

    source_baseline = DAN48_DIR / "results" / "baseline" / "GPT"
    target_baseline = RESULTS_DIR / "baseline" / "GPT"
    shutil.copytree(source_baseline, target_baseline, dirs_exist_ok=True)


def prepare() -> dict[str, object]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    case_ids = [str(item["case_id"]) for item in manifest.get("cases", [])]
    if len(case_ids) != 72 or len(set(case_ids)) != 72:
        raise ValueError(f"Expected 72 unique manifest cases, found {len(set(case_ids))}")

    completed_gpt_ids = {
        path.stem for path in (DAN48_DIR / "inputs").glob("*.json")
    }
    remaining_gpt_ids = [case_id for case_id in case_ids if case_id not in completed_gpt_ids]
    if len(completed_gpt_ids) != 48 or len(remaining_gpt_ids) != 24:
        raise ValueError(
            "Expected the GPT seed to contain 48 cases and leave 24 cases; "
            f"got completed={len(completed_gpt_ids)} remaining={len(remaining_gpt_ids)}"
        )

    _copy_inputs(case_ids)
    _seed_completed_gpt_results()

    run_manifest: dict[str, object] = {
        "experiment_id": "march_binary_webharbor72",
        "source_manifest": str(MANIFEST_PATH),
        "source_commit": MARCH_COMMIT,
        "label_policy": {
            "allowed_labels": ["pass", "fail"],
            "legacy_partial_mapping": "pass",
            "prompt_allows_partial": False,
        },
        "total_cases": len(case_ids),
        "gpt_seeded_case_count": len(completed_gpt_ids),
        "gpt_remaining_case_count": len(remaining_gpt_ids),
        "gpt_remaining_case_ids": remaining_gpt_ids,
        "deepseek": {
            "model": DEEPSEEK_MODEL,
            "provider": "CloseAI OpenAI-compatible endpoint",
            "credential_persisted": False,
        },
    }
    EXPERIMENT_DIR.mkdir(parents=True, exist_ok=True)
    (EXPERIMENT_DIR / "sample_manifest.json").write_text(
        json.dumps(run_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return run_manifest


def _commands() -> dict[str, list[str]]:
    return {
        "agentic_gpt5": [
            sys.executable,
            "-u",
            str(AGENTIC_RUNNER),
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
            str(BASELINE_RUNNER),
            "--dataset-dir",
            str(INPUT_DIR),
            "--results-dir",
            str(RESULTS_DIR / "baseline"),
            "--json-pattern",
            "*.json",
            "--judge-model",
            "gpt-5",
            # Preserve the seeded Dan-48 filenames so --skip-existing sends
            # only the remaining 24 cases to the unchanged GPT API.
            "--run-tag",
            "march_binary_dan10",
            "--fixed-batch-id",
            "full72_gpt5",
            "--request-max-concurrency",
            "2",
            "--max-chars-per-field",
            "700",
            "--skip-existing",
        ],
        "agentic_deepseek": [
            sys.executable,
            "-u",
            str(AGENTIC_RUNNER),
            "--input-dir",
            str(INPUT_DIR),
            "--output-dir",
            str(RESULTS_DIR / "agentic_deepseek_v4_flash"),
            "--judge-model",
            DEEPSEEK_MODEL,
            "--max-attempts",
            "3",
            "--retry-delay",
            "5",
            "--resume",
        ],
        "baseline_deepseek": [
            sys.executable,
            "-u",
            str(BASELINE_RUNNER),
            "--dataset-dir",
            str(INPUT_DIR),
            "--results-dir",
            str(RESULTS_DIR / "baseline"),
            "--json-pattern",
            "*.json",
            "--judge-model",
            DEEPSEEK_MODEL,
            "--run-tag",
            "march_binary_webharbor72_closeai",
            "--fixed-batch-id",
            "full72_deepseek_v4_flash",
            "--request-max-concurrency",
            "2",
            "--max-chars-per-field",
            "700",
            "--skip-existing",
        ],
    }


def _run_one(system_id: str, command: list[str]) -> tuple[str, int]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{system_id}.log"
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
    exit_code = process.wait()
    print(f"[RESULT] {system_id}: exit={exit_code}", flush=True)
    return system_id, exit_code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--system",
        action="append",
        choices=list(_commands()),
        dest="systems",
    )
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument(
        "--skip-prepare",
        action="store_true",
        help="Use the already prepared inputs and GPT seed without copying them again.",
    )
    parser.add_argument("--max-workers", type=int, default=2)
    args = parser.parse_args()

    if args.skip_prepare:
        manifest = json.loads(
            (EXPERIMENT_DIR / "sample_manifest.json").read_text(encoding="utf-8")
        )
    else:
        manifest = prepare()
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)
    if args.prepare_only:
        return 0

    commands = _commands()
    selected = args.systems or list(commands)
    if any("deepseek" in system_id for system_id in selected):
        if not os.environ.get("DEEPSEEK_API_KEY"):
            raise RuntimeError("DEEPSEEK_API_KEY must be supplied in the process environment")
        if not os.environ.get("DEEPSEEK_BASE_URL"):
            raise RuntimeError("DEEPSEEK_BASE_URL must be supplied in the process environment")

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, min(args.max_workers, len(selected)))
    ) as pool:
        futures = [pool.submit(_run_one, system_id, commands[system_id]) for system_id in selected]
        results = [future.result() for future in futures]
    return 0 if all(exit_code == 0 for _, exit_code in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
