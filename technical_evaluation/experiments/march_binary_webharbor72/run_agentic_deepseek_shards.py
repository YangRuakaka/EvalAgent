"""Run the 72-case DeepSeek Agentic Judge in three resumable case shards."""

from __future__ import annotations

import concurrent.futures
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPERIMENT_DIR = Path(__file__).resolve().parent
ROOT = EXPERIMENT_DIR.parents[2]
INPUT_DIR = EXPERIMENT_DIR / "inputs"
RESULTS_DIR = EXPERIMENT_DIR / "results"
CANONICAL_DIR = RESULTS_DIR / "agentic_deepseek_v4_flash"
SHARD_ROOT = RESULTS_DIR / "agentic_deepseek_v4_flash_shards"
RUNNER = ROOT / "technical_evaluation" / "pipelines" / "run_march_binary_agentic_judge.py"
MODEL = "deepseek-v4-flash"
SHARD_COUNT = 3


def _case_ids() -> list[str]:
    manifest = json.loads((EXPERIMENT_DIR / "sample_manifest.json").read_text(encoding="utf-8"))
    source_manifest = Path(str(manifest["source_manifest"]))
    source = json.loads(source_manifest.read_text(encoding="utf-8"))
    case_ids = [str(item["case_id"]) for item in source.get("cases", [])]
    if len(case_ids) != 72 or len(set(case_ids)) != 72:
        raise ValueError(f"Expected 72 unique cases, got {len(set(case_ids))}")
    return case_ids


def _shards(case_ids: list[str]) -> list[list[str]]:
    return [case_ids[index::SHARD_COUNT] for index in range(SHARD_COUNT)]


def _seed_first_shard() -> None:
    target = SHARD_ROOT / "shard_1"
    if (target / "experiment_evaluation.json").is_file():
        return
    if not (CANONICAL_DIR / "experiment_evaluation.json").is_file():
        return
    shutil.copytree(CANONICAL_DIR, target, dirs_exist_ok=True)


def _command(shard_index: int, case_ids: list[str]) -> list[str]:
    command = [
        sys.executable,
        "-u",
        str(RUNNER),
        "--input-dir",
        str(INPUT_DIR),
        "--output-dir",
        str(SHARD_ROOT / f"shard_{shard_index}"),
        "--judge-model",
        MODEL,
        "--max-attempts",
        "3",
        "--retry-delay",
        "5",
        "--resume",
    ]
    for case_id in case_ids:
        command.extend(["--case", case_id])
    return command


