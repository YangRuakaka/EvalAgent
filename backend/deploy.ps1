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
$DefaultLLMModel = "gpt-4o"
$Memory = "4Gi"
$Cpu = "2"
$BrowserAgentMaxConcurrent = "2"
$BrowserAgentMaxSteps = "30"

# --- Pre-flight Checks ---

# 1. Check if gcloud is installed
if (-not (Get-Command "gcloud" -ErrorAction SilentlyContinue)) {
    Write-Error "Google Cloud CLI ('gcloud') is not installed or not in PATH. Please install it first."
    exit 1
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

# --- Sync History Logs ---
if (Test-Path $HistoryLogsPath) {
    Write-Host "Syncing local history_logs to GCS Bucket ($BucketName)..." -ForegroundColor Cyan
    # Use gsutil to sync files. -m for multi-threaded, -r for recursive.
    # We use Start-Process to ensure it runs correctly across environments or call gsutil directly if in path.
    
    $GsutilCommand = "gsutil"
    if ($IsWindows -and (Get-Command "gsutil.cmd" -ErrorAction SilentlyContinue)) {
        $GsutilCommand = "gsutil.cmd"
    }

    if (Get-Command $GsutilCommand -ErrorAction SilentlyContinue) {
        & $GsutilCommand -m cp -r "$HistoryLogsPath\*" "gs://$BucketName/"
        if ($LASTEXITCODE -eq 0) {
            Write-Host "History logs synced successfully." -ForegroundColor Green
        } else {
            Write-Warning "Failed to sync history logs. Continuing with deployment..."
        }
    } else {
        Write-Warning "gsutil not found. Skipping history logs sync."
    }
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
    "--add-volume", "name=logs-storage,type=cloud-storage,bucket=$BucketName",
    "--add-volume-mount", "volume=logs-storage,mount-path=$MountPath"
)

# Build environment variables list
$EnvVars = @(
    "DEFAULT_LLM_MODEL=$DefaultLLMModel",
    "BROWSER_AGENT_MAX_CONCURRENT=$BrowserAgentMaxConcurrent",
    "BROWSER_AGENT_MAX_STEPS=$BrowserAgentMaxSteps",
    "BROWSER_AGENT_ENABLE_SCREENSHOT_PROCESSING=false",
    "BROWSER_AGENT_MAX_SCREENSHOTS=3",
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
