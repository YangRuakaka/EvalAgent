# Technical Evaluation Batch Run Instructions

## Windows / macOS: How to Run `run_technical_evaluation.ps1`

Run from repo root.

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy Bypass -File .\technical_evaluation\run_technical_evaluation.ps1
```

macOS (PowerShell 7 / `pwsh`):

```bash
# If brew is missing, install Homebrew first
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Add brew to current shell (Apple Silicon)
eval "$(/opt/homebrew/bin/brew shellenv)"

# If your Mac is Intel, use this instead:
# eval "$(/usr/local/bin/brew shellenv)"

# Install PowerShell once (current Homebrew formula)
brew install powershell

# Optional fallback only if formula install is unavailable in your environment:
# brew install --cask powershell@preview

# Run .ps1 with pwsh (not bash)
pwsh -File ./technical_evaluation/run_technical_evaluation.ps1
```

macOS alternative (no PowerShell, run Python directly):

```bash
python ./technical_evaluation/run_batch_evaluation.py \
  --dataset-dir ./technical_evaluation/dataset \
  --results-dir ./technical_evaluation/results/agentic \
  --input-mode dataset_json \
  --json-pattern "*.json" \
  --max-files 1 \
  --judge-models gpt-4o-mini \
  --run-tag agentic \
  --fixed-batch-id latest
```

Important:
- Do not run `.ps1` with `bash`; use `powershell` (Windows) or `pwsh` (macOS/Linux).
- Most commands below are shown in Windows style (`.\path`). On macOS, use `./path`.

### Common Parameters (`run_technical_evaluation.ps1`)

- `-InputMode`: `dataset_json` (default) or `txt_requests`
- `-JsonPattern`: file pattern for `dataset_json` mode, default `"*.json"`
- `-Pattern`: file pattern for `txt_requests` mode, default `"*.json"` in script (set to `"*.txt"` for txt requests)
- `-JudgeModels`: one or more judge models, e.g. `-JudgeModels deepseek-chat gpt-4o-mini`; wrapper will run them separately and write to model folders such as `results/Deepseek/` and `results/GPT/`
- `-MaxFiles`: limit number of input files for smoke runs
- `-MaxConditionsPerRequest`: only useful in `txt_requests` mode
- `-CriteriaFile`: custom criteria JSON file
- `-Modes`: output grouping tags (all modes currently run the same unified backend pipeline)
- `-FixedBatchId`: default `latest` (overwrite latest outputs); set `""` for timestamped snapshots
- `-RequestMaxConcurrency`: batch-level request concurrency in runner (default `1`, increase to `2~4` for speed)
- `-SkipExisting`: skip already generated output files for incremental reruns
- `-PythonExe`: optional explicit Python path used by wrapper (recommended on macOS with conda)
- `-FailFast`: stop immediately when one file/request fails

Windows example with parameters:

```powershell
powershell -ExecutionPolicy Bypass -File .\technical_evaluation\run_technical_evaluation.ps1 -InputMode dataset_json -JsonPattern "*.json" -MaxFiles 5 -JudgeModels deepseek-chat gpt-4o-mini -Modes agentic
```

macOS example with parameters:

```bash
pwsh -File ./technical_evaluation/run_technical_evaluation.ps1 -InputMode txt_requests -Pattern "*.txt" -MaxFiles 5 -JudgeModels gpt-4o-mini -FailFast
```

macOS incremental + faster rerun example:

```bash
pwsh -File ./technical_evaluation/run_technical_evaluation.ps1 \
  -InputMode dataset_json \
  -JsonPattern "*.json" \
  -MaxFiles 50 \
  -JudgeModels deepseek-chat \
  -RequestMaxConcurrency 3 \
  -SkipExisting
```

macOS + conda example (force specific Python environment):

```bash
pwsh -File ./technical_evaluation/run_technical_evaluation.ps1 \
  -PythonExe /opt/miniconda3/envs/browseruse/bin/python \
  -MaxFiles 1 \
  -JudgeModels gpt-4o-mini
```

If you see `ModuleNotFoundError` when running through `pwsh`, it usually means wrapper is using a different Python than your active conda env. Use `-PythonExe` to pin the interpreter.

## Objective
- Put evaluation inputs in `dataset/` (as `.txt` request files, or top-level `.json` run files)
- Batch run the Agentic Judge evaluation logic in backend
- Automatically write results to `results/`

## Current Agentic Judge Pipeline (LaTeX)

```latex
\begin{algorithm}[t]
\caption{Context-Aware Agentic Auditing Pipeline (Current Implementation)}
\label{alg:audit_pipeline_current}
\begin{algorithmic}[1]
\Require Set of Agent Traces $\mathcal{T}=\{T_1,\dots,T_n\}$, Set of Criteria $\mathcal{C}$
\Ensure Set of Assessments $\mathcal{A}$, Set of Rankings $\mathcal{R}$

\State $\mathcal{A} \gets \emptyset$, $\mathcal{R} \gets \emptyset$
\State $\mathcal{O} \gets \emptyset$ \Comment{Per-trace global overviews}

