"""Build three blinded 48-case annotation assignments from the 72 WebHarbor runs.

Each case is assigned to exactly two annotators.  The three annotator pairs each
receive 24 cases, so every annotator receives 48 cases.  No judge outputs are
read or copied into the annotation inputs.
"""

from __future__ import annotations

import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO_ROOT / "browser_agent_runs_webharbor_v13_pilot"
CRITERIA_FILE = REPO_ROOT / "technical_evaluation" / "webharbor_v13_judge_base_criteria.json"
OUTPUT_DIR = Path(__file__).resolve().parent / "webharbor_72_human"
WEBHARBOR_SCRIPTS = REPO_ROOT / "scripts" / "webharbor"

if str(WEBHARBOR_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(WEBHARBOR_SCRIPTS))

from webharbor_v13_catalog import ALL_CASES  # noqa: E402


ANNOTATORS = ("Yukun", "Simret", "Dan")
PAIR_YUKUN_SIMRET = ("Yukun", "Simret")
PAIR_YUKUN_DAN = ("Yukun", "Dan")
PAIR_SIMRET_DAN = ("Simret", "Dan")
RERUN_BASE_IDS = {"EDU-01", "EDU-02", "SPT-01", "SPT-02", "SPT-03"}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _case_id(payload: dict[str, Any]) -> str:
    name = str(payload.get("metadata", {}).get("task", {}).get("name", ""))
    return name.split(" | ", 1)[0].strip()


def _timestamp(payload: dict[str, Any]) -> str:
    return str(payload.get("metadata", {}).get("timestamp_utc", ""))


def _latest_runs() -> dict[str, tuple[Path, dict[str, Any]]]:
    latest: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in sorted(RUNS_DIR.glob("webharbor_v13_*.json")):
        try:
            payload = _read_json(path)
        except Exception:
            continue
        case_id = _case_id(payload)
        if not case_id:
            continue
        previous = latest.get(case_id)
        if previous is None or _timestamp(payload) >= _timestamp(previous[1]):
            latest[case_id] = (path, payload)
    return latest


def _catalog_cases() -> dict[str, dict[str, str]]:
    return {str(case["case_id"]): dict(case) for case in ALL_CASES}


def _action_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _steps(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    model_outputs = payload.get("details", {}).get("model_outputs", [])
    if not isinstance(model_outputs, list):
        return result
    for step_id, raw in enumerate(model_outputs):
        item = raw if isinstance(raw, dict) else {}
        result.append(
            {
                "step_id": step_id,
                "EVALUATION": item.get("evaluation_previous_goal") or "",
                "MEMORY": item.get("memory") or "",
                "TARGET OBJECTIVE": item.get("next_goal") or "",
                "AI REASONING": item.get("thinking_process", item.get("thinking")) or "",
                "ACTION": _action_text(item.get("action")),
            }
        )
    return result


def _assign_pairs(case_ids: list[str]) -> dict[str, tuple[str, str]]:
    pending = sorted(
        case_id for case_id in case_ids if case_id.rsplit("-", 1)[0] in RERUN_BASE_IDS
    )
    remaining = sorted(set(case_ids) - set(pending))
    rng = random.Random(20260802)
    rng.shuffle(remaining)

    assignments: dict[str, tuple[str, str]] = {}
    pair_counts: Counter[tuple[str, str]] = Counter()

    # All pending-rerun cases have the same primary owner (Yukun).  The second
    # independent annotator is split between Simret and Dan for agreement.
    for index, case_id in enumerate(pending):
        pair = PAIR_YUKUN_SIMRET if index % 2 == 0 else PAIR_YUKUN_DAN
        assignments[case_id] = pair
        pair_counts[pair] += 1

    remaining_quotas = {
        PAIR_YUKUN_SIMRET: 24 - pair_counts[PAIR_YUKUN_SIMRET],
        PAIR_YUKUN_DAN: 24 - pair_counts[PAIR_YUKUN_DAN],
        PAIR_SIMRET_DAN: 24,
    }
    schedule: list[tuple[str, str]] = []
    while any(value > 0 for value in remaining_quotas.values()):
        for pair in (PAIR_SIMRET_DAN, PAIR_YUKUN_DAN, PAIR_YUKUN_SIMRET):
            if remaining_quotas[pair] > 0:
                schedule.append(pair)
                remaining_quotas[pair] -= 1

    if len(schedule) != len(remaining):
        raise RuntimeError("Pair schedule does not cover all remaining cases")
    for case_id, pair in zip(remaining, schedule, strict=True):
        assignments[case_id] = pair
    return assignments


def _write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)


