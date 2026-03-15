"""
Prompt templates for the 5-step LLM-as-judge evaluation pipeline.

Pipeline (5 LLM calls, in order):
  LLM 1 — get_criteria_interpretation_prompt   : interpret criterion semantics
  LLM 2 — get_phase_segmentation_prompt        : segment trace into behavior phases
  LLM 3 — get_phase_evidence_extraction_prompt : extract evidence per phase with provisional verdicts
  [Program] substring verification             : filter evidence to exact matches
  LLM 4 — get_phase_step_verdict_synthesis_prompt : generate step verdicts per phase
  LLM 5 — get_phase_overall_synthesis_prompt   : produce final criterion-level PASS/FAIL
"""

from langchain_core.prompts import PromptTemplate


class EvaluationPrompts:
    """Container for judge-pipeline prompt templates."""

    # ------------------------------------------------------------------
    # LLM 1 — Criteria Interpretation
    # Input:  task_name, criterion_name, criterion_assertion
    # Output: criterion_intent
    # ------------------------------------------------------------------
    @staticmethod
    def get_criteria_interpretation_prompt() -> PromptTemplate:
        return PromptTemplate(
            input_variables=[
                "task_name",
                "criterion_name",
                "criterion_assertion",
            ],
            template="""You are an expert AI evaluation designer.

Task: {task_name}
Criterion Name: {criterion_name}
Criterion Assertion: {criterion_assertion}

Your job:
  1) Produce one detailed criterion_intent that integrates: the criterion assertion itself and the current task context.
2) Clarify what concrete agent behaviors and decision patterns are in-scope for this criterion under this task setting.
3) Clarify what is out-of-scope to avoid drifting into unrelated quality dimensions.
4) Make criterion_intent actionable for downstream segmentation/evidence/verdict synthesis.
5) Clarify what pass/fail means for this criterion in terms of agent behavior patterns, not just abstract definitions.

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
    # LLM 3 — Phase Evidence Extraction
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

Your job:
1) Extract short-to-medium, exact-substring snippets from the step fields that are directly relevant to this criterion.
2) Cover the behavior storyline: intent setup → action decisions → outcome signals.
3) Prefer decisive moments: tradeoff choices, constraint handling, corrections, successful execution signals, and outcome verification.
4) Include both positive and negative/uncertain signals when present.
5) Avoid failure-only mining: when credible positive evidence exists in this phase, include it instead of only extracting fail-oriented snippets.
6) Avoid generic or procedural lines that do not distinguish this criterion from others.
7) Keep snippets compact and atomic (roughly 4-320 chars each); no ellipses.
8) If no high-signal evidence exists for a step or field, allow medium-signal contextual snippets that clarify intent-action-outcome transitions.
9) Assign a provisional verdict to each evidence item based only on what the snippet itself supports.
10) If a snippet is ambiguous or weakly informative, prefer partial rather than fail.
11) It is acceptable to include planning or intent snippets (next_goal/thinking_process/memory) as supportive evidence when they are consistent with nearby actions/outcomes.

Epistemic rules:
- All fields are self-reported by the agent; treat as claims/signals, not verified facts.
- next_goal/thinking_process/memory/evaluation are valid supportive signals; they do not prove completion alone, but they should still be used when consistent with action/outcome traces.
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
- verdict must be one of: pass|fail|partial

Verdict semantics:
- pass = the snippet supports behavior that satisfies this criterion
- fail = the snippet supports behavior that does not satisfy this criterion
- partial = the snippet is mixed/ambiguous or only partially supports criterion satisfaction

Output ONLY one JSON object:
{{
  "highlighted_evidence": [
    {{
      "step_index": 0,
      "source_field": "thinking_process",
      "highlighted_text": "exact text",
      "verdict": "pass|fail|partial",
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
3) Treat any per-evidence verdict in verified_evidence_json as a provisional polarity signal, not a binding final answer.
4) Do not copy a single evidence item's reasoning verbatim as the full step reasoning; synthesize across items when multiple exist.
5) Reconcile conflicts: if evidence for a step is mixed or contradictory, prefer partial.
6) Do not invent new step indices; only output steps present in verified_evidence_json.
7) Weigh both positive and negative evidence by severity and grounding quality; do not default to fail when evidence is mixed or low-confidence.
8) Reserve fail for clear criterion-violating behavior or strong contradictory evidence; otherwise use partial for uncertainty.

Verdict space:
- pass = this step's behavior satisfies the criterion
- fail = this step's behavior does not satisfy the criterion
- partial = this step is mixed/uncertain or only partially satisfies the criterion

Output ONLY one JSON object:
{{
  "step_assessments": [
    {{
      "step_index": 0,
      "verdict": "pass|fail|partial",
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
                "phase_evaluations_summary",
                "aggregated_evidence_json",
            ],
            template="""You are an expert evaluator producing a final criterion-level judgment.

Task: {task_name}
Criterion Name: {criterion_name}
Criterion Assertion: {criterion_assertion}

Phase-by-phase context (each entry contains phase summary, step span, evidence distribution, and notes):
{phase_evaluations_summary}

Aggregated verified evidence (selected high-signal snippets across all phases):
{aggregated_evidence_json}


CRITICAL — Evidence primacy rules (these override all job rules below):
A) Your ground truth is the actual evidence content in aggregated_evidence_json. Phase-level summaries/notes are context, not final labels.
B) If any phase-level verdict-like text appears in context, treat it as a non-binding heuristic and re-derive from evidence content.
C) If aggregated_evidence_json items are predominantly pass or partial AND no snippet explicitly demonstrates criterion-violating behavior, output PASS. Predominant pass/partial evidence with no explicit violation is sufficient to justify PASS.
D) A FAIL verdict requires at least one clearly criterion-violating snippet in aggregated_evidence_json. Context-level labels or vague negative tone are NOT sufficient on their own.
E) Evidence with partial polarity should be treated as weak-to-moderate supportive signal unless contradicted by explicit violating snippets.

