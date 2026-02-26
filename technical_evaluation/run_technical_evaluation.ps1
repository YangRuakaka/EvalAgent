param(
    [string]$Pattern = "*.txt",
    [switch]$FailFast
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runner = Join-Path $ScriptDir "run_batch_evaluation.py"

if (-not (Test-Path $Runner)) {
    Write-Error "Cannot find script to run: $Runner"
    exit 1
}

$argsList = @(
    $Runner,
    "--dataset-dir", (Join-Path $ScriptDir "dataset"),
    "--results-dir", (Join-Path $ScriptDir "results"),
    "--pattern", $Pattern
)

if ($FailFast) {
    $argsList += "--fail-fast"
}

python @argsList
exit $LASTEXITCODE
