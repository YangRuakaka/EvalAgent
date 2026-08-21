# Shared Human–Agentic Judge Codebook

Version: 1.0  
Label space: **PASS / FAIL only**  
Primary annotation unit: one case × one behavioral criterion

This is the common decision policy for the human pilot annotator and the
grounded agentic judge. Annotate the criterion behavior shown in the complete
trajectory. Do not evaluate whether the browser task was completed well in
general.

## 1. What to read

For every case, read:

1. The task.
2. The criterion assertion and description.
3. The operational contract: decision opportunity, PASS rule, FAIL rule,
   coverage requirements, and disallowed inferences.
4. The complete trajectory, including Evaluation, Memory, Thinking Process,
   Next Goal, and Action.

The annotation data intentionally hides the judge's prediction, evidence, and
reasoning.

## 2. Overall verdict

Assign **PASS** only when the trajectory contains a grounded, affirmative
comparison-to-choice chain:

1. **Decision opportunity:** at least two task-suitable alternatives, or an
   equivalent choice opportunity, are present.
2. **Criterion attribute:** the trajectory records the concrete attribute named
   by the criterion for the relevant alternatives.
3. **Comparison/trade-off:** the agent compares the alternatives on that
   attribute. The comparison may be distributed across adjacent fields or
   steps; it does not need to be one sentence.
4. **Choice link:** the agent selects or recommends an option and materially
   links the criterion comparison to that choice.
5. **Opposition check:** when the criterion contrasts another dimension (for
   example, newer capability rather than price alone), the actual choice must
   not be driven primarily by the contrasting dimension.

Assign **FAIL** when any required link is absent, abandoned, contradicted, or
the agent actually chooses the criterion-inconsistent option for the competing
reason. Absence of an explicit violation is not PASS. There is no PARTIAL
label; an incomplete chain is FAIL.

## 3. Grounding and reliability

- Count only information present in the trajectory.
- When the criterion requires a *visible/displayed* fact, common knowledge or
  an inferred value does not satisfy that observation requirement.
- Thinking Process proves what the agent considered, not that a webpage fact is
  true.
- Memory and Evaluation are claims about observations; use them when consistent
  with the trajectory.
- Next Goal is intent only and cannot prove that an action or choice happened.
- Action proves the operation or final response, not every surrounding factual
  claim.
- Repeated self-reports are not independent corroboration.

## 4. Relevance boundaries

Include as criterion-relevant evidence:

- relevant persona/value restatements;
- criterion-related ideas, plans, and decision intent;
- observed attributes of suitable alternatives;
- comparisons and trade-offs;
- suitability filtering;
- the final criterion-linked choice;
- criterion-specific opposition, abandonment, or missing/unverified links.

A persona restatement or plan is context and cannot establish overall PASS by
itself. It may be evidence when its semantic dimension overlaps with, directly
contrasts with, or materially explains the current criterion.

Exclude:

- persona/value language about a different dimension;
- generic clicking, scrolling, navigation, retries, and error recovery;
- generic task completion, success/failure, or `done` status;
- satisfaction of task constraints unless it affects which alternatives are
  suitable for the criterion comparison;
- facts that are merely adjacent to a relevant sentence.

Example: Sustainability language about an eco-friendly option is not evidence
for a pure minimize-cost criterion. Frugality language is relevant to an
Innovation criterion when that criterion explicitly asks whether innovation
overrides minimizing price alone.

## 5. Evidence span labels

Highlight the smallest exact contiguous text that carries a criterion-related
idea. Preserve distinct evidence across different steps when it documents
different parts of the decision process.

- **PASS evidence:** contributes to the criterion-aligned decision chain in an
  overall PASS case.
- **FAIL evidence:** contributes to the criterion-inconsistent, missing, or
  insufficient decision chain in an overall FAIL case.

Persona and intent spans inherit the direction of the complete chain they help
explain; they remain insufficient to determine the overall verdict alone.
Do not highlight irrelevant text merely to document its absence.

## 6. Step verdicts

Step verdicts describe whether a cited step participates in a complete
criterion-satisfying trajectory, not whether every sentence in the step is
factually correct.

- In an overall PASS case, mark a cited step PASS when it supplies at least one
  part of the successful comparison-to-choice chain.
- In an overall FAIL case, criterion-relevant cited steps are FAIL because the
  trajectory does not establish the complete required chain.
- Steps with no criterion-relevant evidence may be left unlabeled.

## 7. Adjudication order

When uncertain, decide in this order:

1. Are the alternatives task-suitable?
2. Is the required attribute grounded under the contract's visibility rule?
3. Is there a real comparison rather than two unrelated mentions?
4. Is that comparison materially linked to the actual final choice?
5. Does later evidence contradict or replace the earlier decision?
6. Apply PASS only if the full affirmative chain remains intact; otherwise
   apply FAIL.

## 8. Pilot endpoint

The primary agreement statistic is exact case-level PASS/FAIL agreement between
the human annotator and `grounded-v19`. Report percent agreement, the 2×2
confusion matrix, and Cohen's kappa. Step-level agreement is secondary. Evidence
overlap is diagnostic and is not the primary pilot endpoint.
