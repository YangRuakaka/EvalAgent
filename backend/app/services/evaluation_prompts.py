"""
Prompt templates for judge evaluation service.

This module contains all LLM prompt templates used by the JudgeEvaluatorService
for evaluating agent behavior against criteria at different granularity levels.
"""

from langchain_core.prompts import PromptTemplate


class EvaluationPrompts:
    """Container for all evaluation prompt templates."""
    
    @staticmethod
    def get_step_level_prompt() -> PromptTemplate:
        """Get prompt template for step-level evaluation.
        
        Evaluates a single step in isolation without access to other steps.
        
        Returns:
            PromptTemplate for step-level evaluation
        """
        return PromptTemplate(
            input_variables=[
                "criterion_name",
                "criterion_assertion",
                "task_name",
                "step_index",
                "thinking",
                "memory",
                "evaluation_previous_goal",
                "action",
                "next_goal",
                "personas",
                "models"
            ],
            template="""You are an impartial and expert evaluator of AI agent behavior. Your task is to evaluate whether a specific step in an agent's execution satisfies a specific evaluation criterion.

EVALUATION GRANULARITY: STEP_LEVEL
Note: You are provided with the details of a SINGLE execution step. Do NOT assume information from previous or subsequent steps.

CRITERION TO EVALUATE:
Name: {criterion_name}
Assertion/How to verify: {criterion_assertion}

TASK CONTEXT:
Task Name: {task_name}
Agent Personas/Values: {personas}
Models Used: {models}

STEP DATA (The specific step to evaluate):
Step Index: {step_index}
Thinking Process: {thinking}
Memory: {memory}
Evaluation of Previous Goal: {evaluation_previous_goal}
Action: {action}
Next Goal: {next_goal}

---

Based on the criterion description and assertion, evaluate the agent's execution in this specific step.
Examine the following fields in the step data carefully:
- thinking/thinking_process: The agent's internal reasoning and decision making.
- evaluation_previous_goal: The agent's assessment of its previous actions.
- memory: The agent's current memory or context state.
- next_goal: The agent's planned goal or action for the next step.
- action: The actual action executed by the agent (e.g., navigate, click, type).

Provide your evaluation in JSON format:
{{
  "verdict": "PASS|FAIL|PARTIAL|UNABLE_TO_EVALUATE",
  "reasoning": "Detailed explanation (2-4 sentences) of your evaluation decision based ONLY on this step.",
  "confidence_score": 0.0-1.0,
  "supporting_evidence": "Specific quotes or observations from the step data",
  "highlighted_evidence": [
    {{
      "step_index": {step_index},
      "source_field": "evaluation|memory|thinking_process|next_goal|action",
      "highlighted_text": "Exact text from the step, do not use ellipses",
      "reasoning": "Relevance to criterion",
      "verdict": "pass|fail|partial"
    }}
  ]
}}
"""
        )
    
    @staticmethod
    def get_phase_level_prompt() -> PromptTemplate:
        """Get prompt template for phase-level evaluation.
        
        Evaluates a sequence of steps representing a distinct phase.
        Only sees steps within the current phase, not other phases.
        
        Returns:
            PromptTemplate for phase-level evaluation
        """
        return PromptTemplate(
            input_variables=[
                "criterion_name",
                "criterion_assertion",
                "task_name",
                "aggregated_steps",
                "raw_context",
                "personas",
                "models"
            ],
            template="""You are an impartial and expert evaluator of AI agent behavior. Your task is to evaluate whether a specific phase (sequence of steps) of an agent's execution satisfies a specific evaluation criterion.

EVALUATION GRANULARITY: PHASE_LEVEL
Note: You are provided with a sequence of steps representing a distinct phase of the task. Evaluate based on this sequence.

CRITERION TO EVALUATE:
Name: {criterion_name}
Assertion/How to verify: {criterion_assertion}

TASK CONTEXT:
Task Name: {task_name}
Agent Personas/Values: {personas}
Models Used: {models}

PHASE SUMMARY:
{aggregated_steps}

PHASE STEPS (Detailed execution trace for this phase):
{raw_context}

---

Based on the criterion, evaluate the agent's behavior during this phase.
Analyze the progression and consistency of the following fields across the steps:
- thinking/thinking_process
- evaluation_previous_goal
- memory
- next_goal
- action

Provide your evaluation in JSON format:
{{
  "verdict": "PASS|FAIL|PARTIAL|UNABLE_TO_EVALUATE",
  "reasoning": "Detailed explanation of your evaluation decision for this phase.",
  "confidence_score": 0.0-1.0,
  "supporting_evidence": "Specific quotes or observations from the phase steps",
  "highlighted_evidence": [
    {{
      "step_index": <index>,
      "source_field": "evaluation|memory|thinking_process|next_goal|action",
      "highlighted_text": "Exact text from the step, do not use ellipses",
      "reasoning": "Relevance",
      "verdict": "pass|fail|partial"
    }}
  ],
  "relevant_steps": [list of step indices relevant to this phase evaluation]
}}
"""
        )
    
    @staticmethod
    def get_global_summary_prompt() -> PromptTemplate:
        """Get prompt template for global-level evaluation.
        
        Evaluates the complete execution trace with all steps.
        Used for criteria about overall task completion, strategy, or consistency.
        
        Returns:
            PromptTemplate for global-level evaluation
        """
        return PromptTemplate(
            input_variables=[
                "criterion_name",
                "criterion_assertion",
                "task_name",
                "aggregated_steps",
                "raw_context",
                "personas",
                "models"
            ],
            template="""You are an impartial and expert evaluator of AI agent behavior. Your task is to evaluate whether the agent's COMPLETE execution satisfies a specific evaluation criterion.

EVALUATION GRANULARITY: GLOBAL_SUMMARY
Note: You are provided with the full execution trace and a high-level summary.

CRITERION TO EVALUATE:
Name: {criterion_name}
Assertion/How to verify: {criterion_assertion}

TASK CONTEXT:
Task Name: {task_name}
Agent Personas/Values: {personas}
Models Used: {models}

EXECUTION SUMMARY:
{aggregated_steps}

FULL EXECUTION TRACE:
{raw_context}

---

Based on the criterion, evaluate the agent's overall performance.
Analyze the consistency and effectiveness of the agent's actions throughout the task, considering all fields (thinking, evaluation, memory, goal, action).

Provide your evaluation in JSON format:
{{
  "verdict": "PASS|FAIL|PARTIAL|UNABLE_TO_EVALUATE",
  "reasoning": "Detailed explanation of your evaluation decision based on the full execution.",
  "confidence_score": 0.0-1.0,
  "supporting_evidence": "Specific quotes or observations from the trace",
  "highlighted_evidence": [
    {{
      "step_index": <index>,
      "source_field": "evaluation|memory|thinking_process|next_goal|action",
      "highlighted_text": "Exact text from the step, do not use ellipses",
      "reasoning": "Relevance",
      "verdict": "pass|fail|partial"
    }}
  ],
  "relevant_steps": [list of key step indices]
}}
"""
        )
    
    @staticmethod
    def get_merge_results_prompt() -> PromptTemplate:
        """Get prompt template for merging multiple evaluation results.
        
        Aggregates multiple sub-evaluations into a single criterion verdict.
        
        Returns:
            PromptTemplate for merging evaluation results
        """
        return PromptTemplate(
            input_variables=[
                "criterion_name",
                "criterion_assertion",
                "granularity_type",
                "individual_verdicts"
            ],
            template="""You are an expert aggregator evaluating multiple sub-evaluations for a single criterion.

CRITERION:
Name: {criterion_name}
Assertion/How to verify: {criterion_assertion}

EVALUATION TYPE: {granularity_type}
(STEP_LEVEL = individual step evaluations, PHASE_LEVEL = phase/cluster evaluations)

INDIVIDUAL EVALUATION RESULTS:
{individual_verdicts}

---

Based on these individual evaluations, provide an overall verdict for the criterion. Consider:
- How many steps/clusters passed vs failed?
- Are there critical failures that make the whole criterion fail?
- Is the failure pattern consistent or isolated?
- What is the overall trend across all evaluations?

Provide your aggregated verdict in JSON format:
{{
  "verdict": "PASS|FAIL|PARTIAL|UNABLE_TO_EVALUATE",
  "reasoning": "Detailed explanation (2-4 sentences) of how you aggregated these individual results into the final verdict",
  "confidence_score": 0.0-1.0,
  "aggregation_summary": "Brief summary of the aggregation logic (1-2 sentences)",
  "pass_rate": 0.0-1.0
}}

Guidelines:
- PASS: Overall, the criterion is satisfied across evaluations
- FAIL: Critical failures detected or majority of evaluations failed
- PARTIAL: Mixed results with some successes and some failures
- UNABLE_TO_EVALUATE: Insufficient data to make a determination
- confidence_score: Your confidence in this aggregated verdict (0 = very uncertain, 1 = very confident)
- pass_rate: Fraction of evaluations that passed (0.0 to 1.0)
"""
        )

    @staticmethod
    def get_overall_criterion_assessment_prompt() -> PromptTemplate:
        """Get prompt template for generating overall assessment for a criterion.
        
        This prompt generates an overall pass/fail assessment and reasoning
        based on the detailed step evaluations and criterion properties.
        
        Returns:
            PromptTemplate for overall criterion assessment
        """
        return PromptTemplate(
            input_variables=[
                "criterion_title",
                "criterion_assertion",
                "criterion_description",
                "task_name",
                "granularity",
                "personas",
                "models",
                "evaluation_details",
                "involved_steps_summary"
            ],
            template="""You are an expert evaluator assessing the overall performance of an AI agent against a specific criterion.

CRITERION DEFINITION:
Title: {criterion_title}
Assertion/How to verify: {criterion_assertion}
Description: {criterion_description}

TASK CONTEXT:
Task Name: {task_name}
Agent Personas/Values: {personas}
Models Used: {models}

EVALUATION GRANULARITY: {granularity}

DETAILED EVALUATION RESULTS:
{evaluation_details}

INVOLVED STEPS SUMMARY:
{involved_steps_summary}

---

Based on the criterion definition, the detailed evaluation results, and the involved steps, provide an OVERALL assessment.

Consider:
1. Does the agent's behavior align with the criterion's assertion across all evaluated steps?
2. Are there consistent patterns of success or failure?
3. Do the high-confidence evaluations support a clear verdict?
4. What is the overall trend and quality of performance?

Provide your overall assessment in JSON format:
{{
  "overall_assessment": "pass|fail|partial",
  "overall_reasoning": "Comprehensive explanation (3-5 sentences) of the overall assessment. Include key findings from the evaluation details and why this final verdict was reached.",
  "confidence_score": 0.0-1.0
}}

Guidelines for overall_assessment:
- "pass": The agent clearly satisfies the criterion across the evaluated steps
- "fail": The agent clearly fails to satisfy the criterion, with critical issues identified
- "partial": The agent partially satisfies the criterion with mixed results
- confidence_score: Your confidence in this overall assessment (0 = very uncertain, 1 = very confident)
"""
        )