\Statex
\Comment{\textbf{Stage 1: Structural Abstraction}}
\For{each trace $T_i \in \mathcal{T}$}
  \State $O_i \gets \textsc{LLM\_BuildGlobalOverview}(T_i)$
  \Comment{Outputs global summary + phase partition + phase summaries}
  \If{$O_i$ invalid or timeout}
    \State $O_i \gets \textsc{FallbackOverview}(T_i)$
  \EndIf
  \State $\mathcal{O} \gets \mathcal{O} \cup \{O_i\}$
\EndFor

\Statex
\Comment{\textbf{Stage 2: Criterion-Conditioned Phase Evaluation}}
\For{each criterion $C_j \in \mathcal{C}$}
  \State $E_{batch} \gets \emptyset$
  \For{each trace $T_i \in \mathcal{T}$}
    \State $I_{ij} \gets \textsc{LLM\_InterpretCriterion}(C_j, O_i)$
    \Comment{Intent, dimensions, pass/fail signals}
    \State $P_{ij} \gets \textsc{LLM\_SelectRelevantPhases}(T_i, O_i, I_{ij})$
    \State $E_{phase} \gets \emptyset$
    \For{each phase $p \in P_{ij}$}
      \State $e_p, v_p \gets \textsc{LLM\_JudgePhase}(p_{steps}, p_{summary}, C_j, I_{ij})$
      \State $E_{phase} \gets E_{phase} \cup \{(e_p, v_p)\}$
    \EndFor
    \State $Assessment_i \gets \textsc{LLM\_SynthesizeAcrossPhases}(E_{phase}, C_j)$
    \If{$Assessment_i$ invalid}
      \State $Assessment_i \gets \textsc{FallbackMerge}(E_{phase})$
    \EndIf
    \State $Assessment_i \gets \textsc{ConfidenceConflictRefine}(Assessment_i)$
    \Comment{Optional second-pass overall assessment}
    \State $E_{batch} \gets E_{batch} \cup \{Assessment_i\}$
    \State $\mathcal{A} \gets \mathcal{A} \cup \{Assessment_i\}$
  \EndFor

  \Statex
  \Comment{\textbf{Stage 3: Comparative Ranking}}
  \If{$|E_{batch}| > 1$}
    \State $Rank_j \gets \textsc{LLM\_Rank}(E_{batch}, C_j)$
    \If{$Rank_j$ invalid}
      \State $Rank_j \gets \textsc{FallbackRank}(E_{batch})$
    \EndIf
    \State $\mathcal{R} \gets \mathcal{R} \cup \{Rank_j\}$
  \EndIf
\EndFor

\State \Return $\mathcal{A}, \mathcal{R}$
\end{algorithmic}
\end{algorithm}
```

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
powershell -ExecutionPolicy Bypass -File .\technical_evaluation\run_technical_evaluation.ps1 -Pattern "*.txt" -MaxFiles 5  -JudgeModels deepseek-chat gpt-4o-mini
```

`-MaxConditionsPerRequest` applies only to parsed txt requests (when one request contains many `conditions`).

Evaluate all top-level JSON files in `dataset/` directly (ignore subfolders):

```powershell
powershell -ExecutionPolicy Bypass -File .\technical_evaluation\run_technical_evaluation.ps1 -InputMode dataset_json -JsonPattern "*.json" -MaxFiles 200 -JudgeModels deepseek-chat gpt-4o-mini
```

If you want historical snapshots instead of overwriting latest files, set `-FixedBatchId ""`.

Run with explicit output mode tags:

```powershell
powershell -ExecutionPolicy Bypass -File .\technical_evaluation\run_technical_evaluation.ps1 -Modes agentic,step_level,global_summary
```

- `agentic`: default output namespace tag
- `step_level`: output namespace tag for comparative bookkeeping
- `global_summary`: output namespace tag for comparative bookkeeping

Current behavior note:
- The backend currently uses unified phase-level evaluation.
- `-Modes` controls output grouping only (directory/tag naming), not backend granularity behavior.

Results are written to separate subfolders:
- Without `-JudgeModels`: `results/agentic/`, `results/step_level/`, `results/global_summary/`
- With `-JudgeModels` and a single mode: `results/Deepseek/`, `results/GPT/`, ...
- With `-JudgeModels` and multiple modes: `results/<Model>/<Mode>/`

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

Speed up batch while keeping evaluation logic unchanged (batch-level parallelism):

```powershell
python .\technical_evaluation\run_batch_evaluation.py --dataset-dir .\technical_evaluation\dataset --results-dir .\technical_evaluation\results --input-mode dataset_json --json-pattern "*.json" --judge-model deepseek-chat --request-max-concurrency 3
```

Incremental rerun (skip files that already have outputs):

