# Technical evaluation

This directory is organized by responsibility. Datasets and generated results
remain at stable paths; executable Python files live in named subdirectories.
Run commands from the repository root.

## Recommended entry points

### Agentic and baseline judging (`pipelines/`)

- `run_batch_evaluation.py` is the general Agentic Judge batch runner. It reads
  raw TXT requests or top-level dataset JSON files, extracts criteria, calls
  the backend's default grounded-blind evaluator, supports
  concurrent/incremental runs, and writes evaluated cases plus batch summaries
  under `results/`. Its dataset input and evaluated JSON output schemas remain
  compatible with the original EvalAgent batch pipeline.
- `run_baseline_llm_judge.py` runs the one-shot non-agentic baseline on the
  same dataset shape. It preserves the expected evaluation output schema so
  baseline and Agentic Judge results can be compared directly.
- `run_grounded_judge_webharbor.py` is the focused WebHarbor v1.3 pilot runner.
  It joins the canonical Browser Use artifacts with
  `webharbor_v13_judge_cases.json`, runs the grounded judge, and writes
  `experiment_evaluation.json`, `visualization_data.json`, and status metadata.
- `task_group_ranking_eval.py` builds task-group manifests, performs
  criteria-aware or baseline pairwise rankings, and computes LLM/human
  agreement. See `pipelines/task_group_ranking_eval_usage.md`.

The PowerShell wrapper remains at `run_technical_evaluation.ps1` as the main
batch entry point:

```powershell
.\technical_evaluation\run_technical_evaluation.ps1 -InputMode dataset_json
python technical_evaluation\pipelines\run_grounded_judge_webharbor.py --help
```

### Analysis (`analysis/`)

- `compare_criteria1_agreement.py` computes model/model and model/human
  Criterion 1 label agreement, confusion matrices, accuracy/F1/kappa, grounded
  evidence substring accuracy, and step/evidence hit metrics.
- `compare_rank_disagreement.py` compares two or more task-ranking reports,
  calculates pairwise disagreement and group-level Spearman agreement, and can
  score each model against human winners.
- `plot_technical_performance.py` produces publication-style plots for
  grounding accuracy, evidence hit rate, and overlap rate, including
  improvements over baseline.
- `plot_verdict_rank_accuracy.py` plots final-verdict and ranking accuracy from
  the comparison reports.

### Dataset maintenance (`data_tools/`)

- `convert_dataset_txt_to_json.py` parses Browser Use TXT logs into structured
  trajectory JSON, reconstructs step fields, replaces the final `done(...)`
  text with the recorded final result, and separates non-completed runs.
- `redesign_criteria1_by_persona.py` assigns satisfy/not-satisfy Criterion 1
  variants across personas, writes a preview report, and only edits datasets
  when `--apply` is supplied.

### Reporting and validation (`reporting/`)

- `render_grounded_judge_html.py` projects judge citations back onto the
  original trajectory fields and renders the EvalAgent-style highlighted
  evidence UI.
- `verify_grounded_judge_results.py` validates the canonical ten-case grounded
  judge report: schema, case/run IDs, evidence spans, step polarity, screenshot
  references, and required HTML behavior.

Typical report workflow:

```powershell
python technical_evaluation\pipelines\run_grounded_judge_webharbor.py
python technical_evaluation\reporting\render_grounded_judge_html.py
python technical_evaluation\reporting\verify_grounded_judge_results.py
```

## Data and non-Python areas

- `dataset/`: source and grouped evaluation datasets.
- `annotation/`: Label Studio launcher, annotation tasks, and human-label data.
- `results/`: generated judge outputs, comparison reports, figures, and HTML.
- `webharbor_v13_judge_cases.json`: criteria configuration for the canonical
  pilot.
- `pilot_run_efficiency_review.md`: pilot runtime/debug review.

## Removed obsolete one-off scripts

- `update_case_design_v11.py`
- `update_case_design_v12.py`
- `audit_case_design_v12.py`

These scripts only migrated or audited superseded v1.1/v1.2 Word documents,
used hard-coded local paths, and were not referenced by any active pipeline.
The current case-design source is v1.3, so retaining them alongside executable
evaluation code obscured the supported workflow.
