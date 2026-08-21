# March-binary WebHarbor-72 Judge × Dan-48

Primary accuracy uses all 48 Dan cases and counts a final `unknown` as incorrect.

| System | Correct / 48 | Accuracy | Evaluable-only | Grounding | Hit rate | Overlap | Strict step accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|
| agentic_gpt5 | 41/48 | 85.42% | 85.42% (48/48 evaluable) | 98.13% (367/374) | 34.41% (149/433) | 66.58% (249/374) | 47.67% (133/279) |
| baseline_gpt5 | 41/48 | 85.42% | 89.13% (46/48 evaluable) | 73.15% (109/149) | 12.93% (56/433) | 40.27% (60/149) | 25.09% (70/279) |
| agentic_deepseek | 40/48 | 83.33% | 83.33% (48/48 evaluable) | 100.00% (374/374) | 36.26% (157/433) | 63.10% (236/374) | 46.95% (131/279) |
| baseline_deepseek | 41/48 | 85.42% | 87.23% (47/48 evaluable) | 62.59% (87/139) | 9.47% (41/433) | 29.50% (41/139) | 21.15% (59/279) |

## Final-verdict unknown cases

- `agentic_gpt5`: none
- `baseline_gpt5`: HOT-01-B, INF-01-C
- `agentic_deepseek`: none
- `baseline_deepseek`: REC-01-C
