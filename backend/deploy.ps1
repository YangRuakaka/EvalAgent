<#
.SYNOPSIS
    Automated deployment script for EvalAgent Backend on Google Cloud Run.

    # Google Cloud Storage bucket status URL:
    # https://console.cloud.google.com/storage/browser/evalagent-67802-history-logs

.DESCRIPTION
    This script automates the deployment of the EvalAgent backend service to Cloud Run.
    It handles:
    1. Checking for the necessary API Key (DeepSeek).
    2. Constructing the gcloud run deploy command with volume mounts for history logs.
    3. Setting environment variables required for the production environment.

.EXAMPLE
    .\deploy.ps1
    # Interactive mode, will prompt for API Key if not set in environment.

.EXAMPLE
    $env:DEEPSEEK_API_KEY = "sk-..."
    .\deploy.ps1
    # Non-interactive mode using environment variable.
#>

$ErrorActionPreference = "Stop"

# --- Configuration ---
$ServiceName = "eval-agent-backend"
$Region = "us-central1"
$BucketName = "evalagent-67802-history-logs" # GCS Bucket for history persistence
$MountPath = "/app/history_logs"
$SourcePath = $PSScriptRoot
$HistoryLogsPath = Join-Path $PSScriptRoot "history_logs"
$BrowserAgentRunsPath = Join-Path $PSScriptRoot "browser_agent_runs"
$HistoryLogsDir = "$MountPath/history_logs"
$BrowserAgentRunOutputDir = "$MountPath/browser_agent_runs"
$DefaultLLMModel = "gpt-4o"
$Memory = "4Gi"
$Cpu = "2"
$BrowserAgentMaxConcurrent = "4"
$BrowserAgentMaxConcurrentCap = "4"
$BrowserAgentConcurrencyFallbackEnabled = "true"
$BrowserAgentConcurrencyFallbackMaxRetries = "2"
$BrowserAgentConcurrencyFallbackMin = "1"
$BrowserAgentMaxParallelRuns = "1"
$BrowserAgentMaxSteps = "30"
$BrowserAgentRunTimeout = "0"
$BrowserAgentBrowserStartTimeout = "180"
$BrowserAgentBrowserLaunchTimeout = "120"
$BrowserAgentBrowserLaunchRetries = "3"
$BrowserAgentBrowserRetryBackoffSeconds = "2"
$JudgeEvaluationMaxConcurrency = "12"
$JudgeEvaluationStepMaxConcurrency = "16"
$JudgeEvaluationTotalLlmConcurrencyBudget = "192"
$JudgeEvaluationTaskTimeoutSeconds = "3600"

# --- Pre-flight Checks ---

# 1. Check if gcloud is installed
if (-not (Get-Command "gcloud" -ErrorAction SilentlyContinue)) {
    Write-Error "Google Cloud CLI ('gcloud') is not installed or not in PATH. Please install it first."
    exit 1
}

# 1.1 Python syntax pre-check (fail fast before Cloud Run build/deploy)
$PythonCommand = $null
if (Get-Command "python" -ErrorAction SilentlyContinue) {
    $PythonCommand = "python"
} elseif (Get-Command "py" -ErrorAction SilentlyContinue) {
    $PythonCommand = "py"
}

if ($PythonCommand) {
    Write-Host "Running Python syntax check for app/ ..." -ForegroundColor Cyan
    if ($PythonCommand -eq "py") {
        & py -3 -m compileall -q "$PSScriptRoot\app"
    } else {
        & python -m compileall -q "$PSScriptRoot\app"
    }

    if ($LASTEXITCODE -ne 0) {
        Write-Error "Python syntax check failed. Fix syntax errors before deployment."
        exit 1
    }

    Write-Host "Python syntax check passed." -ForegroundColor Green
} else {
    Write-Warning "Python executable not found in PATH. Skipping local syntax pre-check."
}

# 2. API Key Handling
$EnvPath = Join-Path $PSScriptRoot ".env"

$ApiKey = $env:OPENAI_API_KEY
$DeepSeekApiKey = $env:DEEPSEEK_API_KEY
$AnthropicApiKey = $env:ANTHROPIC_API_KEY
$GeminiApiKey = $env:GEMINI_API_KEY