```powershell
python .\technical_evaluation\run_batch_evaluation.py --dataset-dir .\technical_evaluation\dataset --results-dir .\technical_evaluation\results --input-mode dataset_json --json-pattern "*.json" --judge-model deepseek-chat --skip-existing
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
python .\technical_evaluation\run_batch_evaluation.py --dataset-dir .\technical_evaluation\dataset --results-dir .\technical_evaluation\results\step_level --run-tag step_level

python .\technical_evaluation\run_batch_evaluation.py --dataset-dir .\technical_evaluation\dataset --results-dir .\technical_evaluation\results\global_summary --run-tag global_summary
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
  - Includes `duration_seconds`, per-request `duration_seconds`, `executed_requests`, and `skipped_requests`

Where `mode_subdir` is typically:
- `technical_evaluation/results/agentic/`
- `technical_evaluation/results/step_level/`
- `technical_evaluation/results/global_summary/`

When `run_technical_evaluation.ps1` is invoked with `-JudgeModels`, the wrapper now splits runs by model before calling Python:
- Single mode example: `technical_evaluation/results/Deepseek/`, `technical_evaluation/results/GPT/`
- Multiple modes example: `technical_evaluation/results/Deepseek/agentic/`, `technical_evaluation/results/GPT/step_level/`

Typical layout example:

```txt
technical_evaluation/results/agentic/
  batch_summary_20260310_135437.json
  buy_milk_conformity_20250922_172458__req01__agentic__judge-gpt-4o-mini__evaluated.json

technical_evaluation/results/GPT/
  batch_summary_latest.json
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
2. Click **Select JSON Files** and choose one or multiple output files from `technical_evaluation/results/<mode>/`, `technical_evaluation/results/<model>/`, or `technical_evaluation/results/<model>/<mode>/` (for example `results/agentic/` or `results/GPT/`).
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
- `run_technical_evaluation.ps1` writes outputs into `technical_evaluation/results/<mode>/` when `-JudgeModels` is omitted, and into model folders such as `technical_evaluation/results/Deepseek/` or `technical_evaluation/results/GPT/` when `-JudgeModels` is provided.
- The runner auto-loads env vars from these files (if present):
  - `technical_evaluation/.env`
  - `backend/.env`
  - repo root `.env`
- In `dataset_json` mode, each top-level `*.json` file is evaluated once as one condition.
- In `dataset_json` mode, `-MaxConditionsPerRequest` / `--max-conditions-per-request` is effectively a no-op in normal usage.
- In `dataset_json` mode, if `--criteria-file` is not provided, criteria are extracted per source JSON (`criteria1/criteria2/...` or `criteria` list); fallback is built-in `Task Completion`.
- In `dataset_json` mode, source files are auto-converted to backend-compatible run format and written under `results/_normalized_dataset_json_<batch_id>/` for traceability.

## Task-Group Ranking (LLM-as-a-Judge + Human Inter-Agreement)

Use `technical_evaluation/task_group_ranking_eval.py` when you want to:
- Group all dataset JSON files by the same task
- Let LLM judge rank all conditions inside each task group using one `criteria2`
- Let human annotators rank the same group
- Compute inter-agreement between LLM ranking and human ranking

### 1) Build task groups

```powershell
python .\technical_evaluation\task_group_ranking_eval.py group --dataset-dir .\technical_evaluation\dataset --output-file .\technical_evaluation\results\task_groups_latest.json
```

Optional: also materialize grouped copies into per-task subfolders.

```powershell
python .\technical_evaluation\task_group_ranking_eval.py group --dataset-dir .\technical_evaluation\dataset --materialize-dir .\technical_evaluation\results\dataset_grouped_by_task
```

### 2) Run LLM ranking within each task group (by criteria2)

`criteria2` is empty in many source files, so pass a unified assertion via `--criteria2-text`.

```powershell
python .\technical_evaluation\task_group_ranking_eval.py llm-rank --dataset-dir .\technical_evaluation\dataset --criteria2-text "Whether the agent's actions and decisions consistently align with the persona's core value." --judge-model deepseek-chat --output-dir .\technical_evaluation\results
```

This generates a timestamped folder:
- `llm_group_ranking.json`: per-group ranking output from judge
- `human_ranking_template.json`: template for human annotation with same item set
- `raw/*.json`: raw judge responses per task group

### 3) Human ranking

Fill `human_ranking_template.json` with either:
- `ranking`: ordered list of file names (best to worst)
- or `items[].human_rank`
- or `items[].human_score`

### 4) Compute inter-agreement

```powershell
python .\technical_evaluation\task_group_ranking_eval.py inter-agreement --llm-ranking-file .\technical_evaluation\results\task_group_ranking_<timestamp>\llm_group_ranking.json --human-ranking-file .\technical_evaluation\results\task_group_ranking_<timestamp>\human_ranking_template_filled.json --output-file .\technical_evaluation\results\task_group_ranking_<timestamp>\inter_agreement.json
```

Reported metrics:
- Group-level Spearman rho
- Group-level Kendall tau-b
- Top-1 agreement rate
- Overall means across comparable groups

### One-command workflow

```powershell
python .\technical_evaluation\task_group_ranking_eval.py full --dataset-dir .\technical_evaluation\dataset --criteria2-text "Whether the agent's actions and decisions consistently align with the persona's core value." --judge-model deepseek-chat --human-ranking-file .\technical_evaluation\results\task_group_ranking_<timestamp>\human_ranking_template_filled.json
```
