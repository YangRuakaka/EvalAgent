# Technical Evaluation Quick Guide

This guide is intentionally minimal and focuses on:
- How to run `run_technical_evaluation.ps1` on Windows/macOS
- How to set key parameters (including the 2 new console logging flags)

## Prerequisites

- Run commands from repository root.
- Use PowerShell for `.ps1`:
  - Windows: `powershell`
  - macOS: `pwsh` (PowerShell 7)
- Do not run `.ps1` with `bash`.

## Windows

Basic run:

```powershell
powershell -ExecutionPolicy Bypass -File .\technical_evaluation\run_technical_evaluation.ps1
```

Typical smoke run:

```powershell
powershell -ExecutionPolicy Bypass -File .\technical_evaluation\run_technical_evaluation.ps1 -InputMode dataset_json -JsonPattern "*.json" -MaxFiles 5 -JudgeModels deepseek-chat
```

## macOS

Install PowerShell once:

```bash
brew install powershell
```

Basic run:

```bash
pwsh -File ./technical_evaluation/run_technical_evaluation.ps1
```

Typical smoke run:

```bash
pwsh -File ./technical_evaluation/run_technical_evaluation.ps1 -InputMode dataset_json -JsonPattern "*.json" -MaxFiles 5 -JudgeModels gpt-4o-mini
```

If you hit `ModuleNotFoundError` in `pwsh`, pin Python explicitly:

```bash
pwsh -File ./technical_evaluation/run_technical_evaluation.ps1 -PythonExe /opt/miniconda3/envs/browseruse/bin/python
```

## Key Parameters

- `-InputMode`
  - `dataset_json` (default): evaluate top-level JSON files in `technical_evaluation/dataset/`
  - `txt_requests`: parse requests from txt files
- `-JsonPattern`: file glob for `dataset_json` mode, default `"*.json"`
- `-Pattern`: file glob for `txt_requests` mode
- `-JudgeModels`: run one or more judge models, e.g. `-JudgeModels deepseek-chat gpt-4o-mini`
- `-MaxFiles`: limit how many input files to run
- `-RequestMaxConcurrency`: request-level concurrency (default `1`, usually try `2~4`)
- `-SkipExisting`: skip requests whose output already exists
- `-FixedBatchId`: default `latest` (overwrite latest outputs); use `""` for timestamp snapshots
- `-PythonExe`: explicit Python executable path
- `-FailFast`: stop immediately after first failure

### New Parameters

- `-ShowStageTimings`
  - Print per-stage timing in console (criterion/phase level timing logs)
- `-ShowLlmIo`
  - Print LLM input/output in console (prompt/chat input and model responses)

## Recommended Command Patterns

Enable stage timing only:

```powershell
powershell -ExecutionPolicy Bypass -File .\technical_evaluation\run_technical_evaluation.ps1 -InputMode dataset_json -MaxFiles 3 -JudgeModels deepseek-chat -ShowStageTimings
```

Enable LLM I/O only:

```powershell
powershell -ExecutionPolicy Bypass -File .\technical_evaluation\run_technical_evaluation.ps1 -InputMode dataset_json -MaxFiles 1 -JudgeModels gpt-4o-mini -ShowLlmIo
```

Enable both (most verbose):

```powershell
powershell -ExecutionPolicy Bypass -File .\technical_evaluation\run_technical_evaluation.ps1 -InputMode dataset_json -MaxFiles 1 -JudgeModels gpt-4o-mini -ShowStageTimings -ShowLlmIo
```

macOS equivalent:

```bash
pwsh -File ./technical_evaluation/run_technical_evaluation.ps1 -InputMode dataset_json -MaxFiles 1 -JudgeModels gpt-4o-mini -ShowStageTimings -ShowLlmIo
```

## Output Location

- Without `-JudgeModels`: `technical_evaluation/results/<mode>/`
- With `-JudgeModels`: model-specific folders such as `technical_evaluation/results/Deepseek/` and `technical_evaluation/results/GPT/`
- Batch summary: `batch_summary_<batch_id>.json`

## Common Mistakes

- In PowerShell wrapper usage, use `-MaxFiles 1` (not `--max-files 1`).
- Do not keep a trailing `\` line-continuation from bash-style commands.
- Always run `.ps1` with `powershell` or `pwsh`, not `bash`.
