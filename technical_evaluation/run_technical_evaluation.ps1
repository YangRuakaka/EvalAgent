param(
    [string]$Pattern = "*.txt",
    [switch]$FailFast,
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
        "--run-tag", $mode
    )

    if ($FailFast) {
        $argsList += "--fail-fast"
    }

    if ($mode -eq "step_level" -or $mode -eq "global_summary") {
        $argsList += "--forced-granularity"
        $argsList += $mode
    }

    Write-Host "[RUN] mode=$mode pattern=$Pattern"
    python @argsList
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

exit 0