def build() -> None:
    runs = _latest_runs()
    catalog = _catalog_cases()
    criteria = _read_json(CRITERIA_FILE)
    case_ids = sorted(catalog)

    if len(case_ids) != 72:
        raise ValueError(f"Expected 72 catalog cases, found {len(case_ids)}")
    missing_runs = sorted(set(case_ids) - set(runs))
    if missing_runs:
        raise ValueError("Missing run files: " + ", ".join(missing_runs))

    assignments = _assign_pairs(case_ids)
    per_annotator: dict[str, list[str]] = {name: [] for name in ANNOTATORS}
    pair_counts: Counter[str] = Counter()
    for case_id, pair in assignments.items():
        pair_counts[" + ".join(pair)] += 1
        for annotator in pair:
            per_annotator[annotator].append(case_id)

    if any(len(items) != 48 for items in per_annotator.values()):
        raise RuntimeError(f"Unbalanced annotator counts: {per_annotator}")
    if any(count != 24 for count in pair_counts.values()):
        raise RuntimeError(f"Unbalanced pair counts: {pair_counts}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest_cases: list[dict[str, Any]] = []
    pending_case_ids: list[str] = []

    raw_by_case: dict[str, dict[str, Any]] = {}
    for case_id in case_ids:
        source_path, payload = runs[case_id]
        metadata = payload.get("metadata", {})
        task_meta = metadata.get("task", {})
        persona_meta = metadata.get("persona", {})
        base_id = case_id.rsplit("-", 1)[0]
        expected_task = str(catalog[case_id]["task"])
        actual_task = str(task_meta.get("description") or "")
        pending_rerun = actual_task.strip() != expected_task.strip()
        if pending_rerun:
            pending_case_ids.append(case_id)

        criterion = criteria.get(base_id, {})
        assertion = str(criterion.get("assertion") or "").strip()
        if not assertion:
            raise ValueError(f"Missing criterion assertion for {case_id}")

        raw_by_case[case_id] = {
            "data_id": case_id,
            "source_file": str(source_path.resolve()),
            "task": actual_task,
            "expected_task_after_rerun": expected_task,
            "pending_rerun": pending_rerun,
            "criteria1": assertion,
            "persona": str(persona_meta.get("content") or ""),
            "persona_value": str(persona_meta.get("value") or ""),
            "starting_task_prompt": actual_task,
            "steps": _steps(payload),
        }
        manifest_cases.append(
            {
                "case_id": case_id,
                "base_task": base_id,
                "condition": case_id.rsplit("-", 1)[1],
                "assigned_annotators": list(assignments[case_id]),
                "primary_owner": "Yukun" if base_id in RERUN_BASE_IDS else assignments[case_id][0],
                "pending_rerun": pending_rerun,
                "persona_value": raw_by_case[case_id]["persona_value"],
                "criterion_assertion": assertion,
                "source_file": str(source_path.resolve()),
            }
        )

    approved_rerun_cases = {
        f"{base_id}-{condition}"
        for base_id in RERUN_BASE_IDS
        for condition in ("A", "B", "C")
    }
    unexpected_pending = set(pending_case_ids) - approved_rerun_cases
    if unexpected_pending:
        raise RuntimeError(
            "Cases outside the five approved task changes still have stale prompts: "
            f"unexpected={sorted(unexpected_pending)}"
        )
    if any("Yukun" not in assignments[case_id] for case_id in pending_case_ids):
        raise RuntimeError("Every pending-rerun case must be assigned to Yukun")

    for annotator, assigned_ids in per_annotator.items():
        annotator_dir = OUTPUT_DIR / annotator
        raw_dir = annotator_dir / "raw_data"
        raw_dir.mkdir(parents=True, exist_ok=True)
        for case_id in sorted(assigned_ids):
            item = dict(raw_by_case[case_id])
            item["assigned_annotator"] = annotator
            item["co_annotator"] = next(
                name for name in assignments[case_id] if name != annotator
            )
            (raw_dir / f"{case_id}.json").write_text(
                json.dumps(item, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        (annotator_dir / "assigned_case_ids.txt").write_text(
            "\n".join(sorted(assigned_ids)) + "\n",
            encoding="utf-8",
        )
        _write_csv(
            annotator_dir / "human_annotations_template.csv",
            [["case_id", "human_verdict", "notes"]]
            + [[case_id, "", ""] for case_id in sorted(assigned_ids)],
        )

    manifest = {
        "assignment": "webharbor_v13_72_double_annotation",
        "judge_assist": False,
        "criterion_display": "assertion_only",
        "persona_display": "full_original_persona_content",
        "annotators": list(ANNOTATORS),
        "total_cases": 72,
        "annotations_per_case": 2,
        "cases_per_annotator": 48,
        "pair_counts": dict(pair_counts),
        "pending_rerun_primary_owner": "Yukun",
        "pending_rerun_case_ids": sorted(pending_case_ids),
        "cases": manifest_cases,
    }
    (OUTPUT_DIR / "assignment_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "pending_rerun_case_ids.txt").write_text(
        "\n".join(sorted(pending_case_ids)) + "\n",
        encoding="utf-8",
    )
    _write_csv(
        OUTPUT_DIR / "pairing_matrix.csv",
        [["case_id", "annotator_1", "annotator_2", "primary_owner", "pending_rerun"]]
        + [
            [
                item["case_id"],
                item["assigned_annotators"][0],
                item["assigned_annotators"][1],
                item["primary_owner"],
                str(item["pending_rerun"]).lower(),
            ]
            for item in manifest_cases
        ],
    )

    readme = f"""# WebHarbor 72-case Human Annotation Assignment

- Annotators: Yukun, Simret, Dan
- Each annotator: 48 cases
- Each case: 2 independent annotators
- Each annotator pair: 24 shared cases
- Judge assistance: disabled
- Persona shown: complete original persona text from the BrowserUse run
- Criterion shown: assertion only

## Pending reruns

The 15 cases under EDU-01, EDU-02, SPT-01, SPT-02, and SPT-03 share Yukun as
their primary owner and are distributed between Simret and Dan as the second
independent annotator. The annotation tool blocks only cases whose latest
trajectory still uses a stale prompt; a successful rerun unlocks them when this
package is rebuilt.

## Starting annotation

1. Open `../annotation_tool.html`.
2. Select your annotator name.
3. Select your own `<annotator>/raw_data` folder.
4. Keep the fixed criterion field unchanged.
5. Export the completed JSON using the tool.
"""
    (OUTPUT_DIR / "README.md").write_text(readme, encoding="utf-8")

    print(json.dumps({
        "output_dir": str(OUTPUT_DIR),
        "annotator_counts": {name: len(items) for name, items in per_annotator.items()},
        "pair_counts": dict(pair_counts),
        "pending_rerun": len(pending_case_ids),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    build()
