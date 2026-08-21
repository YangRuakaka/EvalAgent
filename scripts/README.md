# Standalone scripts

Run commands from the repository root unless stated otherwise.

## `webharbor/`

- `browseruse_compat.py` is the Browser Use 0.13.6 compatibility and artifact
  adapter. It loads the project API configuration, builds the agent, saves
  screenshots, and writes the legacy-compatible JSON shape consumed by the
  evaluation pipeline. Direct smoke runs go to `browser_agent_runs_scratch/`
  so they cannot be mistaken for canonical pilot cases.
- `run_webharbor_v13_pilot.py` defines the v1.3 pilot case catalog and personas,
  resets each WebHarbor site, executes selected cases, and maintains
  `pilot_status.json`.
- `run_webharbor_v13_pilot_background.ps1` starts the pilot in a hidden
  background process and records PID/stdout/stderr under the canonical run
  directory.

Examples:

```powershell
.\.venv-browseruse-0136\Scripts\python.exe scripts\webharbor\run_webharbor_v13_pilot.py --help
.\scripts\webharbor\run_webharbor_v13_pilot_background.ps1
```

## `experiments/`

- `run_persona_model_experiment.py` is the retained standalone
  persona-by-model browser experiment runner. The former `_old` copy was a
  superseded implementation with the same purpose and was removed.

## `data/`

- `split_dataset_groups.py` rebuilds
  `technical_evaluation/dataset/dataset_grouped_by_task` into two-file task
  groups. For odd-sized groups it duplicates one item with a `__dup` suffix.
  This is a mutating dataset maintenance tool, so review the target before use.

## `analysis/`

- `calculate_user_study_stats.py` reads
  `user_study_analysis/output/combined_cleaned_data.csv` and prints paired
  descriptive statistics, approximate confidence intervals, effect size, and
  a simple signed-rank summary for NASA-TLX-related metrics.

## `dev/`

- `check_gpt5_key.py` is a small network smoke test that loads
  `backend/.env` and checks whether the configured OpenAI key can call GPT-5.

## Removed clutter

- `get_p_values.py`: incomplete stub whose only function body was `pass`.
- `run_persona_model_experiment_old.py`: superseded duplicate of the retained
  runner.
