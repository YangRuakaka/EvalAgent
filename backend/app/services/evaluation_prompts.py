"""
Prompt templates for the 5-step LLM-as-judge evaluation pipeline.

Pipeline (5 LLM calls, in order):
  LLM 1 — get_criteria_interpretation_prompt   : interpret criterion semantics
  LLM 2 — get_phase_segmentation_prompt        : segment trace into behavior phases
  LLM 3 — get_phase_evidence_extraction_prompt : extract evidence per phase (no verdict)
  [Program] substring verification             : filter evidence to exact matches
  LLM 4 — get_phase_step_verdict_synthesis_prompt : generate step verdicts per phase
  LLM 5 — get_phase_overall_synthesis_prompt   : produce final criterion-level PASS/FAIL
"""

from langchain_core.prompts import PromptTemplate


class EvaluationPrompts:
    """Container for judge-pipeline prompt templates."""

    # ------------------------------------------------------------------
    # LLM 1 — Criteria Interpretation
    # Input:  task_name, criterion_name, criterion_assertion, personas
    # Output: criterion_intent
    # ------------------------------------------------------------------
    @staticmethod
    def get_criteria_interpretation_prompt() -> PromptTemplate:
        return PromptTemplate(
            input_variables=[
                "task_name",
                "criterion_name",
                "criterion_assertion",
                "personas",
            ],
            template="""You are an expert AI evaluation designer.

Task: {task_name}
Criterion Name: {criterion_name}
Criterion Assertion: {criterion_assertion}
Personas/Values: {personas}

Your job:
1) Produce one detailed criterion_intent that integrates: the criterion assertion itself, the current task context, and the persona/value priorities.
2) Clarify what concrete agent behaviors and decision patterns are in-scope for this criterion under this task/persona setting.
3) Clarify what is out-of-scope to avoid drifting into unrelated quality dimensions.
4) Make criterion_intent actionable for downstream segmentation/evidence/verdict synthesis.

Output ONLY one JSON object:
{{
  "criterion_intent": "..."
}}
""",
        )

    # ------------------------------------------------------------------
    # LLM 2 — Phase Segmentation
    # Input:  task_name, criterion_name, criterion_intent, steps_text
    # Output: phases, relevant_phase_ids, segmentation_reasoning
    # ------------------------------------------------------------------
    @staticmethod
    def get_phase_segmentation_prompt() -> PromptTemplate:
        return PromptTemplate(
            input_variables=[
                "task_name",
                "criterion_name",
                "criterion_intent",
                "steps_text",
            ],
            template="""You are an expert in execution-trace analysis.

Task: {task_name}
Criterion Name: {criterion_name}
Criterion Intent: {criterion_intent}

All Agent Steps:
{steps_text}

Your job:
1) Segment steps directly for this criterion (do NOT rely on any external pre-segmentation).
2) Ensure step indices are accurate and non-overlapping across phases.
3) Mark which phases are evaluation-relevant under this criterion.
4) Keep steps that form one coherent behavior chain in the same phase when possible.
5) Prioritize phases where the agent makes decisions/tradeoffs/recovery actions;

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

    # ------------------------------------------------------------------
    # LLM 3 — Phase Evidence Extraction  (evidence only, no verdict)
    # Input:  criterion_name, criterion_assertion, criterion_intent,
    #         phase_id, phase_summary, phase_steps_context
    # Output: highlighted_evidence
    # ------------------------------------------------------------------
    @staticmethod
    def get_phase_evidence_extraction_prompt() -> PromptTemplate:
        return PromptTemplate(
            input_variables=[
                "criterion_name",
                "criterion_assertion",
                "criterion_intent",
                "phase_id",
                "phase_summary",
                "phase_steps_context",
            ],
            template="""You are an expert evidence miner for AI-agent execution traces.

Criterion Name: {criterion_name}
Criterion Assertion: {criterion_assertion}
Criterion Intent: {criterion_intent}
Phase: {phase_id}
Phase Summary: {phase_summary}

Phase Steps (raw context):
{phase_steps_context}

Your job (evidence extraction ONLY — no verdict):
1) Extract short, exact-substring snippets from the step fields that are directly relevant to this criterion.
2) Cover the behavior storyline: intent setup → action decisions → outcome signals.
3) Prefer decisive moments: tradeoff choices, constraint handling, corrections, outcome verification.
4) Include both positive and negative/uncertain signals when present.
5) Avoid generic or procedural lines that do not distinguish this criterion from others.
6) Keep snippets short and atomic (roughly 8–220 chars each); no ellipses.
7) If no high-signal evidence exists for a step or field, skip it rather than forcing low-value quotes.

