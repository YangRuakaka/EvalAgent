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

# --- Pre-flight Checks ---

# 1. Check if gcloud is installed
if (-not (Get-Command "gcloud" -ErrorAction SilentlyContinue)) {
    Write-Error "Google Cloud CLI ('gcloud') is not installed or not in PATH. Please install it first."
    exit 1
}

# 2. API Key Handling
$ApiKey = $env:DEEPSEEK_API_KEY

if (-not $ApiKey -and (Test-Path ".env")) {
    Write-Host "Reading API Key from .env file..." -ForegroundColor Cyan
    $EnvContent = Get-Content ".env"
    foreach ($line in $EnvContent) {
        if ($line -match "^DEEPSEEK_API_KEY=(.*)$") {
            $ApiKey = $matches[1].Trim()
            break
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
    "--add-volume", "name=logs-storage,type=cloud-storage,bucket=$BucketName",
    "--add-volume-mount", "volume=logs-storage,mount-path=$MountPath",
    "--set-env-vars", "DEEPSEEK_API_KEY=$ApiKey,DEFAULT_LLM_MODEL=$DefaultLLMModel"
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