if (Test-Path $EnvPath) {
    Write-Host "Reading configuration from $EnvPath..." -ForegroundColor Cyan
    $EnvContent = Get-Content $EnvPath
    foreach ($line in $EnvContent) {
        # Skip comments and empty lines
        if ($line.Trim().StartsWith("#") -or [string]::IsNullOrWhiteSpace($line)) { continue }
        
        if ($line -match "^([^=]+)=(.*)$") {
            $Key = $matches[1].Trim()
            $Value = $matches[2].Trim()
            # Remove potential quotes
            $Value = $Value -replace '^"|"$|^''|''$', ''
            
            switch ($Key) {
                "OPENAI_API_KEY" { if (-not $ApiKey) { $ApiKey = $Value } }
                "DEEPSEEK_API_KEY" { if (-not $DeepSeekApiKey) { $DeepSeekApiKey = $Value } }
                "ANTHROPIC_API_KEY" { if (-not $AnthropicApiKey) { $AnthropicApiKey = $Value } }
                "GEMINI_API_KEY" { if (-not $GeminiApiKey) { $GeminiApiKey = $Value } }
                "DEFAULT_LLM_MODEL" { if (-not $env:DEFAULT_LLM_MODEL) { $DefaultLLMModel = $Value } }
            }
        }
    }
}

if (-not $ApiKey -and -not $DeepSeekApiKey -and -not $AnthropicApiKey -and -not $GeminiApiKey) {
    Write-Warning "No API Keys found in environment or .env file."
    Write-Host "The backend requires at least one API Key to function correctly."
}

if ($ApiKey) { Write-Host "OPENAI_API_KEY configured." -ForegroundColor Green }
if ($DeepSeekApiKey) { Write-Host "DEEPSEEK_API_KEY configured." -ForegroundColor Green }
if ($AnthropicApiKey) { Write-Host "ANTHROPIC_API_KEY configured." -ForegroundColor Green }
if ($GeminiApiKey) { Write-Host "GEMINI_API_KEY configured." -ForegroundColor Green }

# --- Sync history/browser folders ---
if ((Test-Path $HistoryLogsPath) -or (Test-Path $BrowserAgentRunsPath)) {
    Write-Host "Syncing local history/browser folders to GCS Bucket ($BucketName)..." -ForegroundColor Cyan

    $GcloudStorageCommand = "gcloud"
    if ($IsWindows -and (Get-Command "gcloud.cmd" -ErrorAction SilentlyContinue)) {
        $GcloudStorageCommand = "gcloud.cmd"
    }

    $GsutilCommand = "gsutil"
    if ($IsWindows -and (Get-Command "gsutil.cmd" -ErrorAction SilentlyContinue)) {
        $GsutilCommand = "gsutil.cmd"
    }

    function Invoke-BucketRsync {
        param(
            [Parameter(Mandatory = $true)]
            [string]$LocalPath,
            [Parameter(Mandatory = $true)]
            [string]$BucketPrefix
        )

        if (-not (Test-Path $LocalPath)) {
            return
        }

        $Destination = "gs://$BucketName/$BucketPrefix"
        $Synced = $false

        if (Get-Command $GcloudStorageCommand -ErrorAction SilentlyContinue) {
            & $GcloudStorageCommand storage rsync --recursive "$LocalPath" "$Destination"
            if ($LASTEXITCODE -eq 0) {
                Write-Host "$BucketPrefix synced successfully via gcloud storage." -ForegroundColor Green
                $Synced = $true
            } else {
                Write-Warning "gcloud storage rsync failed for $BucketPrefix. Falling back to gsutil if available..."
            }
        }

        if (-not $Synced -and (Get-Command $GsutilCommand -ErrorAction SilentlyContinue)) {
            & $GsutilCommand -m rsync -r "$LocalPath" "$Destination"
            if ($LASTEXITCODE -eq 0) {
                Write-Host "$BucketPrefix synced successfully via gsutil." -ForegroundColor Green
                $Synced = $true
            } else {
                Write-Warning "gsutil rsync failed for $BucketPrefix. Continuing with deployment..."
            }
        }

        if (-not $Synced) {
            Write-Warning "No available sync command succeeded for $BucketPrefix. Continuing with deployment..."
        }
    }

    Invoke-BucketRsync -LocalPath $HistoryLogsPath -BucketPrefix "history_logs"
    Invoke-BucketRsync -LocalPath $BrowserAgentRunsPath -BucketPrefix "browser_agent_runs"
}

# --- Deployment ---

Write-Host "Starting deployment for service: $ServiceName..." -ForegroundColor Cyan
Write-Host "Region: $Region"
Write-Host "Storage Bucket: $BucketName"

# Construct the command arguments
# Note: volume parameters might vary slightly based on gcloud version, but these match DEPLOY.md
$gcloudArgs = @(
    "run", "deploy", $ServiceName,
    "--source", $SourcePath,
    "--region", $Region,
    "--allow-unauthenticated",
    "--execution-environment", "gen2",
    "--memory", $Memory,
    "--cpu", $Cpu,
    "--concurrency", "1",
    "--timeout", "3600",
    "--no-cpu-throttling",
    "--add-volume", "name=logs-storage,type=cloud-storage,bucket=$BucketName",
    "--add-volume-mount", "volume=logs-storage,mount-path=$MountPath"
)

