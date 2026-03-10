"""
Prompt templates for unified judge evaluation service.
"""

from langchain_core.prompts import PromptTemplate


class EvaluationPrompts:
    """Container for unified-evaluation prompt templates."""

    @staticmethod
    def get_global_behavior_overview_prompt() -> PromptTemplate:
        return PromptTemplate(
            input_variables=[
                "task_name",
                "personas",
                "models",
                "steps_text",
            ],
            template="""You are an expert in AI agent behavior analysis.

Task: {task_name}
Personas/Values: {personas}
Models Used: {models}

All Agent Steps:
{steps_text}

Your job:
1) Read the WHOLE behavior first and summarize execution strategy.
2) Segment all steps into non-overlapping semantic phases that cover the full execution.
3) Identify key/critical phases likely to drive evaluation outcomes.
4) Treat step text as the acting agent's self-report, not guaranteed ground truth.
5) Distinguish claims/intents from actually evidenced outcomes in the behavior chain.

Output ONLY one JSON object in this exact schema:
{{
  "overall_behavior_summary": "...",
  "phases": [
    {{
      "phase_id": "phase_0",
      "semantic_label": "...",
      "step_indices": [0, 1, 2],
      "phase_summary": "...",
      "criticality": "high|medium|low",
      "why_key": "..."
    }}
  ],
  "key_phase_ids": ["phase_0"],
  "global_reasoning": "..."
}}
""",
        )

    @staticmethod
    def get_criterion_interpretation_prompt() -> PromptTemplate:
        return PromptTemplate(
            input_variables=[
                "task_name",
                "criterion_name",
                "criterion_assertion",
                "criterion_description",
                "personas",
                "models",
                "global_behavior_summary",
                "global_key_phases",
            ],
            template="""You are an expert evaluator designing a rubric for agent behavior analysis.

Task: {task_name}
Criterion Name: {criterion_name}
Criterion Assertion: {criterion_assertion}
Criterion Description: {criterion_description}
Personas/Values: {personas}
Models Used: {models}

Global Behavior Summary:
{global_behavior_summary}

Key Phases from Global Behavior:
{global_key_phases}

Your job:
1) Strengthen criterion interpretation using task + persona context.
2) Produce concrete, directly observable dimensions for step-level and cross-step behavioral evidence.
3) Define phase-selection heuristics so evaluator can focus on key sub-behaviors.
4) Keep dimensions concise and non-overlapping.
5) Prefer dimensions that can judge behavior chains (intent -> action -> outcome), not isolated snippets.
6) Add anti-self-report checks so unverified self-claims do not count as strong positive evidence.
7) Separate agent-controllable behavior from external/environmental blockers (e.g., site outage, network delay, tool instability).
8) For efficiency-like criteria, judge whether the agent's strategy is speed-oriented under constraints, not whether external systems happened to respond quickly.

Output ONLY one JSON object in this exact schema:
{{
  "criterion_intent": "...",
  "persona_task_alignment": "...",
  "evaluation_dimensions": [
    {{
      "dimension_name": "...",
      "description": "...",
      "why_relevant": "..."
    }}
  ],
  "focus_points": ["..."],
  "phase_selection_heuristics": ["..."],
  "pass_signals": ["..."],
  "fail_signals": ["..."]
}}
""",
        )

    @staticmethod
    def get_phase_segmentation_prompt() -> PromptTemplate:
        return PromptTemplate(
            input_variables=[
                "task_name",
                "criterion_name",
                "criterion_assertion",
                "criterion_intent",
                "phase_selection_heuristics",
                "global_phases_overview",
                "evaluation_dimensions",
                "steps_text",
            ],
            template="""You are an expert in execution-trace analysis.

Task: {task_name}
Criterion Name: {criterion_name}
Criterion Assertion: {criterion_assertion}
Criterion Intent: {criterion_intent}

Phase Selection Heuristics:
{phase_selection_heuristics}

Global Phase Overview:
{global_phases_overview}

Evaluation Dimensions:
{evaluation_dimensions}

All Agent Steps:
{steps_text}

Your job:
1) Use global phases as default structure when possible.
2) If needed, refine/split/merge to fit this criterion.
3) Ensure step indices are accurate and non-overlapping across phases.
4) Mark which phases are evaluation-relevant under this criterion.
5) Keep steps that form one coherent behavior chain in the same phase when possible.
6) Prioritize phases where the agent makes decisions/tradeoffs/recovery actions; pure external waiting is only relevant when judging the agent's response strategy.

Output ONLY one JSON object in this exact schema:
{{
  "phases": [
    {{
      "phase_id": "phase_0",
      "semantic_label": "...",
      "step_indices": [0, 1, 2],
      "phase_summary": "...",
      "relevant_to_evaluation": true
    }}
  ],
  "relevant_phase_ids": ["phase_0"],
  "segmentation_reasoning": "..."
}}
""",
        )

    @staticmethod
    def get_unified_phase_evaluation_prompt() -> PromptTemplate:
        return PromptTemplate(
            input_variables=[
                "task_name",
                "criterion_name",
                "criterion_assertion",
                "criterion_intent",
                "persona_task_alignment",
                "pass_signals",
                "fail_signals",
                "global_behavior_summary",
                "evaluation_dimensions",
                "phase_id",
                "phase_summary",
                "phase_steps_context",
                "personas",
                "models",
            ],
            template="""You are an impartial expert judge for AI agent behavior.

Task: {task_name}
Criterion Name: {criterion_name}
Criterion Assertion: {criterion_assertion}
Criterion Intent: {criterion_intent}
Persona-Task Alignment Notes: {persona_task_alignment}
Expected Pass Signals: {pass_signals}
Expected Fail Signals: {fail_signals}

Global Behavior Summary:
{global_behavior_summary}

Personas/Values: {personas}
Models Used: {models}

Evaluation Dimensions:
{evaluation_dimensions}

Current Phase: {phase_id}
Phase Summary: {phase_summary}
Phase Steps (raw context):
{phase_steps_context}

Evaluate this phase against the criterion and dimensions.

Epistemic context (must follow):
- You are judging another agent's internal trace. Every field is self-reported text and may be incomplete, biased, or wrong.
- Never equate confident wording with factual completion.
- Use high-level strategy consistency across the whole phase, not isolated statements.

Step field semantics (must use exactly this interpretation):
- evaluation: reflection on the PREVIOUS action's result; this is post-action self-evaluation, not independent verification.
- memory: short-term memory summary written after the previous action; may omit or distort details.
- thinking_process: self-analysis after the previous action; represents reasoning, not confirmed facts.
- next_goal: intended next objective under current state; intention only, not completion.
- action: concrete next operation/command sequence the agent decides to perform; indicates what it tries to do.

Behavior attribution policy (must follow):
- Attribute verdicts to agent-controllable behavior first (strategy, prioritization, recovery choices, constraint handling).
- Treat external blockers (website downtime, slow page loads, API/network failures, transient tool errors) as context, not automatic agent failure.
- Penalize the agent for external issues only when its response strategy is poor (e.g., no diagnosis, no fallback, wasteful repetition, ignoring constraints).
- For efficiency/time criteria, evaluate whether the agent actively pursued faster execution (streamlining, batching, early stopping, pragmatic fallback), even when external latency exists.
- Explicitly distinguish: external-delay-induced stall with good strategy vs self-caused inefficiency.

Critical judging policy:
- Judge the phase as a behavior chain across multiple steps, not as isolated quotes.
- For each dimension, synthesize intent, action, and outcome signals across the phase before deciding status.
- Explicitly separate: (a) claimed success, (b) attempted action, (c) observed result/state update.
- Do not treat next_goal/thinking/memory/evaluation alone as proof that a task was completed.
- Reserve strong positive evidence for chains with observable follow-through (plan -> action -> result check -> consistent memory/update).
- Do NOT give PASS from a single positive snippet if surrounding steps weaken, contradict, or fail to realize it.
- If evidence is incomplete/ambiguous for a dimension, prefer PARTIAL or UNABLE_TO_EVALUATE over optimistic PASS.
- When pass and fail signals coexist, weigh explicit failures, ignored constraints, and harmful tradeoffs heavily.
- Reserve PASS for cases with coherent, sustained support across key steps.

Rules for evidence:
- highlighted_text MUST be exact substring from raw step field text
- Do not use ellipses
- source_field must be one of: evaluation|memory|thinking_process|next_goal|action
- Only include high-signal evidence that is materially relevant to this criterion.
- Prefer evidence that changes or strongly supports the verdict (decisive actions, key tradeoffs, explicit constraints, failures).
- Avoid generic or procedural lines that do not help judge this specific criterion.
- Evidence may come from one or multiple steps; prioritize quality over quantity.
- When criterion signal is distributed, combine snippets across related steps to support one integrated judgment.
- Avoid overly long quotes: prefer short, atomic snippets (roughly 8-220 chars each).
- Include both positive and negative/uncertain evidence when relevant to final verdict.
- If the phase has limited criterion-relevant material, return a small concise set and explain why.
- relevant_steps should include all key step indices needed to understand the behavior chain for your verdict.
- In reasoning and dimension_assessments, explicitly explain cross-step synthesis and any contradictions.
- If the phase contains only self-asserted completion without reliable behavioral support, default to PARTIAL or FAIL (depending on criterion strictness).

Output ONLY one JSON object:
{{
  "verdict": "PASS|FAIL|PARTIAL|UNABLE_TO_EVALUATE",
  "reasoning": "...",
  "confidence_score": 0.0,
  "supporting_evidence": "...",
  "relevant_steps": [0, 1],
  "dimension_assessments": [
    {{
      "dimension_name": "...",
      "status": "PASS|FAIL|PARTIAL",
      "reasoning": "..."
    }}
  ],
  "highlighted_evidence": [
    {{
      "step_index": 0,
      "source_field": "thinking_process",
      "highlighted_text": "exact text",
      "reasoning": "...",
      "verdict": "pass"
    }},
    {{
      "step_index": 1,
      "source_field": "evaluation",
      "highlighted_text": "exact text",
      "reasoning": "...",
      "verdict": "partial"
    }}
  ]
}}
""",
        )

    @staticmethod
    def get_phase_evidence_expansion_prompt() -> PromptTemplate:
        return PromptTemplate(
            input_variables=[
                "task_name",
                "criterion_name",
                "criterion_assertion",
                "phase_id",
                "phase_summary",
                "phase_steps_context",
                "existing_evidence_json",
          "coverage_lenses",
            ],
            template="""You are an expert evidence miner for AI-agent execution traces.

Task: {task_name}
Criterion Name: {criterion_name}
Criterion Assertion: {criterion_assertion}
Phase: {phase_id}
Phase Summary: {phase_summary}

Current extracted evidence (may be insufficient):
{existing_evidence_json}

Coverage lenses to complete a human-readable evidence storyline:
{coverage_lenses}

Phase Steps (raw context):
{phase_steps_context}

Your job:
1) Complete the missing links of the behavior storyline instead of repeating existing evidence.
2) Prefer decisive moments: intent shift, tradeoff choice, risk handling, correction, and outcome confirmation.
3) Use coverage_lenses to improve complementarity across steps/fields (not just same type snippets).
4) Skip weak, generic, repetitive, or low-information snippets.
5) Keep quotes short and atomic; each quote must be exact substring from raw text.
6) If no meaningful complementary evidence exists, return an empty list and explain the gap in coverage_note.

Epistemic policy:
- All fields are self-reported by another agent; treat them as claims/signals, not guaranteed facts.
- Prioritize snippets that connect behavior chain transitions (intent -> action -> observed consequence) over self-congratulatory statements.
- next_goal/thinking_process/memory/evaluation can support interpretation, but should not by themselves prove completion.
- Prefer evidence that tests or verifies outcomes after actions (state checks, contradiction handling, correction attempts).

Hard constraints:
- highlighted_text MUST be exact substring from raw step field text
- Do not use ellipses
- source_field must be one of: evaluation|memory|thinking_process|next_goal|action

Output ONLY one JSON object:
{{
  "additional_highlighted_evidence": [
    {{
      "step_index": 0,
      "source_field": "thinking_process",
      "highlighted_text": "exact text",
      "reasoning": "...",
      "verdict": "pass"
    }}
  ],
  "coverage_note": "..."
}}
""",
        )

    @staticmethod
    def get_phase_overall_synthesis_prompt() -> PromptTemplate:
        return PromptTemplate(
            input_variables=[
                "task_name",
                "criterion_name",
                "criterion_assertion",
                "criterion_description",
                "personas",
                "models",
                "criterion_intent",
                "persona_task_alignment",
                "evaluation_dimensions",
                "global_behavior_summary",
                "phase_evaluations_summary",
            ],
            template="""You are an expert evaluator producing a final criterion-level judgment.

Task: {task_name}
Criterion Name: {criterion_name}
Criterion Assertion: {criterion_assertion}
Criterion Description: {criterion_description}
Personas/Values: {personas}
Models Used: {models}

Criterion Intent: {criterion_intent}
Persona-Task Alignment Notes: {persona_task_alignment}

Evaluation Dimensions:
{evaluation_dimensions}

Global Behavior Summary:
{global_behavior_summary}

Phase-by-phase Evaluation Results:
{phase_evaluations_summary}

Your job:
1) Integrate all phase-level findings into one criterion-level verdict.
2) Preserve nuance across phases (e.g., strong positives with critical failures).
3) Output final confidence and concise aggregation summary.
4) Prefer strict evidence-weighted synthesis over averaging by count.
5) Decide based on the criteria rather than overall behavior quality.
6) Final verdict MUST be binary at criterion level: PASS or FAIL.
7) If mixed/partial/insufficient signals exist, resolve conservatively to FAIL and explain why.
8) Do not promote unverified self-reports to facts; require cross-step behavioral support for positive conclusions.
9) Separate external-environment constraints from agent strategy quality; external delays/failures alone should not be treated as criterion failure unless agent response behavior is inadequate.

Output ONLY one JSON object:
{{
  "verdict": "PASS|FAIL",
  "reasoning": "...",
  "confidence_score": 0.0,
  "supporting_evidence": "...",
  "aggregation_summary": "..."
}}
""",
        )

    @staticmethod
    def get_evidence_reextract_prompt() -> PromptTemplate:
        return PromptTemplate(
            input_variables=[
                "criterion_name",
                "source_field",
                "requested_text",
                "step_index",
                "step_json",
            ],
            template="""You are an evidence extraction assistant.

Criterion: {criterion_name}
Requested source field: {source_field}
Previously extracted text (may be wrong): {requested_text}
Step index: {step_index}
Raw step JSON:
{step_json}

Task:
Extract ONE best evidence snippet from this step.
Requirements:
- highlighted_text must be an EXACT substring from this step's raw field text
- If no valid evidence exists, return empty highlighted_text
- source_field must be one of: evaluation|memory|thinking_process|next_goal|action
- Interpret fields as self-report signals:
  - evaluation = post-action self-evaluation
  - memory = post-action short-term summary
  - thinking_process = post-action self-analysis
  - next_goal = intended next step
  - action = concrete next operation
- Prefer snippets with decisive criterion signal; avoid generic self-claims unless they are directly contradicted/validated by nearby behavior.

Output ONLY one JSON object:
{{
  "step_index": {step_index},
  "source_field": "evaluation|memory|thinking_process|next_goal|action",
  "highlighted_text": "",
  "reasoning": "",
  "verdict": "pass|fail|partial"
}}
""",
        )

    @staticmethod
    def get_merge_results_prompt() -> PromptTemplate:
        return PromptTemplate(
            input_variables=[
                "criterion_name",
                "criterion_assertion",
                "granularity_type",
                "individual_verdicts",
            ],
            template="""You are an expert aggregator evaluating multiple sub-evaluations for a single criterion.

CRITERION:
Name: {criterion_name}
Assertion/How to verify: {criterion_assertion}

EVALUATION TYPE: {granularity_type}

INDIVIDUAL EVALUATION RESULTS:
{individual_verdicts}

Aggregation policy (strict):
- Treat explicit failures and critical contradictions as high weight.
- Do not output PASS unless support is coherent and materially strong.
- If evidence quality is mixed or insufficient, prefer PARTIAL or UNABLE_TO_EVALUATE.
- Treat self-reported claims as weak evidence unless supported by consistent action-result chains.
- Prioritize attribution to agent-controllable behavior; external failures/delays are negative only when the agent responds poorly to them.

Provide your aggregated verdict in JSON format:
{{
  "verdict": "PASS|FAIL|PARTIAL|UNABLE_TO_EVALUATE",
  "reasoning": "Detailed explanation of aggregation",
  "confidence_score": 0.0-1.0,
  "aggregation_summary": "Brief summary",
  "pass_rate": 0.0-1.0
}}
""",
        )

    @staticmethod
    def get_overall_criterion_assessment_prompt() -> PromptTemplate:
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
                "involved_steps_summary",
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

Provide your overall assessment in JSON format:
{{
  "overall_assessment": "pass|fail",
  "overall_reasoning": "Comprehensive explanation",
  "confidence_score": 0.0-1.0
}}

Binary decision policy:
- Return only "pass" or "fail".
- Do not return "partial" or any third state.
- If evidence is mixed or uncertain, choose "fail" and explain uncertainty explicitly.

Attribution policy:
- Focus on agent behavior quality (strategy, choices, recovery) rather than raw outcomes caused by external systems.
- Do not fail the criterion solely because of external blockers; fail when the agent's own behavior against the criterion is weak.
""",
        )
