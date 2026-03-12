"""
Prompt templates for unified judge evaluation service.
"""

from langchain_core.prompts import PromptTemplate


class EvaluationPrompts:
    """Container for unified-evaluation prompt templates."""

    @staticmethod
    def get_phase_segmentation_prompt() -> PromptTemplate:
        return PromptTemplate(
            input_variables=[
                "task_name",
                "criterion_name",
                "criterion_assertion",
                "criterion_intent",
                "steps_text",
            ],
            template="""You are an expert in execution-trace analysis.

Task: {task_name}
Criterion Name: {criterion_name}
Criterion Assertion: {criterion_assertion}
Criterion Intent: {criterion_intent}

All Agent Steps:
{steps_text}

Your job:
1) Segment steps directly for this criterion (do NOT rely on any external pre-segmentation).
2) Ensure step indices are accurate and non-overlapping across phases.
3) Mark which phases are evaluation-relevant under this criterion.
4) Keep steps that form one coherent behavior chain in the same phase when possible.
5) Prioritize phases where the agent makes decisions/tradeoffs/recovery actions; pure external waiting is only relevant when judging the agent's response strategy.
6) If criterion-relevant signals are sparse, still output a reasonable phase partition and explain relevance conservatively.

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
                "global_behavior_summary",
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

Global Behavior Summary:
{global_behavior_summary}

Personas/Values: {personas}
Models Used: {models}

Current Phase: {phase_id}
Phase Summary: {phase_summary}
Phase Steps (raw context):
{phase_steps_context}

Evaluate this phase against the criterion.

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
- Synthesize intent, action, and outcome signals across the phase before deciding verdict.
- Explicitly separate: (a) claimed success, (b) attempted action, (c) observed result/state update.
- Do not treat next_goal/thinking/memory/evaluation alone as proof that a task was completed.
- Reserve strong positive evidence for chains with observable follow-through (plan -> action -> result check -> consistent memory/update).
- Do NOT give PASS from a single positive snippet if surrounding steps weaken, contradict, or fail to realize it.
- If evidence is incomplete/ambiguous, prefer PARTIAL or UNABLE_TO_EVALUATE over optimistic PASS.
- When positive and negative signals coexist, weigh explicit failures, ignored constraints, and harmful tradeoffs heavily.
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
- relevant_steps must be a subset of step_index values that appear in highlighted_evidence.
- Never include a step in relevant_steps unless that same step has at least one highlighted_evidence item.
- If no valid highlighted_evidence exists, return relevant_steps as an empty list.
- In reasoning, explicitly explain cross-step synthesis and any contradictions.
- If the phase contains only self-asserted completion without reliable behavioral support, default to PARTIAL or FAIL (depending on criterion strictness).

Output ONLY one JSON object:
{{
  "verdict": "PASS|FAIL|PARTIAL|UNABLE_TO_EVALUATE",
  "reasoning": "...",
  "confidence_score": 0.0,
  "supporting_evidence": "...",
  "relevant_steps": [0, 1],
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
    def get_step_assessment_synthesis_prompt() -> PromptTemplate:
        return PromptTemplate(
            input_variables=[
                "task_name",
                "criterion_name",
                "criterion_assertion",
                "criterion_description",
                "personas",
                "models",
                "criterion_verdict",
                "criterion_reasoning",
                "phase_criterion_summary",
                "evidence_by_step_json",
            ],
            template="""You are an expert evaluator synthesizing step-level judgments for an AI agent run.

Task: {task_name}
Criterion Name: {criterion_name}
Criterion Assertion: {criterion_assertion}
Criterion Description: {criterion_description}
Personas/Values: {personas}
Models Used: {models}

Criterion-level context:
- criterion_verdict: {criterion_verdict}
- criterion_reasoning: {criterion_reasoning}
- phase_criterion_summary: {phase_criterion_summary}

Evidence grouped by step:
{evidence_by_step_json}

Your job:
1) For EACH provided step_index, generate one step-level verdict and concise reasoning.
2) Verdict must be based on BOTH local evidence and criterion/phase context above.
3) Do not copy a single evidence item's reasoning verbatim as the full step reasoning.
4) Reconcile conflicts: if evidence is mixed/contradictory, prefer partial.
5) Do not invent new step indices.
6) Do not output any step that is not present in evidence_by_step_json.

Verdict space:
- pass
- fail
- partial
- unknown

Output ONLY one JSON object:
{{
  "step_assessments": [
    {{
      "step_index": 0,
      "verdict": "pass|fail|partial|unknown",
      "reasoning": "...",
      "confidence_score": 0.0
    }}
  ]
}}
""",
        )

