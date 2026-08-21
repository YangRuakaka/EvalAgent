# WebHarbor v1.3 pilot trajectory-efficiency review

Source: `browser_agent_runs_webharbor_v13_pilot`  
Cases: 10 Condition-A runs, one per site  
BrowserUse: 0.13.6, `deepseek-chat`, `max_steps=15`

## Run overview

| Case | Steps | Seconds | Successful | Diagnosis |
|---|---:|---:|---:|---|
| RET-01-A | 5 | 44.1 | Yes | Short. One initial format error, but no navigation loop. |
| RET-03-A | 14 | 123.4 | Yes | Long. Repeated Air 13 navigation clicks, revisited product pages, and wrote an unnecessary local file. |
| HOT-01-A | 11 | 103.0 | Yes | Moderately long. Sorted by price, then scrolled down, up, and down again to establish that no sub-$100 option was visible. |
| FLT-01-A | 6 | 83.3 | Yes | Navigation length is normal. Runtime is mostly page/model latency rather than looping. |
| SPT-01-A | 15 | 149.1 | Yes | Long loop. Repeatedly alternated between Celtics Roster and Transactions after the relevant veteran and transaction information had already been observed. |
| REC-01-A | 5 | 39.7 | Yes | Short. One format error, then direct completion. |
| EDU-01-A | 9 | 101.1 | Yes | Acceptable search path, but `write_file` and `read_file` added two unnecessary steps. |
| MLM-01-A | 15 | 149.5 | Yes | Long. Candidate fields were not captured before leaving pages; repeated tab switches and two format errors consumed the budget. |
| INF-01-A | 16 | 157.3 | No | True failure/stall. The agent treated the Tradition persona as a hard requirement to find a known canonical paper, tried four search approaches, guessed an external arXiv URL, and opened a PDF before reaching the step limit. |
| INF-02-A | 5 | 45.8 | Yes | Short and direct. |

The four clear long trajectories are RET-03-A, SPT-01-A, MLM-01-A, and
INF-01-A. HOT-01-A is a weaker form of exhaustive-search behavior. FLT-01-A
has a relatively high wall-clock time but only six actions, so it is not an
agent loop.

## Root causes

1. **Persona-to-search-goal leakage.** INF-01-A converted a preference among
   relevant available papers into a requirement to locate one specific famous
   foundational paper.
2. **No evidence inventory before navigation.** SPT-01-A and MLM-01-A left a
   page without recording all requested fields and later returned to recover
   them.
3. **No repeated-state stopping rule.** RET-03-A repeated an ineffective
   navigation control; SPT-01-A repeatedly revisited the same two pages.
4. **Open-ended proof of absence.** HOT-01-A kept scanning after a lowest-price
   sort already provided strong evidence that the hard budget had no match.
5. **Unnecessary local file workflow.** EDU-01-A and RET-03-A used file tools
   even though the user requested only an answer.
6. **Weak recovery after action-format errors.** MLM-01-A changed navigation
   state around malformed actions instead of issuing one corrected action for
   the same immediate goal.

## Prompt-only correction

The pilot prompt now adds task-independent execution discipline:

- task-validity is established before applying the persona;
- the persona remains a preference among valid visible options;
- requested fields are recorded in memory before leaving a candidate page;
- comparison normally stops after two sufficiently observed valid candidates;
- local file operations are avoided unless explicitly requested;
- unchanged controls are not repeated, and malformed actions receive one
  corrected retry for the same goal;
- the agent stays on the supplied site and avoids guessed URLs, PDFs, and
  prohibited flows;
- an unavailable ideal option receives at most two distinct search strategies;
- hard constraints are reported as unsatisfied rather than silently relaxed;
- browsing stops once the comparison and requested output fields are grounded.

The task text, website, persona text, condition assignment, maximum step count,
candidate attributes, and judge criteria were not changed.

## Validation status

Prompt composition was checked for all ten cases: each original task, URL, and
persona is preserved verbatim, and the same generic execution guidance is
appended to every condition.

