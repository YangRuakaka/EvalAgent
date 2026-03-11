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

foreach ($mode in $Modes) {
    $resultsDir = Join-Path $resultsRoot $mode
    if (-not (Test-Path $resultsDir)) {
        New-Item -ItemType Directory -Path $resultsDir | Out-Null
    }

    $argsList = @(
        $Runner,
        "--dataset-dir", $datasetDir,
        "--results-dir", $resultsDir,
        "--pattern", $Pattern,
        "--input-mode", $InputMode,
        "--json-pattern", $JsonPattern,
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

    if ($JudgeModels.Count -gt 0) {
        $argsList += "--judge-models"
        $argsList += $JudgeModels
    }

    if ($mode -eq "step_level" -or $mode -eq "global_summary") {
        $argsList += "--forced-granularity"
        $argsList += $mode
    }

    Write-Host "[RUN] mode=$mode input_mode=$InputMode pattern=$Pattern json_pattern=$JsonPattern max_files=$MaxFiles"
    python @argsList
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

exit 0
