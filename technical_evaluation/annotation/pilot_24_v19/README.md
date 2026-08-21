# 24-case Pilot Annotation

1. Read `CODEBOOK.md` completely before annotating.
2. Open `../annotation_tool.html` in Chrome or Edge.
3. Select this pilot's `raw_data` folder.
4. Keep `criteria1`; label only PASS or FAIL.
5. Label the overall verdict for all 24 cases. Step labels and exact evidence
   spans are secondary but recommended.
6. Export the annotation JSON when complete.
7. Calculate agreement:

```powershell
python technical_evaluation\annotation\calculate_pilot_agreement.py `
  --human-annotations <exported-annotation.json>
```

The raw annotation cases are blinded: they do not contain judge verdicts,
reasoning, evidence, confidence, or step predictions.

## Judge-assisted annotation tool

Open `annotation_tool_with_judge_assist.html` when the annotator should be able
to inspect the Judge's highlighted evidence as an aid. Load:

1. this folder's `raw_data` directory; and
2. `../../results/grounded_judge_webharbor_v13_v19_pilot_24/visualization_data.json`.

The tool highlights Judge evidence in the corresponding trajectory field and
shows its evidence verdict and reasoning. Judge step and overall verdicts stay
hidden until explicitly revealed. Human annotations are stored and exported
separately from Judge annotations.
