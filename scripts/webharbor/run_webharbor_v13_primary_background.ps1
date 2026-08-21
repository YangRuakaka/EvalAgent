param(
    [string]$Model = "deepseek-chat",
    [int]$MaxSteps = 15
)

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$python = Join-Path $repoRoot ".venv-browseruse-0136\Scripts\python.exe"
$runner = Join-Path $PSScriptRoot "run_webharbor_v13_pilot.py"
$outputDir = Join-Path $repoRoot "browser_agent_runs_webharbor_v13_pilot"
$pidPath = Join-Path $outputDir "primary.pid"
$stdoutPath = Join-Path $outputDir "primary.stdout.log"
$stderrPath = Join-Path $outputDir "primary.stderr.log"
$statusPath = Join-Path $outputDir "primary_status.json"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Browser Use Python environment not found: $python"
}

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

if (Test-Path -LiteralPath $pidPath) {
    $existingPid = Get-Content -LiteralPath $pidPath -ErrorAction SilentlyContinue
    if ($existingPid -and (Get-Process -Id $existingPid -ErrorAction SilentlyContinue)) {
        throw "Primary WebHarbor batch is already running with PID $existingPid"
    }
}

$command = ('"{0}" -u "{1}" --full --model "{2}" --max-steps {3} --output-dir "{4}" --status-path "{5}" 1>"{6}" 2>"{7}"' -f `
    $python, $runner, $Model, $MaxSteps, $outputDir, $statusPath, $stdoutPath, $stderrPath)

# The display may turn off while the Python process keeps Windows awake. Both
# the launcher and BrowserUse batch stay hidden.
$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = "$env:SystemRoot\System32\cmd.exe"
$startInfo.Arguments = "/d /s /c `"$command`""
$startInfo.WorkingDirectory = $repoRoot
$startInfo.UseShellExecute = $true
$startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
$launcherProcess = [System.Diagnostics.Process]::Start($startInfo)
if (-not $launcherProcess) {
    throw "Failed to start the primary WebHarbor batch"
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

