# Persona-Model Experiment Runner

This document explains how to use `run_persona_model_experiment.py` to run the browser agent with multiple personas and models on the same tasks.

The script is designed for one main goal:
- Persist artifacts in the **exact same format** as `BrowserAgentService` run outputs (JSON + screenshots).

## What this script guarantees

The script calls `BrowserAgentService.run()` directly instead of re-implementing serialization.
That means JSON and screenshots are produced by the same backend logic used in normal browser-agent runs.

When strict validation is enabled (default), each generated JSON file is verified to have exactly these fields and order:

Top-level fields:
1. `metadata`
2. `summary`
3. `details`

`metadata` fields:
1. `id`
2. `timestamp_utc`
3. `task`
4. `persona`
5. `model`
6. `run_index`

`summary` fields:
1. `is_done`
2. `is_successful`
3. `has_errors`
4. `number_of_steps`
5. `total_duration_seconds`
6. `final_result`

`details` fields:
1. `screenshots`
2. `step_descriptions`
3. `model_outputs`
4. `last_action`
5. `structured_output`

The script also validates that all screenshot paths listed in `details.screenshots` resolve to real files.

## File location

Script file:
- `backend/run_persona_model_experiment.py`

## Before you run

1. Go to the backend folder:
```bash
cd backend
```

2. Make sure dependencies are installed (including `browser-use`, `pillow`, and your LLM SDKs).

3. Make sure your `.env` has valid LLM keys and browser-agent settings.

4. Confirm screenshots are enabled in config:
- `BROWSER_AGENT_ENABLE_SCREENSHOTS=true`

If screenshots are disabled, the script stops with an error because output would no longer match expected run artifacts.

## Configure tasks/personas/models

Open `run_persona_model_experiment.py` and edit this block:

- `TASKS`
- `PERSONAS`
- `MODELS`
- `RUN_TIMES`

You can set website URL in either way:
1. Edit each task's `url` in `TASKS`.
2. Use CLI `--website-url` to override all task URLs for one run.

### Task format
```python
TaskConfig(
    name="Buy milk",
    url="http://localhost:3000/riverbuy",
    description="Buy milk with the persona's decision style.",
)
```

### Persona format
```python
PersonaConfig(
    value="Frugality",
    content="You maximize value for money and avoid unnecessary spending.",
)
```

### Models format
```python
MODELS = [
    "deepseek-chat",
    "gpt-4o-mini",
]
```

`RUN_TIMES` means repetitions per `(task, persona, model)` combination.

Total runs = `len(TASKS) * len(PERSONAS) * len(MODELS) * RUN_TIMES`.

## Run commands

Default (uses `RUN_TIMES` from the file):
```bash
python run_persona_model_experiment.py
```

Override run times from CLI:
```bash
python run_persona_model_experiment.py --run-times 2
```

Override website URL for all tasks in this run:
```bash
python run_persona_model_experiment.py --website-url http://localhost:3000/riverbuy
```

Combine run times + website URL override:
```bash
python run_persona_model_experiment.py --run-times 2 --website-url http://localhost:3000/riverbuy
```

Verbose logs:
```bash
python run_persona_model_experiment.py --verbose
```

Disable strict schema validation (not recommended):
```bash
python run_persona_model_experiment.py --no-strict-schema
```

## Output artifacts

The script prints every generated history JSON file path at the end.

Artifacts are stored in the browser-agent output directory defined by backend settings:
- default: `backend/browser_agent_runs/`

For each run, you will get:
1. One JSON history file (exact browser-agent run format)
2. One screenshot folder under `screenshots/<run_id>/` with the referenced images

## Team usage checklist

1. One teammate edits only the config block in the script.
2. Run the script.
3. Confirm no strict-schema errors.
4. Share generated JSON + screenshot folders for evaluation.

If strict validation fails, do not use those artifacts until the mismatch is fixed.

## Troubleshooting

`No results returned for task ...`
- Check URL availability and browser startup health.

`History file not found ...`
- Check write permissions and `BROWSER_AGENT_RUN_OUTPUT_DIR`.

`Screenshot files missing ...`
- Check screenshot settings and disk cleanup jobs.

`Experiment failed: ... authentication / quota ...`
- Check LLM API keys, quota, and selected model names.
