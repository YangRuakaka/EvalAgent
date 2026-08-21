"""Build blinded annotation inputs from a grounded-judge pilot run."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_DIR = (
    REPO_ROOT
    / "technical_evaluation"
    / "results"
    / "grounded_judge_webharbor_v13_v19_pilot_24"
)
DEFAULT_PILOT_DIR = Path(__file__).resolve().parent / "pilot_24_v19"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _action_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _contract_by_case(debug_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    contracts: dict[str, dict[str, Any]] = {}
    for case in debug_payload.get("cases", []):
        for stage in case.get("stages", []):
            if stage.get("stage") == "contract":
                raw = stage.get("raw_output")
                if isinstance(raw, dict):
                    contracts[str(case.get("case_id"))] = raw
                break
    return contracts


def _format_contract(criterion: dict[str, Any], contract: dict[str, Any]) -> str:
    lines = [
        f"Criterion: {criterion.get('title', '')}",
        f"Assertion: {criterion.get('assertion', '')}",
        f"Description: {criterion.get('description', '')}",
        "",
        "Operational contract used by both human and LLM:",
        f"Decision opportunity: {contract.get('decision_opportunity', '')}",
        f"PASS rule: {contract.get('pass_rule', '')}",
        f"FAIL rule: {contract.get('fail_rule', '')}",
        "Coverage requirements:",
    ]
    for item in contract.get("coverage_requirements", []):
        if isinstance(item, dict):
            lines.append(
                f"- {item.get('element', 'requirement')}: "
                f"{item.get('requirement', '')}"
            )
        else:
            lines.append(f"- {item}")
    lines.append("Disallowed inferences:")
    lines.extend(f"- {item}" for item in contract.get("disallowed_inferences", []))
    return "\n".join(lines).strip()


def build(results_dir: Path, pilot_dir: Path) -> None:
    visualization = _read_json(results_dir / "visualization_data.json")
    debug = _read_json(results_dir / "pipeline_debug.json")
    contracts = _contract_by_case(debug)
    cases = visualization.get("cases", [])
    if len(cases) != 24:
        raise ValueError(f"Expected 24 pilot cases, found {len(cases)}")
    if visualization.get("judge_version") != "grounded-v19":
        raise ValueError(
            "Pilot annotation must be built from grounded-v19; found "
            f"{visualization.get('judge_version')!r}"
        )

    pilot_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = pilot_dir / "raw_data"
    raw_dir.mkdir(parents=True, exist_ok=True)
    selected_ids = {str(case.get("case_id")) for case in cases}
    stale = [
        path.name
        for path in raw_dir.glob("*.json")
        if path.stem not in selected_ids
    ]
    if stale:
        raise RuntimeError(
            "raw_data contains stale cases; move them out before rebuilding: "
            + ", ".join(sorted(stale))
        )

    manifest_cases: list[dict[str, Any]] = []
    for case in cases:
        case_id = str(case["case_id"])
        contract = contracts.get(case_id)
        if contract is None:
            raise ValueError(f"Missing operational contract for {case_id}")
        steps = []
        for step_index, step in enumerate(case.get("steps", [])):
            steps.append(
                {
                    # Keep the original zero-based index so human and judge
                    # step labels can be compared without an offset.
                    "step_id": step_index,
                    "EVALUATION": step.get("evaluation_previous_goal") or "",
                    "MEMORY": step.get("memory") or "",
                    "TARGET OBJECTIVE": step.get("next_goal") or "",
                    "AI REASONING": step.get("thinking_process") or "",
                    "ACTION": _action_text(step.get("action")),
                }
            )
        raw_item = {
            "data_id": case_id,
            "source_file": case.get("source_path", ""),
            "task": case.get("task", ""),
            "criteria1": _format_contract(case.get("criterion", {}), contract),
            "criteria2": "",
            "criteria3": "",
            "persona": (
                "Agent persona/value condition: "
                f"{case.get('agent', {}).get('persona_value', '')}. "
                "Apply it only when semantically relevant to the current criterion."
            ),
            "starting_task_prompt": "",
            "steps": steps,
        }
        (raw_dir / f"{case_id}.json").write_text(
            json.dumps(raw_item, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        manifest_cases.append(
            {
                "case_id": case_id,
                "domain": case_id.split("-", 1)[0],
                "base_task": case_id.rsplit("-", 1)[0],
                "condition": case_id.rsplit("-", 1)[1],
                "persona_value": case.get("agent", {}).get("persona_value"),
                "criterion": case.get("criterion", {}).get("title"),
                "step_count": len(steps),
            }
        )

    manifest = {
        "pilot": "webharbor_v13_grounded_v19_pilot_24",
        "judge_version": "grounded-v19",
        "blinded": True,
        "label_space": ["PASS", "FAIL"],
        "case_count": len(manifest_cases),
        "cases": manifest_cases,
    }
    (pilot_dir / "annotation_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with (pilot_dir / "human_annotations_template.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(["case_id", "human_verdict", "notes"])
        writer.writerows([item["case_id"], "", ""] for item in manifest_cases)

    print(raw_dir)
    print(pilot_dir / "annotation_manifest.json")
    print(pilot_dir / "human_annotations_template.csv")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build blinded raw_data files for the 24-case annotation pilot."
    )
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--pilot-dir", type=Path, default=DEFAULT_PILOT_DIR)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    build(args.results_dir.resolve(), args.pilot_dir.resolve())
