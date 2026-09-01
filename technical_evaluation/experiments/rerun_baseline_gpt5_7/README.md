# Baseline GPT-5 rerun of seven missing/unknown cases

Date: 2026-08-31

This experiment reruns, exactly once, every baseline GPT-5 case that was missing
or had an `unknown` final verdict in the pooled original-33 plus new-72
evaluation. It uses `technical_evaluation/pipelines/run_baseline_llm_judge.py`,
model `gpt-5`, one-shot mode, and `max_chars_per_field=700`.

Repeatedly sampling an unresolved case until it returns a desired binary label
would introduce selection bias. The one remaining API `unknown` was therefore
not sampled again; it was subsequently resolved by a documented human override
based on the visible final action, while the raw API response was preserved.

| Case | Previous | Rerun | Human | Rerun correct? |
|---|---|---|---|---|
| `data_000024` | unknown | pass | pass | yes |
| `data_000029` | unknown | pass | fail | no |
| `data_000066` | missing | pass | pass | yes |
| `data_000091` | unknown | fail | fail | yes |
| `HOT-01-B` | unknown | unknown → **manual fail** | fail | yes |
| `INF-01-C` | unknown | pass | fail | no |
| `RET-03-B` | unknown | pass | fail | no |

All seven API requests completed successfully. Six cases became evaluable from
the rerun. `HOT-01-B` remained `unknown` because the model incorrectly claimed
that the final hotel recommendation was not visible. Step 6 explicitly
recommends LUMA at $250/night over the valid Artezen option at $111/night, so
the case was manually adjudicated as `fail`. The override is recorded in the
active JSON and the untouched API output is stored under `raw_api_outputs/`.

For the old 33-case evidence metrics, the historical baseline outputs were
recovered from commit `e03205c`, the four selected cases were overlaid with the
rerun outputs, and the metric definition from commit `733de8e` was used. This
reproduces the published old baseline GPT-5 counts before applying the overlay.

After pooling with the new 72-case set, baseline GPT-5 has:

- final-verdict accuracy: 82/105 = 78.10%
- evaluable-only accuracy: 82/105 = 78.10%
- Cohen's kappa: 0.575
- grounding: 284/398 = 71.36%
- human-evidence hit rate: 275/967 = 28.44%
- evidence overlap: 197/398 = 49.50%
- strict step accuracy: 199/409 = 48.66%
- five-metric composite: 59.48/100

The cross-model baseline mean becomes 59.01/100. The agentic mean remains
83.97/100, for a 24.96-point advantage.
