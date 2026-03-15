import asyncio
from types import SimpleNamespace

from app.schemas.judge import AgentStepField, EvaluateStatus, EvidenceCitation
from app.services.judge_evaluator import JudgeEvaluatorService


class _QueueLLM:
    def __init__(self, responses):
        self._responses = list(responses)

    def __call__(self, _prompt_value):
        if self._responses:
            return SimpleNamespace(content=self._responses.pop(0))
        return SimpleNamespace(content="{}")


class _FakeLLMFactory:
    def __init__(self, responses):
        self._llm = _QueueLLM(responses)

    def get_langchain_llm(self, _model_name=None, **_kwargs):
        return self._llm


class _CaptureInvokeService(JudgeEvaluatorService):
    def __init__(self):
        super().__init__(llm_factory=_FakeLLMFactory(["{}"]))
        self.captured_invoke_dicts = []

    async def _invoke_chain_async(self, chain, invoke_dict, llm_semaphore=None):
        del chain, llm_semaphore
        self.captured_invoke_dicts.append(dict(invoke_dict))
        return SimpleNamespace(content="{}")


def _build_steps(step_count=6):
    steps = []
    for idx in range(step_count):
        steps.append(
            {
                "thinking_process": f"Step {idx} thinking about booking option {idx}",
                "memory": f"Remembered constraint {idx}",
                "evaluation_previous_goal": f"Evaluated previous goal at step {idx}",
                "action": {"type": "click", "target": f"button-{idx}"},
                "next_goal": f"Proceed to next sub-goal {idx}",
            }
        )
    return steps


def test_prompt_templates_are_bound_to_refactored_methods():
    service = JudgeEvaluatorService(llm_factory=_FakeLLMFactory(["{}"]))

    assert set(service.criteria_interpretation_template.input_variables) == {
        "task_name",
        "criterion_name",
        "criterion_assertion",
    }
    assert set(service.phase_segmentation_template.input_variables) == {
        "task_name",
        "criterion_name",
        "criterion_intent",
        "steps_text",
    }
    assert set(service.phase_evidence_extraction_template.input_variables) == {
        "criterion_name",
        "criterion_assertion",
        "criterion_intent",
        "phase_id",
        "phase_summary",
        "phase_steps_context",
    }
    assert set(service.phase_step_verdict_synthesis_template.input_variables) == {
        "criterion_name",
        "criterion_assertion",
        "criterion_intent",
        "phase_id",
        "phase_summary",
        "verified_evidence_json",
        "phase_steps_context",
    }
    assert set(service.phase_overall_synthesis_template.input_variables) == {
        "task_name",
        "criterion_name",
        "criterion_assertion",
        "criterion_intent",
        "phase_evaluations_summary",
        "aggregated_evidence_json",
    }
    assert set(service.multi_condition_ranking_template.input_variables) == {
        "task_name",
        "criterion_name",
        "criterion_assertion",
        "criterion_description",
        "condition_summaries_json",
    }


def test_evaluate_criterion_unified_runs_with_refactored_prompt_params():
    responses = [
        '{"criterion_intent": "Prioritize successful booking completion with constraint-aware tradeoffs."}',
        (
            '{"phases": [{"phase_id": "phase_0", "semantic_label": "booking", '
            '"step_indices": [0, 1, 2, 3, 4, 5], "phase_summary": "booking flow", '
            '"relevant_to_evaluation": true}], "relevant_phase_ids": ["phase_0"], '
            '"segmentation_reasoning": "single coherent chain"}'
        ),
        (
            '{"highlighted_evidence": ['
            '{"step_index": 0, "source_field": "thinking_process", '
            '"highlighted_text": "Step 0 thinking about booking option 0", '
            '"verdict": "pass", "reasoning": "Initial intent setup."},'
            '{"step_index": 3, "source_field": "next_goal", '
            '"highlighted_text": "Proceed to next sub-goal 3", '
            '"verdict": "pass", "reasoning": "Shows progress toward completion."}'
            ']}'
        ),
        (
            '{"step_assessments": ['
            '{"step_index": 0, "verdict": "pass", "reasoning": "Reasonable intent.", "confidence_score": 0.8},'
            '{"step_index": 3, "verdict": "pass", "reasoning": "Progressed effectively.", "confidence_score": 0.7}'
            ']}'
        ),
        (
            '{"verdict": "PASS", "reasoning": "Phase evidence supports successful criterion behavior.", '
            '"confidence_score": 0.76, "supporting_evidence": "steps 0 and 3", '
            '"aggregation_summary": "Consistent positive signals."}'
        ),
    ]

    service = JudgeEvaluatorService(llm_factory=_FakeLLMFactory(responses))
    result = asyncio.run(
        service.evaluate_criterion_unified(
            criterion_name="Task Completion",
            criterion_assertion="Agent should complete booking",
            task_name="Book flight",
            personas=["Cost Savings"],
            models=["deepseek-chat"],
            all_steps=_build_steps(6),
            model_name="deepseek-chat",
        )
    )

    assert result.verdict == "PASS"
    assert result.reasoning
    assert result.highlighted_evidence
    assert all(item.verdict is not None for item in result.highlighted_evidence)
    assert result.used_granularity.value == "phase_level"


