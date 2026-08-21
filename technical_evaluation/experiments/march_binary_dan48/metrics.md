# March binary Judge × Dan-48 GPT-5 metrics

- Source commit: `2881b03bc19ac4ee6c53c08ec94930348ab59465`
- Sample: all 48 completed Dan Criteria1 annotations
- Dan evidence denominator: 433 items
- Label policy: prompts forbid PARTIAL; any leaked/legacy PARTIAL is normalized to PASS.
- Step alignment: strict one-to-one model step_index → raw steps[index].step_id → human step_id; same normalized field required.

| System | Cases | Binary overall labels | Grounding | Hit rate | Overlap rate | PARTIAL labels |
|---|---:|---:|---:|---:|---:|---:|
| agentic_gpt5 | 48/48 | 48/48 | 98.13% (367/374) | 34.41% (149/433) | 66.58% (249/374) | 0 |
| baseline_gpt5 | 48/48 | 46/48 | 73.15% (109/149) | 12.93% (56/433) | 40.27% (60/149) | 0 |

## Non-binary overall outputs

The pilot Baseline prompt explicitly allows `unknown`; these outputs are retained rather than selectively rerun.

- `baseline_gpt5` / `HOT-01-B`: `unknown`
- `baseline_gpt5` / `INF-01-C`: `unknown`
