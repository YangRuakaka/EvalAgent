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
    [int]$RequestMaxConcurrency = 1,
    [switch]$SkipExisting,
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

foreach ($mode in $Modes) {
    $resultsDir = Join-Path $resultsRoot $mode
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

    if ($JudgeModels.Count -gt 0) {
        $argsList += "--judge-models"
        $argsList += $JudgeModels
    }

    Write-Host "[RUN] mode=$mode input_mode=$InputMode pattern=$Pattern json_pattern=$JsonPattern max_files=$MaxFiles request_max_concurrency=$RequestMaxConcurrency skip_existing=$SkipExisting"
    & $pythonCmd @argsList
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

exit 0