def test_step_assessment_synthesis_uses_refactored_step_verdict_prompt():
    responses = [
        (
            '{"step_assessments": ['
            '{"step_index": 2, "verdict": "partial", '
            '"reasoning": "Mixed evidence on goal progress.", "confidence_score": 0.62}'
            ']}'
        )
    ]
    service = JudgeEvaluatorService(llm_factory=_FakeLLMFactory(responses))

    evidence_by_step = {
        2: [
            EvidenceCitation(
                step_index=2,
                source_field=AgentStepField.THINKING_PROCESS,
                highlighted_text="Step 2 thinking about booking option 2",
                reasoning="Tradeoff considered",
                verdict=EvaluateStatus.PARTIAL,
            )
        ]
    }

    step_assessments = asyncio.run(
        service.synthesize_step_assessments(
            task_name="Book flight",
            criterion_name="Task Completion",
            criterion_assertion="Agent should complete booking",
            criterion_description="",
            personas=["Cost Savings"],
            models=["deepseek-chat"],
            criterion_verdict="pass",
            criterion_reasoning="Criterion-level reasoning",
            phase_criterion_summary="Single phase summary",
            evidence_by_step=evidence_by_step,
            model_name="deepseek-chat",
        )
    )

    assert 2 in step_assessments
    assert step_assessments[2]["verdict"] == "partial"
    assert step_assessments[2]["confidence_score"] == 0.62


def test_step_text_builders_fill_null_literal_for_empty_fields():
    service = JudgeEvaluatorService(llm_factory=_FakeLLMFactory(["{}"]))
    steps = [
        {
            "thinking_process": None,
            "thinking": None,
            "memory": None,
            "evaluation_previous_goal": None,
            "action": None,
            "next_goal": "",
        }
    ]

    segmentation_text = service._format_steps_for_unified_segmentation(steps)
    assert "Thinking: null" in segmentation_text
    assert "Memory: null" in segmentation_text
    assert "Evaluation: null" in segmentation_text
    assert "Action: null" in segmentation_text
    assert "Next Goal: null" in segmentation_text

    phase_context = service._build_phase_steps_context(steps, [0])
    assert "Thinking Process: null" in phase_context
    assert "Memory: null" in phase_context
    assert "Evaluation of Previous Goal: null" in phase_context
    assert "Action: null" in phase_context
    assert "Next Goal: null" in phase_context


def test_criterion_interpretation_invoke_dict_uses_null_for_empty_values():
    service = _CaptureInvokeService()

    criterion_intent = asyncio.run(
        service._interpret_criterion_intent_async(
            task_name="",
            criterion_name="",
            criterion_assertion="",
            personas=[],
            model_name="deepseek-chat",
        )
    )

    assert criterion_intent == "null"
    assert service.captured_invoke_dicts
    invoke_dict = service.captured_invoke_dicts[0]
    assert invoke_dict["task_name"] == "null"
    assert invoke_dict["criterion_name"] == "null"
    assert invoke_dict["criterion_assertion"] == "null"
    assert "personas" not in invoke_dict


def test_rank_multi_conditions_parses_ranking_output():
    responses = [
        (
            '{"ranking": ['
            '{"condition_id": "cond_a", "reasoning": "pass with stronger grounded evidence"}, '
            '{"condition_id": "cond_b", "reasoning": "partial with weaker evidence"}'
            '], "ranking_reasoning": "overall first, evidence second", '
            '"comparison_summary": "cond_a > cond_b"}'
        )
    ]
    service = JudgeEvaluatorService(llm_factory=_FakeLLMFactory(responses))

    ranking = asyncio.run(
        service.rank_multi_conditions(
            task_name="Book flight",
            criterion_name="Value Alignment",
            criterion_assertion="Agent aligns actions to assigned value",
            criterion_description="",
            condition_summaries=[
                {"condition_id": "cond_a", "overall_assessment": "pass", "evidence_score_hint": 0.8},
                {"condition_id": "cond_b", "overall_assessment": "partial", "evidence_score_hint": 0.4},
            ],
            model_name="deepseek-chat",
        )
    )

    assert ranking["ranking"]
    assert ranking["ranking"][0]["condition_id"] == "cond_a"
    assert ranking["ranking"][1]["condition_id"] == "cond_b"
    assert ranking["ranking_reasoning"] == "overall first, evidence second"
    assert ranking["comparison_summary"] == "cond_a > cond_b"


def test_rank_multi_conditions_filters_unknown_condition_ids():
    responses = [
        (
            '{"ranking": ['
            '{"condition_id": "unknown_cond", "reasoning": "should be ignored"}, '
            '{"condition_id": "cond_b", "reasoning": "valid"}'
            ']}'
        )
    ]
    service = JudgeEvaluatorService(llm_factory=_FakeLLMFactory(responses))

    ranking = asyncio.run(
        service.rank_multi_conditions(
            task_name="Book flight",
            criterion_name="Value Alignment",
            criterion_assertion="Agent aligns actions to assigned value",
            criterion_description="",
            condition_summaries=[
                {"condition_id": "cond_a", "overall_assessment": "pass"},
                {"condition_id": "cond_b", "overall_assessment": "partial"},
            ],
            model_name="deepseek-chat",
        )
    )

    assert len(ranking["ranking"]) == 1
    assert ranking["ranking"][0]["condition_id"] == "cond_b"
