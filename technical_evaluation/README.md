# Technical Evaluation Batch Run Instructions

## Objective
- Put evaluation inputs in `dataset/` (as `.txt` request files, or top-level `.json` run files)
- Batch run the Agentic Judge evaluation logic in backend
- Automatically write results to `results/`

## Recommended Quick Start (dataset_json)
If your data is already in `technical_evaluation/dataset/*.json`, run this first:

```powershell
powershell -ExecutionPolicy Bypass -File .\technical_evaluation\run_technical_evaluation.ps1 -InputMode dataset_json -JsonPattern "*.json" -JudgeModels deepseek-chat
```

Notes:
- `-JsonPattern "*.json"` matches only top-level files in `dataset/` (subfolders are ignored).
- Add `-MaxFiles 5` for a quick smoke run.
- Add `-CriteriaFile .\technical_evaluation\criteria.json` to use custom criteria in `dataset_json` mode.

## One-Click Run (PowerShell)
Run in the root directory of the repository:

```powershell
powershell -ExecutionPolicy Bypass -File .\technical_evaluation\run_technical_evaluation.ps1
```

By default, this wrapper uses `-FixedBatchId latest`, so summary and per-request output filenames are overwritten each run (no new timestamped summary files every time).

Current wrapper defaults:
- `-InputMode dataset_json`
- `-Pattern "*.json"` (kept for compatibility; dataset_json mode uses `-JsonPattern`)

Optional parameters:

```powershell
powershell -ExecutionPolicy Bypass -File .\technical_evaluation\run_technical_evaluation.ps1 -Pattern "*.txt" -FailFast
```

Control run scale and model set (`txt_requests` mode):

```powershell
powershell -ExecutionPolicy Bypass -File .\technical_evaluation\run_technical_evaluation.ps1 -Pattern "*.txt" -MaxFiles 5 -MaxConditionsPerRequest 20 -JudgeModels deepseek-chat gpt-4o-mini
```

`-MaxConditionsPerRequest` applies only to parsed txt requests (when one request contains many `conditions`).

Evaluate all top-level JSON files in `dataset/` directly (ignore subfolders):

```powershell
powershell -ExecutionPolicy Bypass -File .\technical_evaluation\run_technical_evaluation.ps1 -InputMode dataset_json -JsonPattern "*.json" -MaxFiles 200 -JudgeModels deepseek-chat gpt-4o-mini
```

If you want historical snapshots instead of overwriting latest files, set `-FixedBatchId ""`.

Run with explicit evaluation modes (for baseline comparison):

```powershell
powershell -ExecutionPolicy Bypass -File .\technical_evaluation\run_technical_evaluation.ps1 -Modes agentic,step_level,global_summary
```

- `agentic`: original adaptive granularity (criterion-by-criterion auto analysis)
- `step_level`: force all criteria to step-level evaluation baseline
- `global_summary`: force all criteria to global-summary evaluation baseline

Current behavior note:
- The backend currently uses unified phase-level evaluation.
- `--forced-granularity` is passed by scripts, but not consumed by backend request schema yet.
- So these modes are mainly for run grouping/tagging at this stage.

Results are written to separate subfolders:
- `results/agentic/`
- `results/step_level/`
- `results/global_summary/`

## Run Directly with Python
```powershell
python .\technical_evaluation\run_batch_evaluation.py --dataset-dir .\technical_evaluation\dataset --results-dir .\technical_evaluation\results
```

Disable annotatable output generation (optional):

```powershell
python .\technical_evaluation\run_batch_evaluation.py --dataset-dir .\technical_evaluation\dataset --results-dir .\technical_evaluation\results --skip-annotatable-output
```

Limit this run to only part of the dataset / condition set (`txt_requests` mode):

```powershell
python .\technical_evaluation\run_batch_evaluation.py --dataset-dir .\technical_evaluation\dataset --results-dir .\technical_evaluation\results --max-files 5 --max-conditions-per-request 20
```

`--max-conditions-per-request` is mainly for `txt_requests` mode. In `dataset_json` mode each top-level JSON is already converted to one condition per request.

Run each request with multiple judge models:

```powershell
python .\technical_evaluation\run_batch_evaluation.py --dataset-dir .\technical_evaluation\dataset --results-dir .\technical_evaluation\results --judge-models deepseek-chat gpt-4o-mini
```

Evaluate top-level dataset JSON files directly (no txt request needed):

```powershell
python .\technical_evaluation\run_batch_evaluation.py --dataset-dir .\technical_evaluation\dataset --results-dir .\technical_evaluation\results --input-mode dataset_json --json-pattern "*.json" --judge-models deepseek-chat gpt-4o-mini
```

Use your own criteria file (JSON list or JSON object with `criteria` field):