# Build environment variables list
$EnvVars = @(
    "DEFAULT_LLM_MODEL=$DefaultLLMModel",
    "CACHE_HISTORY_LOGS_DIR=$HistoryLogsDir",
    "BROWSER_AGENT_RUN_OUTPUT_DIR=$BrowserAgentRunOutputDir",
    "BROWSER_AGENT_OUTPUT_DIR=$HistoryLogsDir",
    "BROWSER_AGENT_MAX_CONCURRENT=$BrowserAgentMaxConcurrent",
    "BROWSER_AGENT_MAX_CONCURRENT_CAP=$BrowserAgentMaxConcurrentCap",
    "BROWSER_AGENT_CONCURRENCY_FALLBACK_ENABLED=$BrowserAgentConcurrencyFallbackEnabled",
    "BROWSER_AGENT_CONCURRENCY_FALLBACK_MAX_RETRIES=$BrowserAgentConcurrencyFallbackMaxRetries",
    "BROWSER_AGENT_CONCURRENCY_FALLBACK_MIN=$BrowserAgentConcurrencyFallbackMin",
    "BROWSER_AGENT_MAX_PARALLEL_RUNS=$BrowserAgentMaxParallelRuns",
    "BROWSER_AGENT_MAX_STEPS=$BrowserAgentMaxSteps",
    "BROWSER_AGENT_RUN_TIMEOUT=$BrowserAgentRunTimeout",
    "BROWSER_AGENT_BROWSER_START_TIMEOUT=$BrowserAgentBrowserStartTimeout",
    "BROWSER_AGENT_BROWSER_LAUNCH_TIMEOUT=$BrowserAgentBrowserLaunchTimeout",
    "BROWSER_AGENT_BROWSER_LAUNCH_RETRIES=$BrowserAgentBrowserLaunchRetries",
    "BROWSER_AGENT_BROWSER_RETRY_BACKOFF_SECONDS=$BrowserAgentBrowserRetryBackoffSeconds",
    "JUDGE_EVALUATION_MAX_CONCURRENCY=$JudgeEvaluationMaxConcurrency",
    "JUDGE_EVALUATION_STEP_MAX_CONCURRENCY=$JudgeEvaluationStepMaxConcurrency",
    "JUDGE_EVALUATION_TOTAL_LLM_CONCURRENCY_BUDGET=$JudgeEvaluationTotalLlmConcurrencyBudget",
    "JUDGE_EVALUATION_TASK_TIMEOUT_SECONDS=$JudgeEvaluationTaskTimeoutSeconds",
    "BROWSER_AGENT_FORCE_THREADED_RUN_ON_WINDOWS=true",
    "BROWSER_AGENT_ENABLE_SCREENSHOT_PROCESSING=false",
    "BROWSER_AGENT_MAX_SCREENSHOTS=0",
    "BROWSER_AGENT_INCLUDE_SCREENSHOTS_IN_RUN_RESPONSE=false",
    "BROWSER_AGENT_INCLUDE_SCREENSHOT_BASE64_IN_HISTORY_PAYLOAD=false",
    "ENABLE_OLLAMA=false"
)

if ($ApiKey) { $EnvVars += "OPENAI_API_KEY=$ApiKey" }
if ($DeepSeekApiKey) { $EnvVars += "DEEPSEEK_API_KEY=$DeepSeekApiKey" }
if ($AnthropicApiKey) { $EnvVars += "ANTHROPIC_API_KEY=$AnthropicApiKey" }
if ($GeminiApiKey) { $EnvVars += "GEMINI_API_KEY=$GeminiApiKey" }

$gcloudArgs += "--set-env-vars"
$gcloudArgs += ($EnvVars -join ",")

Write-Host "Executing gcloud command..." -ForegroundColor DarkGray

# Determine correct gcloud command (avoid .ps1 execution policy issues on Windows)
$GcloudCommand = "gcloud"
if ($IsWindows -and (Get-Command "gcloud.cmd" -ErrorAction SilentlyContinue)) {
    $GcloudCommand = "gcloud.cmd"
}

# Execute the command
# Using Start-Process to pass arguments cleanly, or direct invocation
& $GcloudCommand @gcloudArgs

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nDeployment completed successfully!" -ForegroundColor Green
} else {
    Write-Error "`nDeployment failed with exit code $LASTEXITCODE."
}
