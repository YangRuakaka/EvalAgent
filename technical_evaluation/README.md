# Technical Evaluation Batch Run Instructions

## Objective
- Put evaluation inputs in `dataset/` (as `.txt` files)
- Batch run the Agentic Judge evaluation logic in backend
- Automatically write results to `results/`

## One-Click Run (PowerShell)
Run in the root directory of the repository:

```powershell
powershell -ExecutionPolicy Bypass -File .\technical_evaluation\run_technical_evaluation.ps1
```

Optional parameters:

```powershell
powershell -ExecutionPolicy Bypass -File .\technical_evaluation\run_technical_evaluation.ps1 -Pattern "*.txt" -FailFast
```

Run with explicit evaluation modes (for baseline comparison):

```powershell
powershell -ExecutionPolicy Bypass -File .\technical_evaluation\run_technical_evaluation.ps1 -Modes agentic,step_level,global_summary
```

- `agentic`: original adaptive granularity (criterion-by-criterion auto analysis)
- `step_level`: force all criteria to step-level evaluation baseline
- `global_summary`: force all criteria to global-summary evaluation baseline

Results are written to separate subfolders:
- `results/agentic/`
- `results/step_level/`
- `results/global_summary/`

## Run Directly with Python
```powershell
python .\technical_evaluation\run_batch_evaluation.py --dataset-dir .\technical_evaluation\dataset --results-dir .\technical_evaluation\results
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
- Each request corresponds to a result file: `results/<txt_filename>__reqXX__result.json`
- Each batch run will generate a summary: `results/batch_summary_<timestamp>.json`

## Notes
- `conditionID` will be mapped to `backend/history_logs/<conditionID>.json`.
- If there is no recognizable request in the txt file, the summary will record the error reason to help you structure the data later.