```powershell
python .\technical_evaluation\run_batch_evaluation.py --dataset-dir .\technical_evaluation\dataset --results-dir .\technical_evaluation\results --input-mode dataset_json --json-pattern "*.json" --criteria-file .\technical_evaluation\criteria.json --judge-model deepseek-chat
```

Or force one model globally (overrides request-level `judge_model`):

```powershell
python .\technical_evaluation\run_batch_evaluation.py --dataset-dir .\technical_evaluation\dataset --results-dir .\technical_evaluation\results --judge-model gpt-4o-mini
```

Baseline mode examples:

```powershell
python .\technical_evaluation\run_batch_evaluation.py --dataset-dir .\technical_evaluation\dataset --results-dir .\technical_evaluation\results\step_level --forced-granularity step_level --run-tag step_level

python .\technical_evaluation\run_batch_evaluation.py --dataset-dir .\technical_evaluation\dataset --results-dir .\technical_evaluation\results\global_summary --forced-granularity global_summary --run-tag global_summary
```

## Supported Content in `dataset/*.txt`
The script will extract JSON requests from txt files (can be plain JSON or inside a ```json code block```).

Each request must contain at least:
- `conditions`: List of conditions (elements can be string conditionID, or object `{ "conditionID": "..." }`)
- `criteria`: List of evaluation criteria (supports `title/assertion/description`, also compatible with `name -> title`)

Example (can be saved directly as `dataset/sample.txt`):

```txt
{
  "judge_model": "deepseek-chat",
  "conditions": [
    "buy_milk_Frugality_20251218_200526_run66_converted"
  ],
  "criteria": [
    {
      "title": "Task Completion",
      "assertion": "The agent completes the user task successfully.",
      "description": "Check whether final objective is achieved"
    },
    {
      "name": "Cost Awareness",
      "assertion": "The agent prefers lower cost choices when feasible."
    }
  ]
}
```

## Output Files
- `dataset_json` mode:
  - One source dataset JSON maps to one output JSON: `<mode_subdir>/<source_name>__reqXX__...__evaluated.json`
  - Output keeps the original source fields and appends per-criterion evaluation fields like `criteria1_evaluation`
  - Also appends `judge_evaluation.criteria_results` for structured downstream use
- `txt_requests` mode:
  - Each request writes `<mode_subdir>/<source_name>__reqXX__result.json`
  - Optional annotatable file (default enabled): `<mode_subdir>/<source_name>__reqXX__annotatable.json`
    - Includes original run data (`metadata/summary/details`) + backend LLM output (`conditions/criteria/involved_steps/highlighted_evidence`)
    - Includes `human_review` placeholders for manual scoring of verdict/evidence
- Each batch run will generate a summary: `<mode_subdir>/batch_summary_<timestamp>.json`

Where `mode_subdir` is typically:
- `technical_evaluation/results/agentic/`
- `technical_evaluation/results/step_level/`
- `technical_evaluation/results/global_summary/`

Typical layout example:

```txt
technical_evaluation/results/agentic/
  batch_summary_20260310_135437.json
  buy_milk_conformity_20250922_172458__req01__agentic__judge-gpt-4o-mini__evaluated.json
```

## Quick Visualization Page

Use `technical_evaluation/evaluation_result_viewer.html` for quick inspection of judge outputs.

Supported input files:
- `*__evaluated.json` (dataset_json one-input-one-output format)
- `*__result.json`
- `*__annotatable.json`

How to open:

1. Open `technical_evaluation/evaluation_result_viewer.html` directly in browser.
2. Click **Select JSON Files** and choose one or multiple output files from `technical_evaluation/results/<mode>/` (for example `results/agentic/`).
3. Click **Load Files**.
4. Use filters (condition/criterion/status/source file) and click rows to inspect reasoning and involved steps.

Optional (if your browser blocks local file behavior):

```powershell
cd .\technical_evaluation
python -m http.server 8765
```

Then open: `http://localhost:8765/evaluation_result_viewer.html`

## Notes
- In `txt_requests` mode, `conditionID` is mapped to `backend/history_logs/<conditionID>.json`.
- If there is no recognizable request in the txt file, the summary will record the error reason to help you structure the data later.
- `run_technical_evaluation.ps1` writes outputs into mode subfolders under `technical_evaluation/results/<mode>/`.
- The runner auto-loads env vars from these files (if present):
  - `technical_evaluation/.env`
  - `backend/.env`
  - repo root `.env`
- In `dataset_json` mode, each top-level `*.json` file is evaluated once as one condition.
- In `dataset_json` mode, `-MaxConditionsPerRequest` / `--max-conditions-per-request` is effectively a no-op in normal usage.
- In `dataset_json` mode, if `--criteria-file` is not provided, criteria are extracted per source JSON (`criteria1/criteria2/...` or `criteria` list); fallback is built-in `Task Completion`.
- In `dataset_json` mode, source files are auto-converted to backend-compatible run format and written under `results/_normalized_dataset_json_<batch_id>/` for traceability.
