"""Export review tables for every case in the Dan-10 preliminary experiment."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any


EXPERIMENT_DIR = Path(__file__).resolve().parent
INPUT_DIR = EXPERIMENT_DIR / "inputs"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _escape_md(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\r", " ").replace("\n", "<br>")


def main() -> int:
    manifest = json.loads((EXPERIMENT_DIR / "sample_manifest.json").read_text(encoding="utf-8"))
    dan_export = json.loads((EXPERIMENT_DIR / "dan_criteria1_annotations.json").read_text(encoding="utf-8"))
    annotations = dan_export["annotations"]

    rows: list[dict[str, Any]] = []
    for selection in manifest["cases"]:
        case_id = str(selection["case_id"])
        input_path = INPUT_DIR / f"{case_id}.json"
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        annotation = annotations[case_id]
        rows.append(
            {
                "case_id": case_id,
                "task_family": case_id.split("-", 1)[0],
                "dan_overall": annotation.get("overall_assessment"),
                "human_evidence_count": len(annotation.get("evidences") or []),
                "step_count": len(payload.get("steps") or []),
                "task": payload.get("task"),
                "persona_value": payload.get("persona_value"),
                "persona": payload.get("persona"),
                "criterion_id": "criteria1",
                "criterion": payload.get("criteria1"),
                "assigned_annotator": payload.get("assigned_annotator"),
                "co_annotator": payload.get("co_annotator"),
                "pending_rerun": payload.get("pending_rerun"),
                "source_file": payload.get("source_file"),
                "input_file": str(input_path.resolve()),
                "input_sha256": _sha256(input_path),
            }
        )

    common_config = {
        "experiment_id": manifest["experiment_id"],
        "source_commit": manifest["source_commit"],
        "case_count": len(rows),
        "label_policy": manifest["label_policy"],
        "systems": manifest["systems"],
        "judge_persona_parameter_passed": True,
        "judge_persona_directly_in_llm_prompts": False,
        "judge_persona_visibility_note": (
            "The March backend accepts personas but does not include them in LLM prompt variables. "
            "Persona can still be visible indirectly when encoded in the criterion or mentioned in trajectory fields."
        ),
        "step_alignment_policy": (
            "strict one-to-one: model step_index k maps only to raw steps[k].step_id; "
            "human evidence must use that exact step_id and the same normalized source field"
        ),
    }

    json_path = EXPERIMENT_DIR / "case_configuration_audit.json"
    json_path.write_text(
        json.dumps({"common_config": common_config, "cases": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    csv_path = EXPERIMENT_DIR / "case_configuration_audit.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    md_lines = [
        "# Dan-10 case configuration audit",
        "",
        "## Common Judge configuration",
        "",
        "| Setting | Value |",
        "|---|---|",
        f"| Experiment | `{_escape_md(common_config['experiment_id'])}` |",
        f"| March source commit | `{_escape_md(common_config['source_commit'])}` |",
        "| Label policy | Prompt allows PASS/FAIL only; leaked or legacy PARTIAL maps to PASS |",
        "| Persona argument passed by runner | Yes |",
        "| Persona directly included in March LLM prompts | **No** |",
        "| Indirect persona visibility | Criterion wording and any persona text already present in trajectory fields |",
        "| Step alignment | Strict one-to-one: model `step_index=k` → raw `steps[k].step_id` → exact human `step_id`; same normalized field required |",
        "",
        "## Case table",
        "",
        "| Case | Dan | Steps | Task | Persona value | Full persona | Criterion | Annotators |",
        "|---|---:|---:|---|---|---|---|---|",
    ]
    for row in rows:
        md_lines.append(
            "| {case_id} | {dan_overall} | {step_count} | {task} | {persona_value} | {persona} | {criterion} | {assigned_annotator} + {co_annotator} |".format(
                **{key: _escape_md(value) for key, value in row.items()}
            )
        )
    md_path = EXPERIMENT_DIR / "case_configuration_audit.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(json.dumps({"markdown": str(md_path), "csv": str(csv_path), "json": str(json_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