Your job:
1) Integrate phase context and aggregated evidence into one criterion-level verdict, applying the CRITICAL rules above first and prioritizing evidence content.
2) Preserve nuance across phases (e.g., strong positives with critical failures elsewhere).
3) Prefer balanced evidence-weighted synthesis over averaging by count.
4) Decide based on this specific criterion, not overall agent performance quality.
5) Final verdict MUST be binary: PASS or FAIL.
  - PASS means the observed behavior satisfies this criterion.
  - FAIL means the observed behavior does not satisfy this criterion.
6) If signals are mixed, choose PASS when there is credible criterion-aligned positive evidence and no clear high-severity violation; choose FAIL only when there is an explicit criterion-violating snippet in aggregated_evidence_json demonstrating unambiguous criterion violation.
7) Do not promote unverified self-reports to facts; however, consistent multi-step self-reports that align with concrete actions/outcomes can be treated as supportive (not conclusive) evidence.
8) Separate external-environment constraints from agent strategy quality; external delays/failures alone should not cause FAIL unless the agent's response strategy is inadequate.
9) When uncertainty remains but observed behavior mostly satisfies the criterion with only minor gaps, prefer PASS and state the caveats in reasoning.

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

    # ------------------------------------------------------------------
    # LLM 6 — Multi-Condition Ranking (criterion-level)
    # Input:  task_name, criterion_name, criterion_assertion, criterion_description,
    #         condition_summaries_json
    # Output: ranking, ranking_reasoning, comparison_summary
    # ------------------------------------------------------------------
    @staticmethod
    def get_multi_condition_ranking_prompt() -> PromptTemplate:
        return PromptTemplate(
            input_variables=[
          "task_name",
                "criterion_name",
                "criterion_assertion",
                "criterion_description",
                "condition_summaries_json",
            ],
            template="""You are an expert evaluator ranking multiple agent conditions for one criterion.

  Task: {task_name}

Criterion Name: {criterion_name}
Criterion Assertion: {criterion_assertion}
Criterion Description: {criterion_description}

Condition summaries:
{condition_summaries_json}

Your job:
1) Rank all conditions from best to worst for this criterion.
2) Use ONLY these two dimensions for ranking:
   - overall_assessment (primary: pass > partial > fail > unknown)
   - grounded evidence quality/strength (secondary tie-breaker)
3) Do NOT use confidence_score/confidence as a ranking basis.
4) Keep condition_id exactly as provided; do not invent, rename, or omit IDs.
5) Provide concise rationale per ranked condition and one global ranking_reasoning.

Output ONLY one JSON object:
{{
  "ranking": [
    {{
      "condition_id": "...",
      "reasoning": "..."
    }}
  ],
  "ranking_reasoning": "...",
  "comparison_summary": "..."
}}
""",
        )