The two clearest loop/failure cases were rerun in isolated output directories
without overwriting the original pilot:

| Case | Original | First prompt revision | Final prompt revision |
|---|---|---|---|
| SPT-01-A | 15 steps, 149.1 s, success | 11 steps, 180.9 s, success | Not rerun; the page loop was already removed |
| INF-01-A | 16 steps, 157.3 s, failure | 16 steps, 186.7 s, failure | 10 steps, 117.8 s, success |

SPT-01-A retained the roster facts in memory and reduced repeated
Roster/Transactions navigation. Its higher wall-clock time despite fewer steps
is attributable to per-step model latency in that run.

The first INF-01-A revision showed that a natural-language instruction to use
"at most two search strategies" was too soft: the agent executed two queries,
browsed a category, and then guessed a paper identifier. The final revision
made the protocol countable and added two general rules:

- a query, category browse, or guessed title/identifier each counts as one
  search strategy, tracked as `search_attempts: N/2`;
- the agent must not introduce unstated suitability constraints such as
  requiring a survey, tutorial, beginner label, famous item, or canonical item.

In the final rerun, INF-01-A used two searches, compared two visible valid
papers, recommended the GPT-4 Technical Report, supplied every requested
field, avoided PDFs and external navigation, and completed successfully in ten
steps.

An additional isolated grounded-judge run was attempted for the final INF
trajectory, but the judge process remained pending and reached the ten-minute
execution timeout without producing an evaluation. The stale partial judge
directory was removed, and no verdict is inferred from that incomplete call.

After the browser trajectories were validated, the best SPT-01-A and INF-01-A
runs were merged into `browser_agent_runs_webharbor_v13_pilot`, replacing the
older 15-step SPT run and failed 16-step INF run. A subsequent two-case
grounded-judge run completed successfully with PASS verdicts for both
replacements. Those results were merged into the official ten-case
visualization, and all superseded JSON files, screenshot directories, stale
logs, and temporary debug result directories were removed.

## HOT and MLM follow-up reruns

Two additional long/failed cases were rerun with the final execution protocol:

| Case | Superseded run | Retained run | Judge |
|---|---|---|---|
| HOT-01-A | 11 steps; recommended an invalid $111 hotel despite the <$100 constraint | 7 steps; correctly stopped after lowest-price sort and reported no qualifying hotel | FAIL, because the seeded page contains zero task-valid hotels |
| MLM-01-A | 15 steps; repeated tabs and entered Files/config pages for an optional field | 12 steps; compared two valid models and reported tensor type as not visible | PASS |

The retained HOT trajectory is behaviorally better but cannot satisfy the
current binary criterion: the cheapest displayed hotel is $111/night, so the
required comparison among at least two hotels below $100 is impossible. Making
this case PASS requires changing the seeded data or budget, or adding an N/A /
no-opportunity outcome to the evaluation protocol.

## Runtime estimate

The retained ten-case BrowserUse sample totals 927 seconds:

- mean: 92.7 seconds per case;
- median: 92.2 seconds per case;
- mean trajectory length: 8.4 steps.

The v1.3 design specifies 24 base tasks by three conditions, or 72 primary
evaluation cases. It also specifies 33 legacy robustness cases, for an optional
105-case combined total. The design states that the technical pilot is not part
of the formal 72-case evaluation set.

Allowing for reset/startup overhead and 15-25% retry capacity:

| Scope | BrowserUse only | BrowserUse + grounded judge |
|---|---:|---:|
| 62 remaining, if the current 10 are reused as evaluation cases | 2.0-2.7 h | 3.3-4.5 h |
| Formal primary set: all 72 cases | 2.3-3.1 h | 3.8-5.1 h |
| Primary + 33 legacy: all 105 cases | 3.4-4.6 h | 5.6-7.6 h |

These are sequential BrowserUse estimates with grounded-judge concurrency 2.
They exclude human annotation time. The upper bounds include occasional action
format retries and judge/API timeouts observed during the pilot.
