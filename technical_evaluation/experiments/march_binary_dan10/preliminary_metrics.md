# March binary Judge × Dan-10 preliminary metrics

- Source commit: `2881b03bc19ac4ee6c53c08ec94930348ab59465`
- Sample: 10 cases (5 Dan PASS + 5 Dan FAIL)
- Dan evidence denominator: 89 items
- Label policy: prompts forbid PARTIAL; any leaked/legacy PARTIAL is normalized to PASS.
- Step alignment: strict one-to-one model step_index → raw steps[index].step_id → human step_id; same normalized field required.

| System | Cases | Grounding | Hit rate | Overlap rate | PARTIAL labels |
|---|---:|---:|---:|---:|---:|
| agentic_gpt5 | 10/10 | 100.00% (75/75) | 31.46% (28/89) | 58.67% (44/75) | 0 |
| agentic_deepseek | 1/10 | INCOMPLETE | INCOMPLETE | INCOMPLETE | 0 |
| baseline_gpt5 | 10/10 | 70.97% (22/31) | 16.85% (15/89) | 48.39% (15/31) | 0 |
| baseline_deepseek | 1/10 | INCOMPLETE | INCOMPLETE | INCOMPLETE | 0 |

## Incomplete configurations

DeepSeek Agentic and DeepSeek Baseline stopped after the smoke case because the DeepSeek API returned HTTP 402 `Insufficient Balance`. Their one-case progress is retained, but no 10-case metric is reported.
