<#
.SYNOPSIS
    Automated deployment script for EvalAgent Backend on Google Cloud Run.
    Based on DEPLOY.md instructions.

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
$BucketName = "1099182984762-history-logs" # GCS Bucket for history persistence
$MountPath = "/app/history_logs"
$DefaultLLMModel = "deepseek-chat"
$Memory = "4Gi"
$Cpu = "2"
$BrowserAgentMaxConcurrent = "1"

# --- Pre-flight Checks ---

# 1. Check if gcloud is installed
if (-not (Get-Command "gcloud" -ErrorAction SilentlyContinue)) {
    Write-Error "Google Cloud CLI ('gcloud') is not installed or not in PATH. Please install it first."
    exit 1
}

# 2. API Key Handling
$ApiKey = $env:DEEPSEEK_API_KEY
$OpenAiStackApiKey = $env:OPENAI_API_KEY

if (Test-Path ".env") {
    Write-Host "Reading API Keys from .env file..." -ForegroundColor Cyan
    $EnvContent = Get-Content ".env"
    foreach ($line in $EnvContent) {
        if ($line -match "^DEEPSEEK_API_KEY=(.*)$" -and -not $ApiKey) {
            $ApiKey = $matches[1].Trim()
        }
        if ($line -match "^OPENAI_API_KEY=(.*)$" -and -not $OpenAiStackApiKey) {
            $OpenAiStackApiKey = $matches[1].Trim()
        }
    }
}

if (-not $ApiKey) {
    Write-Host "Environment variable 'DEEPSEEK_API_KEY' is not found in environment or .env file." -ForegroundColor Yellow
    Write-Host "The backend requires an API Key to function correctly on Cloud Run."
    $ApiKey = Read-Host "Please enter your DeepSeek API Key"
    
    if ([string]::IsNullOrWhiteSpace($ApiKey)) {
        Write-Error "API Key cannot be empty. Deployment aborted."
        exit 1
    }
} else {
    Write-Host "Using DEEPSEEK_API_KEY from environment variables." -ForegroundColor Green
}

if ($OpenAiStackApiKey) {
    Write-Host "Using OPENAI_API_KEY from environment variables." -ForegroundColor Green
} else {
    Write-Host "OPENAI_API_KEY not found. Some features (GPT-4o) may not work." -ForegroundColor Yellow
}

# --- Deployment ---

Write-Host "Starting deployment for service: $ServiceName..." -ForegroundColor Cyan
Write-Host "Region: $Region"
Write-Host "Storage Bucket: $BucketName"

# Construct the command arguments
# Note: volume parameters might vary slightly based on gcloud version, but these match DEPLOY.md
$gcloudArgs = @(
    "run", "deploy", $ServiceName,
    "--source", ".",
    "--region", $Region,
    "--allow-unauthenticated",
    "--execution-environment", "gen2",
    "--memory", $Memory,
    "--cpu", $Cpu,
    "--add-volume", "name=logs-storage,type=cloud-storage,bucket=$BucketName",
    "--add-volume-mount", "volume=logs-storage,mount-path=$MountPath",
    "--set-env-vars", "DEEPSEEK_API_KEY=$ApiKey,OPENAI_API_KEY=$OpenAiStackApiKey,DEFAULT_LLM_MODEL=$DefaultLLMModel,BROWSER_AGENT_MAX_CONCURRENT=$BrowserAgentMaxConcurrent"
)

Write-Host "Executing gcloud command..." -ForegroundColor DarkGray

# Execute the command
# Using Start-Process to pass arguments cleanly, or direct invocation
& gcloud @gcloudArgs

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nDeployment completed successfully!" -ForegroundColor Green
} else {
    Write-Error "`nDeployment failed with exit code $LASTEXITCODE."
}