def _run_shard(shard_index: int, case_ids: list[str]) -> tuple[int, int]:
    SHARD_ROOT.mkdir(parents=True, exist_ok=True)
    log_path = SHARD_ROOT / f"shard_{shard_index}.log"
    process = subprocess.Popen(
        _command(shard_index, case_ids),
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
            print(f"[shard_{shard_index}] {line}", end="", flush=True)
    exit_code = process.wait()
    print(f"[RESULT] shard_{shard_index}: exit={exit_code}", flush=True)
    return shard_index, exit_code


def _contains_partial_label(node: Any) -> bool:
    if isinstance(node, dict):
        for key, value in node.items():
            if str(key).lower() in {"verdict", "evaluatestatus", "overall_assessment"}:
                if str(value).strip().lower() == "partial":
                    return True
            if _contains_partial_label(value):
                return True
    elif isinstance(node, list):
        return any(_contains_partial_label(item) for item in node)
    return False


def merge(case_ids: list[str]) -> None:
    conditions_by_id: dict[str, dict[str, Any]] = {}
    visualizations_by_id: dict[str, dict[str, Any]] = {}
    shard_reports: list[dict[str, Any]] = []

    for shard_index, expected_ids in enumerate(_shards(case_ids), start=1):
        shard_dir = SHARD_ROOT / f"shard_{shard_index}"
        status = json.loads((shard_dir / "run_status.json").read_text(encoding="utf-8"))
        response = json.loads((shard_dir / "experiment_evaluation.json").read_text(encoding="utf-8"))
        visualization = json.loads((shard_dir / "visualization_data.json").read_text(encoding="utf-8"))
        conditions = response.get("conditions", [])
        if status.get("state") != "completed" or len(conditions) != len(expected_ids):
            raise RuntimeError(
                f"Shard {shard_index} incomplete: state={status.get('state')} "
                f"conditions={len(conditions)} expected={len(expected_ids)}"
            )
        for condition in conditions:
            condition_id = str(condition.get("conditionID") or "")
            if not condition_id or condition_id in conditions_by_id:
                raise ValueError(f"Missing or duplicate condition ID: {condition_id!r}")
            if _contains_partial_label(condition):
                raise ValueError(f"PARTIAL label found in merged condition {condition_id}")
            conditions_by_id[condition_id] = condition
        for item in visualization.get("cases", []):
            visualizations_by_id[str(item.get("case_id") or "")] = item
        shard_reports.append(
            {
                "shard": shard_index,
                "case_count": len(conditions),
                "failed": int(status.get("failed") or 0),
            }
        )

    if set(conditions_by_id) != set(case_ids):
        missing = sorted(set(case_ids) - set(conditions_by_id))
        extra = sorted(set(conditions_by_id) - set(case_ids))
        raise ValueError(f"Merged case mismatch: missing={missing} extra={extra}")

    CANONICAL_DIR.mkdir(parents=True, exist_ok=True)
    evaluated_dir = CANONICAL_DIR / "evaluated"
    evaluated_dir.mkdir(parents=True, exist_ok=True)
    for shard_index in range(1, SHARD_COUNT + 1):
        source_dir = SHARD_ROOT / f"shard_{shard_index}" / "evaluated"
        for source in source_dir.glob("*__evaluated.json"):
            shutil.copy2(source, evaluated_dir / source.name)

    ordered_conditions = [conditions_by_id[case_id] for case_id in case_ids]
    ordered_visualizations = [
        visualizations_by_id[case_id]
        for case_id in case_ids
        if case_id in visualizations_by_id
    ]
    (CANONICAL_DIR / "experiment_evaluation.json").write_text(
        json.dumps(
            {"conditions": ordered_conditions, "multi_condition_assessment": None},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (CANONICAL_DIR / "visualization_data.json").write_text(
        json.dumps(
            {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "judge_model": MODEL,
                "judge_version": "march-binary-partial-as-pass@2881b03bc19ac4ee6c53c08ec94930348ab59465",
                "selection_rule": "All 72 WebHarbor cases, criteria1, merged from three disjoint case shards.",
                "cases": ordered_visualizations,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (CANONICAL_DIR / "run_status.json").write_text(
        json.dumps(
            {
                "state": "completed",
                "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                "pipeline": "march_2026_agentic_judge_binary_partial_as_pass",
                "source_commit": "2881b03bc19ac4ee6c53c08ec94930348ab59465",
                "judge_model": MODEL,
                "total": 72,
                "completed": 72,
                "failed": 0,
                "execution": "three_disjoint_case_shards",
                "cases": {case_id: "completed" for case_id in case_ids},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (CANONICAL_DIR / "shard_merge_report.json").write_text(
        json.dumps(
            {
                "merged_at_utc": datetime.now(timezone.utc).isoformat(),
                "unique_case_count": len(conditions_by_id),
                "evaluated_file_count": len(list(evaluated_dir.glob("*__evaluated.json"))),
                "partial_label_found": False,
                "shards": shard_reports,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> int:
    case_ids = _case_ids()
    _seed_first_shard()
    shards = _shards(case_ids)
    with concurrent.futures.ThreadPoolExecutor(max_workers=SHARD_COUNT) as pool:
        results = list(
            pool.map(
                lambda item: _run_shard(item[0], item[1]),
                enumerate(shards, start=1),
            )
        )
    if any(exit_code != 0 for _, exit_code in results):
        return 2
    merge(case_ids)
    print("[DONE] merged 72 unique DeepSeek Agentic results", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
