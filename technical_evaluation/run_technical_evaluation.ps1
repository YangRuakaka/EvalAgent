param(
    [string]$Pattern = "*.json",
    [ValidateSet("txt_requests", "dataset_json")]
    [string]$InputMode = "dataset_json",
    [string]$JsonPattern = "*.json",
    [string]$CriteriaFile = "",
    [switch]$FailFast,
    [int]$MaxFiles = 0,
    [int]$MaxConditionsPerRequest = 0,
    [string[]]$JudgeModels = @(),
    [string]$FixedBatchId = "latest",
    [int]$RequestMaxConcurrency = 4,
    [switch]$SkipExisting,
    [switch]$ShowStageTimings,
    [switch]$ShowLlmIo,
    [string]$PythonExe = "",
    [ValidateSet("agentic", "step_level", "global_summary")]
    [string[]]$Modes = @("agentic")
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runner = Join-Path $ScriptDir "run_batch_evaluation.py"

if (-not (Test-Path $Runner)) {
    Write-Error "Cannot find script to run: $Runner"
    exit 1
}

$datasetDir = Join-Path $ScriptDir "dataset"
$resultsRoot = Join-Path $ScriptDir "results"

function Get-ModelResultsFolderName {
    param(
        [string]$ModelName
    )

    $normalized = [string]$ModelName
    if ([string]::IsNullOrWhiteSpace($normalized)) {
        return "Model"
    }

    $lower = $normalized.Trim().ToLowerInvariant()
    if ($lower -match "deepseek") {
        return "Deepseek"
    }

    if ($lower -match "(^|[^a-z])gpt([^a-z]|$)" -or $lower -match "openai") {
        return "GPT"
    }

    $sanitized = ($normalized -replace "[^A-Za-z0-9._-]+", "-").Trim("-", ".", "_")
    if ([string]::IsNullOrWhiteSpace($sanitized)) {
        return "Model"
    }

    return $sanitized
}

function Get-ResultsDirForRun {
    param(
        [string]$ResultsRoot,
        [string]$Mode,
        [string]$ModelName,
        [bool]$HasMultipleModes
    )

    if ([string]::IsNullOrWhiteSpace($ModelName)) {
        return (Join-Path $ResultsRoot $Mode)
    }

    $modelDir = Join-Path $ResultsRoot (Get-ModelResultsFolderName -ModelName $ModelName)
    if ($HasMultipleModes) {
        return (Join-Path $modelDir $Mode)
    }

    return $modelDir
}

$pythonCmd = $PythonExe
if ([string]::IsNullOrWhiteSpace($pythonCmd)) {
    $condaPrefix = $env:CONDA_PREFIX
    if (-not [string]::IsNullOrWhiteSpace($condaPrefix)) {
        $condaPythonUnix = Join-Path $condaPrefix "bin/python"
        $condaPythonWin = Join-Path $condaPrefix "python.exe"
        if (Test-Path $condaPythonUnix) {
            $pythonCmd = $condaPythonUnix
        }
        elseif (Test-Path $condaPythonWin) {
            $pythonCmd = $condaPythonWin
        }
    }
}

if ([string]::IsNullOrWhiteSpace($pythonCmd)) {
    $pythonCmd = "python"
}

Write-Host "[INFO] Python executable: $pythonCmd"

$modelsToRun = @("")
if ($JudgeModels.Count -gt 0) {
    $modelsToRun = $JudgeModels
}

$hasMultipleModes = $Modes.Count -gt 1

foreach ($mode in $Modes) {
    foreach ($judgeModel in $modelsToRun) {
        $resultsDir = Get-ResultsDirForRun -ResultsRoot $resultsRoot -Mode $mode -ModelName $judgeModel -HasMultipleModes:$hasMultipleModes
        if (-not (Test-Path $resultsDir)) {
            New-Item -ItemType Directory -Path $resultsDir | Out-Null
        }

        $argsList = @(
            $Runner,
            "--dataset-dir", $datasetDir,
            "--results-dir", $resultsDir,
            "--pattern=$Pattern",
            "--input-mode", $InputMode,
            "--json-pattern=$JsonPattern",
            "--run-tag", $mode
        )

        if ($FixedBatchId -ne "") {
            $argsList += "--fixed-batch-id"
            $argsList += $FixedBatchId
        }

        if ($CriteriaFile -ne "") {
            $argsList += "--criteria-file"
            $argsList += $CriteriaFile
        }

        if ($FailFast) {
            $argsList += "--fail-fast"
        }

        if ($MaxFiles -gt 0) {
            $argsList += "--max-files"
            $argsList += $MaxFiles
        }

        if ($MaxConditionsPerRequest -gt 0) {
            $argsList += "--max-conditions-per-request"
            $argsList += $MaxConditionsPerRequest
        }

        if ($RequestMaxConcurrency -gt 1) {
            $argsList += "--request-max-concurrency"
            $argsList += $RequestMaxConcurrency
        }

        if ($SkipExisting) {
            $argsList += "--skip-existing"
        }

        if ($ShowStageTimings) {
            $argsList += "--show-stage-timings"
        }

        if ($ShowLlmIo) {
            $argsList += "--show-llm-io"
        }

        if (-not [string]::IsNullOrWhiteSpace($judgeModel)) {
            $argsList += "--judge-model"
            $argsList += $judgeModel
        }

        $judgeModelLabel = if ([string]::IsNullOrWhiteSpace($judgeModel)) { "<request/default>" } else { $judgeModel }
        Write-Host "[RUN] mode=$mode judge_model=$judgeModelLabel results_dir=$resultsDir input_mode=$InputMode pattern=$Pattern json_pattern=$JsonPattern max_files=$MaxFiles request_max_concurrency=$RequestMaxConcurrency skip_existing=$SkipExisting show_stage_timings=$ShowStageTimings show_llm_io=$ShowLlmIo"
        & $pythonCmd @argsList
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }
}

exit 0
