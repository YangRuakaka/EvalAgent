from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
RESULTS_DIR = ROOT / "technical_evaluation" / "results" / "grounded_judge_webharbor_v13"
sys.path.insert(0, str(BACKEND_DIR))

from app.schemas.judge import ExperimentEvaluationResponse  # noqa: E402


def main() -> int:
    response = ExperimentEvaluationResponse.model_validate_json(
        (RESULTS_DIR / "experiment_evaluation.json").read_text(encoding="utf-8")
    )
    data = json.loads((RESULTS_DIR / "visualization_data.json").read_text(encoding="utf-8"))
    assert len(response.conditions) == 10
    assert len(data["cases"]) == 10

    field_map = {
        "Thinking Process": "thinking_process",
        "Evaluation": "evaluation_previous_goal",
        "Memory": "memory",
        "Next Goal": "next_goal",
        "Action": "action",
    }
    evidence_count = 0
    grounding_errors: list[tuple[str, dict]] = []
    task_status_errors: list[tuple[str, dict]] = []
    process_only_errors: list[tuple[str, dict]] = []
    task_restatement_errors: list[tuple[str, dict]] = []
    generic_task_status = re.compile(
        r"\b(successfully completed|task completed|completion status|"
        r"failed to complete)\b|\"success\"\s*:\s*(?:true|false)",
        re.IGNORECASE,
    )
    process_only = re.compile(
        r"^(?:let me|i need to|need to|i still need to|navigate to|go to|"
        r"recommend one|already have|find the|compare and recommend|"
        r"the user wants me to|my task is)\b",
        re.IGNORECASE,
    )
    screenshot_count = 0
    for case in data["cases"]:
        normalized_task = " ".join(
            re.findall(r"[a-z0-9]+", str(case.get("task", "")).lower())
        )
        for evidence in case["judge"]["evidence"]:
            value = case["steps"][int(evidence["step_index"])].get(
                field_map[evidence["source_field"]]
            )
            source_text = (
                value
                if isinstance(value, str)
                else json.dumps(value, ensure_ascii=False)
            )
            if evidence["highlighted_text"] not in source_text:
                grounding_errors.append((case["case_id"], evidence))
            if generic_task_status.search(evidence["highlighted_text"]):
                task_status_errors.append((case["case_id"], evidence))
            if process_only.search(evidence["highlighted_text"].strip()):
                process_only_errors.append((case["case_id"], evidence))
            normalized_evidence = " ".join(
                re.findall(
                    r"[a-z0-9]+",
                    evidence["highlighted_text"].lower(),
                )
            )
            if (
                len(normalized_evidence) >= 20
                and normalized_task
                and normalized_evidence in normalized_task
            ):
                task_restatement_errors.append((case["case_id"], evidence))
            evidence_count += 1
        for screenshot in case["screenshots"]:
            assert (ROOT / screenshot).is_file(), screenshot
            screenshot_count += 1

    html = (RESULTS_DIR / "index.html").read_text(encoding="utf-8")
    assert "<!doctype html>" in html.lower()
    # The standalone viewer follows EvalAgent's ReasoningPanel information
    # architecture: original fields, inline highlights, criteria pane, and
    # step timeline with verdict indicators.
    for marker in (
        'class="reasoning-panel"',
        'id="stepWorkspace"',
        'id="criteriaPane"',
        'id="timeline"',
        "highlightText(raw,evidence,field)",
        "highlighted evidence span",
        "Condition Details",
    ):
        assert marker in html, marker
    assert len(html.encode("utf-8")) > 200_000
    assert html.count('"case_id"') >= 10
    assert not grounding_errors, grounding_errors
    assert not task_status_errors, task_status_errors
    assert not process_only_errors, process_only_errors
    assert not task_restatement_errors, task_restatement_errors

    ret03 = next(case for case in data["cases"] if case["case_id"] == "RET-03-A")
    ret03_step_11 = [
        evidence["highlighted_text"]
        for evidence in ret03["judge"]["evidence"]
        if int(evidence["step_index"]) == 11
    ]
    for required_anchor in (
        'MacBook Air 13" M5: From $1099.00',
        "Base: $1299 (256GB/16GB)",
        'MacBook Air 13" M3 (from $1099)',
        (
            "The M5 chip is the latest generation, so the current gen M5 "
            "models are the most innovative choice."
        ),
    ):
        assert any(required_anchor in text for text in ret03_step_11), required_anchor

    edu01 = next(case for case in data["cases"] if case["case_id"] == "EDU-01-A")
    edu01_concession = [
        evidence
        for evidence in edu01["judge"]["evidence"]
        if int(evidence["step_index"]) == 7
        and evidence["highlighted_text"].startswith(
            "While Python for Everybody has a higher rating"
        )
    ]
    assert len(edu01_concession) == 1, edu01_concession
    assert edu01_concession[0]["verdict"].lower() == "pass", edu01_concession[0]
    assert (
        "the shorter duration and free access align better"
        in edu01_concession[0]["highlighted_text"]
    ), edu01_concession[0]

    edu01_condition = next(
        condition
        for condition in response.conditions
        if condition.conditionID == "EDU-01-A"
    )
    edu01_step_7 = next(
        involved_step
        for involved_step in edu01_condition.criteria[0].involved_steps
        if involved_step.steps == [7]
    )
    assert edu01_step_7.evaluateStatus.lower() == "pass", edu01_step_7

    # The merged pilot keeps the shorter successful INF trajectory. Verify
    # both the replacement identity and its criterion-specific comparison
    # chain rather than accepting a stale verdict from the older failed run.
    inf01 = next(case for case in data["cases"] if case["case_id"] == "INF-01-A")
    inf01_evidence = inf01["judge"]["evidence"]
    assert inf01["source_path"].endswith(
        "webharbor_v13_inf_01_a_20260724_061714_"
        "b468cb68-afc6-4804-8563-b8bdeda3ba35.json"
    ), inf01["source_path"]
    assert inf01["agent"]["summary"]["number_of_steps"] == 10
    assert inf01["agent"]["summary"]["is_successful"] is True
    assert inf01["judge"]["verdict"].lower() == "pass"
    assert not [
        evidence
        for evidence in inf01_evidence
        if evidence["verdict"].lower() == "fail"
    ], inf01_evidence
    for required_anchor in (
        "An Automated Survey of Generative Artificial Intelligence",
        "GPT-4 Technical Report",
        "the GPT-4 Technical Report is the better choice",
        "more \"classic\" and \"foundational\"",
    ):
        assert any(
            required_anchor in evidence["highlighted_text"]
            for evidence in inf01_evidence
        ), required_anchor

    spt01 = next(case for case in data["cases"] if case["case_id"] == "SPT-01-A")
    assert spt01["source_path"].endswith(
        "webharbor_v13_spt_01_a_20260724_060856_"
        "903ef467-613e-4ad8-b9b8-469a5ce48314.json"
    ), spt01["source_path"]
    assert spt01["agent"]["summary"]["number_of_steps"] == 11
    assert spt01["agent"]["summary"]["is_successful"] is True
    assert spt01["judge"]["verdict"].lower() == "pass"

    mlm01 = next(case for case in data["cases"] if case["case_id"] == "MLM-01-A")
    assert mlm01["source_path"].endswith(
        "webharbor_v13_mlm_01_a_20260724_071004_"
        "f72af804-3871-44bd-9c16-34685a5322c9.json"
    ), mlm01["source_path"]
    assert mlm01["agent"]["summary"]["number_of_steps"] == 12
    assert mlm01["agent"]["summary"]["is_successful"] is True
    assert mlm01["judge"]["verdict"].lower() == "pass"
    mlm_suitability = [
        evidence
        for evidence in mlm01["judge"]["evidence"]
        if "cooking instructions" in evidence["highlighted_text"].lower()
        and "not full recipe" in evidence["highlighted_text"].lower()
    ]
    assert mlm_suitability, mlm01["judge"]["evidence"]
    assert all(
        evidence["verdict"].lower() == "partial"
        for evidence in mlm_suitability
    ), mlm_suitability

    hot01 = next(case for case in data["cases"] if case["case_id"] == "HOT-01-A")
    assert hot01["source_path"].endswith(
        "webharbor_v13_hot_01_a_20260724_070845_"
        "9375ec4c-95d3-4c49-a8df-9b3aebc8ccec.json"
    ), hot01["source_path"]
    assert hot01["agent"]["summary"]["number_of_steps"] == 7
    assert hot01["agent"]["summary"]["is_successful"] is False
    assert hot01["judge"]["verdict"].lower() == "fail"
    assert "zero task-valid hotels" in hot01["judge"]["reasoning"].lower()
    assert not [
        evidence
        for evidence in hot01["judge"]["evidence"]
        if evidence["verdict"].lower() == "fail"
    ], hot01["judge"]["evidence"]

    inf02 = next(case for case in data["cases"] if case["case_id"] == "INF-02-A")
    inf02_rejected_alternative = [
        evidence
        for evidence in inf02["judge"]["evidence"]
        if evidence["highlighted_text"].startswith(
            'But let me also consider "Amazon deforestation surged'
        )
    ]
    assert inf02_rejected_alternative, inf02["judge"]["evidence"]
    assert all(
        evidence["verdict"].lower() == "partial"
        for evidence in inf02_rejected_alternative
    ), inf02_rejected_alternative

    print(
        "PASS "
        f"conditions={len(response.conditions)} "
        f"grounded_evidence={evidence_count} "
        f"screenshots={screenshot_count} "
        f"html_bytes={len(html.encode('utf-8'))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