Epistemic rules:
- All fields are self-reported by the agent; treat as claims/signals, not verified facts.
- next_goal/thinking_process/memory/evaluation can support interpretation but do not prove completion alone.
- Prefer snippets that connect behavior chain transitions over self-congratulatory statements.

Step field semantics:
- evaluation: reflection on the PREVIOUS action's result (post-action, not independent verification)
- memory: short-term memory after the previous action (may omit or distort details)
- thinking_process: self-analysis after the previous action (reasoning, not confirmed facts)
- next_goal: intended next objective under current state (intention only, not completion)
- action: concrete operation/command the agent decides to execute

Hard constraints:
- highlighted_text MUST be an exact substring of the raw step field text
- Do not use ellipses
- source_field must be one of: evaluation|memory|thinking_process|next_goal|action

Output ONLY one JSON object:
{{
  "highlighted_evidence": [
    {{
      "step_index": 0,
      "source_field": "thinking_process",
      "highlighted_text": "exact text",
      "reasoning": "..."
    }}
  ]
}}
""",
        )

    # ------------------------------------------------------------------
    # LLM 4 — Phase Step Verdict Synthesis
    # Input:  criterion_name, criterion_assertion, criterion_intent,
    #         phase_id, phase_summary,
    #         verified_evidence_json, phase_steps_context
    # Output: step_assessments [{step_index, verdict, reasoning, confidence_score}]
    # ------------------------------------------------------------------
    @staticmethod
    def get_phase_step_verdict_synthesis_prompt() -> PromptTemplate:
        return PromptTemplate(
            input_variables=[
                "criterion_name",
                "criterion_assertion",
                "criterion_intent",
                "phase_id",
                "phase_summary",
                "verified_evidence_json",
                "phase_steps_context",
            ],
            template="""You are an expert evaluator synthesizing step-level judgments for an AI agent.

Criterion Name: {criterion_name}
Criterion Assertion: {criterion_assertion}
Criterion Intent: {criterion_intent}
Phase: {phase_id}
Phase Summary: {phase_summary}

Verified evidence for this phase (exact substrings confirmed present in raw step fields):
{verified_evidence_json}

Phase Steps (raw context for cross-reference):
{phase_steps_context}

Your job:
1) For EACH step_index that appears in verified_evidence_json, generate one step-level verdict and concise reasoning.
2) Base the verdict on BOTH the local evidence and the phase-level behavior context (phase_summary and criterion_intent).
3) Do not copy a single evidence item's reasoning verbatim as the full step reasoning; synthesize across items when multiple exist.
4) Reconcile conflicts: if evidence for a step is mixed or contradictory, prefer partial.
5) Do not invent new step indices; only output steps present in verified_evidence_json.
6) Weigh explicit failures, ignored constraints, and harmful tradeoffs heavily against positive self-reported snippets.

Verdict space: pass | fail | partial | unknown

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

    # ------------------------------------------------------------------
    # LLM 5 — Overall Assessment (criterion-level PASS/FAIL)
    # Input:  task_name, criterion_name, criterion_assertion,
    #         personas, criterion_intent,
    #         phase_evaluations_summary, aggregated_evidence_json
    # Output: verdict, reasoning, confidence_score,
    #         supporting_evidence, aggregation_summary
    # ------------------------------------------------------------------
    @staticmethod
    def get_phase_overall_synthesis_prompt() -> PromptTemplate:
        return PromptTemplate(
            input_variables=[
                "task_name",
                "criterion_name",
                "criterion_assertion",
                "personas",
                "criterion_intent",
                "phase_evaluations_summary",
                "aggregated_evidence_json",
            ],
            template="""You are an expert evaluator producing a final criterion-level judgment.

Task: {task_name}
Criterion Name: {criterion_name}
Criterion Assertion: {criterion_assertion}
Personas/Values: {personas}

Criterion Intent: {criterion_intent}

Phase-by-phase evaluation results (each entry contains phase_summary and step_assessments):
{phase_evaluations_summary}

Aggregated verified evidence (selected high-signal snippets across all phases):
{aggregated_evidence_json}

Your job:
1) Integrate all phase-level step verdicts and evidence into one criterion-level verdict.
2) Preserve nuance across phases (e.g., strong positives with critical failures elsewhere).
3) Prefer strict evidence-weighted synthesis over averaging by count.
4) Decide based on this specific criterion, not overall agent performance quality.
5) Final verdict MUST be binary: PASS or FAIL.
6) If mixed/partial/insufficient signals exist, resolve conservatively to FAIL and explain why.
7) Do not promote unverified self-reports to facts; require cross-step behavioral support for positive conclusions.
8) Separate external-environment constraints from agent strategy quality; external delays/failures alone should not cause FAIL unless the agent's response strategy is inadequate.

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

