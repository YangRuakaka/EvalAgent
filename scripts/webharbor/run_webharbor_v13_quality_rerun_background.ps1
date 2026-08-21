param(
    [string]$Model = "deepseek-chat",
    [int]$MaxSteps = 15,
    [string[]]$CaseIds = @()
)

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$python = Join-Path $repoRoot ".venv-browseruse-0136\Scripts\python.exe"
$supervisor = Join-Path $PSScriptRoot "quality_rerun_webharbor_v13.py"
$outputDir = Join-Path $repoRoot "browser_agent_runs_webharbor_v13_pilot"
$pidPath = Join-Path $outputDir "quality_rerun.pid"
$statusPath = Join-Path $outputDir "quality_rerun_supervisor_status.json"
$stdoutPath = Join-Path $outputDir "quality_rerun.stdout.log"
$stderrPath = Join-Path $outputDir "quality_rerun.stderr.log"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Browser Use Python environment not found: $python"
}

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

if (Test-Path -LiteralPath $pidPath) {
    $existingPid = Get-Content -LiteralPath $pidPath -ErrorAction SilentlyContinue
    if ($existingPid -and (Get-Process -Id $existingPid -ErrorAction SilentlyContinue)) {
        throw "Quality rerun supervisor is already running with PID $existingPid"
    }
}

$caseArguments = ""
foreach ($caseId in $CaseIds) {
    $caseArguments += (' --case "{0}"' -f $caseId)
}
$command = ('"{0}" -u "{1}" --model "{2}" --max-steps {3} --output-dir "{4}" --status-path "{5}"{6} 1>"{7}" 2>"{8}"' -f `
    $python, $supervisor, $Model, $MaxSteps, $outputDir, $statusPath, $caseArguments, $stdoutPath, $stderrPath)

$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = "$env:SystemRoot\System32\cmd.exe"
$startInfo.Arguments = "/d /s /c `"$command`""
$startInfo.WorkingDirectory = $repoRoot
$startInfo.UseShellExecute = $true
$startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
$launcherProcess = [System.Diagnostics.Process]::Start($startInfo)
if (-not $launcherProcess) {
    throw "Failed to start the WebHarbor quality rerun supervisor"
}

$pythonPid = $null
for ($attempt = 0; $attempt -lt 50; $attempt++) {
    if (Test-Path -LiteralPath $statusPath) {
        try {
            $status = Get-Content -Raw -LiteralPath $statusPath | ConvertFrom-Json
            if ($status.state -eq "running" -and $status.pid) {
                $candidate = Get-Process -Id $status.pid -ErrorAction SilentlyContinue
                if ($candidate) {
                    $pythonPid = [int]$status.pid
                    break
                }
            }
        } catch {
            # The supervisor may be replacing the status file while starting.
        }
    }
    Start-Sleep -Milliseconds 200
}
if (-not $pythonPid) {
    $pythonPid = $launcherProcess.Id
}
Set-Content -LiteralPath $pidPath -Value $pythonPid -Encoding ascii

[pscustomobject]@{
    PID = $pythonPid
    Status = $statusPath
    Stdout = $stdoutPath
    Stderr = $stderrPath
}
