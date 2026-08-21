param(
    [string]$Model = "deepseek-chat",
    [int]$MaxSteps = 15
)

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$python = Join-Path $repoRoot ".venv-browseruse-0136\Scripts\python.exe"
$runner = Join-Path $PSScriptRoot "run_webharbor_v13_pilot.py"
$outputDir = Join-Path $repoRoot "browser_agent_runs_webharbor_v13_pilot"
$pidPath = Join-Path $outputDir "pilot.pid"
$stdoutPath = Join-Path $outputDir "pilot.stdout.log"
$stderrPath = Join-Path $outputDir "pilot.stderr.log"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Browser Use Python environment not found: $python"
}

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

if (Test-Path -LiteralPath $pidPath) {
    $existingPid = Get-Content -LiteralPath $pidPath -ErrorAction SilentlyContinue
    if ($existingPid -and (Get-Process -Id $existingPid -ErrorAction SilentlyContinue)) {
        throw "Pilot is already running with PID $existingPid"
    }
}

$statusPath = Join-Path $outputDir "pilot_status.json"
$command = ('"{0}" -u "{1}" --model "{2}" --max-steps {3} --output-dir "{4}" --status-path "{5}" 1>"{6}" 2>"{7}"' -f `
    $python, $runner, $Model, $MaxSteps, $outputDir, $statusPath, $stdoutPath, $stderrPath)

# Process.Start avoids a Windows PowerShell Start-Process bug triggered when the
# parent environment contains both Path and PATH entries. cmd remains alive as
# the tracked parent until Python finishes, and both windows stay hidden.
$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = "$env:SystemRoot\System32\cmd.exe"
$startInfo.Arguments = "/d /s /c `"$command`""
$startInfo.WorkingDirectory = $repoRoot
$startInfo.UseShellExecute = $true
$startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
$launcherProcess = [System.Diagnostics.Process]::Start($startInfo)
if (-not $launcherProcess) {
    throw "Failed to start the WebHarbor pilot process"
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
            # The runner may be replacing the status file while it starts.
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
