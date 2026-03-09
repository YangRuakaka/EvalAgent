#!/usr/bin/env bash

set -euo pipefail

SERVICE_NAME="eval-agent-backend"
REGION="us-central1"
BUCKET_NAME="evalagent-67802-history-logs"
MOUNT_PATH="/app/history_logs"
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HISTORY_LOGS_PATH="${SCRIPT_ROOT}/history_logs"
BROWSER_AGENT_RUNS_PATH="${SCRIPT_ROOT}/browser_agent_runs"
HISTORY_LOGS_DIR="${MOUNT_PATH}/history_logs"
BROWSER_AGENT_RUN_OUTPUT_DIR="${MOUNT_PATH}/browser_agent_runs"

DEFAULT_LLM_MODEL="gpt-4o"
MEMORY="4Gi"
CPU="2"

BROWSER_AGENT_MAX_CONCURRENT="4"
BROWSER_AGENT_MAX_CONCURRENT_CAP="4"
BROWSER_AGENT_CONCURRENCY_FALLBACK_ENABLED="true"
BROWSER_AGENT_CONCURRENCY_FALLBACK_MAX_RETRIES="2"
BROWSER_AGENT_CONCURRENCY_FALLBACK_MIN="1"
BROWSER_AGENT_MAX_PARALLEL_RUNS="1"
BROWSER_AGENT_MAX_STEPS="30"
BROWSER_AGENT_RUN_TIMEOUT="0"
BROWSER_AGENT_BROWSER_START_TIMEOUT="180"
BROWSER_AGENT_BROWSER_LAUNCH_TIMEOUT="120"
BROWSER_AGENT_BROWSER_LAUNCH_RETRIES="3"
BROWSER_AGENT_BROWSER_RETRY_BACKOFF_SECONDS="2"

JUDGE_EVALUATION_MAX_CONCURRENCY="12"
JUDGE_EVALUATION_STEP_MAX_CONCURRENCY="12"
JUDGE_EVALUATION_TASK_TIMEOUT_SECONDS="1800"

echo_info() {
  printf "\033[36m%s\033[0m\n" "$1"
}

echo_success() {
  printf "\033[32m%s\033[0m\n" "$1"
}

echo_warn() {
  printf "\033[33m%s\033[0m\n" "$1"
}

echo_error() {
  printf "\033[31m%s\033[0m\n" "$1"
}

resolve_gcloud_bin() {
  if command -v gcloud >/dev/null 2>&1; then
    command -v gcloud
    return 0
  fi

  local candidates=(
    "$HOME/google-cloud-sdk/bin/gcloud"
    "/usr/local/google-cloud-sdk/bin/gcloud"
    "/opt/homebrew/share/google-cloud-sdk/bin/gcloud"
  )

  local match
  match=$(find /opt/homebrew/Caskroom/google-cloud-sdk /usr/local/Caskroom/google-cloud-sdk -type f -name gcloud 2>/dev/null | head -n 1 || true)
  if [[ -n "$match" ]]; then
    candidates+=("$match")
  fi

  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -x "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done

  return 1
}

GCLOUD_BIN=""
if GCLOUD_BIN="$(resolve_gcloud_bin)"; then
  echo_success "Using gcloud: ${GCLOUD_BIN}"
else
  echo_error "Google Cloud CLI (gcloud) 未安装或不在 PATH 中。"
  echo ""
  echo "请先安装（macOS）："
  echo "  curl https://sdk.cloud.google.com | bash"
  echo "  exec -l \$SHELL"
  echo "  gcloud init"
  echo ""
  echo "若已安装但当前终端找不到，可执行："
  echo "  source \"\$HOME/google-cloud-sdk/path.zsh.inc\""
  exit 1
fi

PYTHON_COMMAND=""
if command -v python3 >/dev/null 2>&1; then
  PYTHON_COMMAND="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_COMMAND="python"
fi

if [[ -n "$PYTHON_COMMAND" ]]; then
  echo_info "Running Python syntax check for app/ ..."
  "$PYTHON_COMMAND" -m compileall -q "${SCRIPT_ROOT}/app"
  echo_success "Python syntax check passed."
else
  echo_warn "Python executable not found in PATH. Skipping local syntax pre-check."
fi

ENV_PATH="${SCRIPT_ROOT}/.env"

API_KEY="${OPENAI_API_KEY:-}"
DEEPSEEK_API_KEY_VALUE="${DEEPSEEK_API_KEY:-}"
ANTHROPIC_API_KEY_VALUE="${ANTHROPIC_API_KEY:-}"
GEMINI_API_KEY_VALUE="${GEMINI_API_KEY:-}"

if [[ -f "$ENV_PATH" ]]; then
  echo_info "Reading configuration from ${ENV_PATH}..."
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "${line//[[:space:]]/}" || "${line#\#}" != "$line" ]] && continue
    if [[ "$line" =~ ^([^=]+)=(.*)$ ]]; then
      key="$(echo "${BASH_REMATCH[1]}" | xargs)"
      value="${BASH_REMATCH[2]}"
      value="$(echo "$value" | sed -e 's/^\s*//' -e 's/\s*$//' -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")"

      case "$key" in
        OPENAI_API_KEY)
          [[ -z "$API_KEY" ]] && API_KEY="$value"
          ;;
        DEEPSEEK_API_KEY)
          [[ -z "$DEEPSEEK_API_KEY_VALUE" ]] && DEEPSEEK_API_KEY_VALUE="$value"
          ;;
        ANTHROPIC_API_KEY)
          [[ -z "$ANTHROPIC_API_KEY_VALUE" ]] && ANTHROPIC_API_KEY_VALUE="$value"
          ;;
        GEMINI_API_KEY)
          [[ -z "$GEMINI_API_KEY_VALUE" ]] && GEMINI_API_KEY_VALUE="$value"
          ;;
        DEFAULT_LLM_MODEL)
          if [[ -z "${DEFAULT_LLM_MODEL:-}" || "$DEFAULT_LLM_MODEL" == "gpt-4o" ]]; then
            DEFAULT_LLM_MODEL="$value"
          fi
          ;;
      esac
    fi
  done < "$ENV_PATH"
fi

if [[ -z "$API_KEY" && -z "$DEEPSEEK_API_KEY_VALUE" && -z "$ANTHROPIC_API_KEY_VALUE" && -z "$GEMINI_API_KEY_VALUE" ]]; then
  echo_warn "No API Keys found in environment or .env file."
  echo_warn "The backend requires at least one API Key to function correctly."
fi

[[ -n "$API_KEY" ]] && echo_success "OPENAI_API_KEY configured."
[[ -n "$DEEPSEEK_API_KEY_VALUE" ]] && echo_success "DEEPSEEK_API_KEY configured."
[[ -n "$ANTHROPIC_API_KEY_VALUE" ]] && echo_success "ANTHROPIC_API_KEY configured."
[[ -n "$GEMINI_API_KEY_VALUE" ]] && echo_success "GEMINI_API_KEY configured."

if [[ -d "$HISTORY_LOGS_PATH" || -d "$BROWSER_AGENT_RUNS_PATH" ]]; then
  echo_info "Syncing local cache/browser-run folders to GCS Bucket (${BUCKET_NAME})..."

  if command -v gsutil >/dev/null 2>&1; then
    if [[ -d "$HISTORY_LOGS_PATH" ]]; then
      if gsutil -m rsync -r "$HISTORY_LOGS_PATH" "gs://${BUCKET_NAME}/history_logs"; then
        echo_success "history_logs synced successfully."
      else
        echo_warn "Failed to sync history_logs. Continuing with deployment..."
      fi
    fi

    if [[ -d "$BROWSER_AGENT_RUNS_PATH" ]]; then
      if gsutil -m rsync -r "$BROWSER_AGENT_RUNS_PATH" "gs://${BUCKET_NAME}/browser_agent_runs"; then
        echo_success "browser_agent_runs synced successfully."
      else
        echo_warn "Failed to sync browser_agent_runs. Continuing with deployment..."
      fi
    fi
  else
    echo_warn "gsutil not found. Skipping folder sync."
  fi
fi

echo_info "Starting deployment for service: ${SERVICE_NAME}"
echo "Region: ${REGION}"
echo "Storage Bucket: ${BUCKET_NAME}"

GCLOUD_ARGS=(
  run deploy "${SERVICE_NAME}"
  --source "${SCRIPT_ROOT}"
  --region "${REGION}"
  --allow-unauthenticated
  --execution-environment gen2
  --memory "${MEMORY}"
  --cpu "${CPU}"
  --concurrency 1
  --timeout 3600
  --no-cpu-throttling
  --add-volume "name=logs-storage,type=cloud-storage,bucket=${BUCKET_NAME}"
  --add-volume-mount "volume=logs-storage,mount-path=${MOUNT_PATH}"
)

ENV_VARS=(
  "DEFAULT_LLM_MODEL=${DEFAULT_LLM_MODEL}"
  "CACHE_HISTORY_LOGS_DIR=${HISTORY_LOGS_DIR}"
  "BROWSER_AGENT_RUN_OUTPUT_DIR=${BROWSER_AGENT_RUN_OUTPUT_DIR}"
  "BROWSER_AGENT_OUTPUT_DIR=${BROWSER_AGENT_RUN_OUTPUT_DIR}"
  "BROWSER_AGENT_MAX_CONCURRENT=${BROWSER_AGENT_MAX_CONCURRENT}"
  "BROWSER_AGENT_MAX_CONCURRENT_CAP=${BROWSER_AGENT_MAX_CONCURRENT_CAP}"
  "BROWSER_AGENT_CONCURRENCY_FALLBACK_ENABLED=${BROWSER_AGENT_CONCURRENCY_FALLBACK_ENABLED}"
  "BROWSER_AGENT_CONCURRENCY_FALLBACK_MAX_RETRIES=${BROWSER_AGENT_CONCURRENCY_FALLBACK_MAX_RETRIES}"
  "BROWSER_AGENT_CONCURRENCY_FALLBACK_MIN=${BROWSER_AGENT_CONCURRENCY_FALLBACK_MIN}"
  "BROWSER_AGENT_MAX_PARALLEL_RUNS=${BROWSER_AGENT_MAX_PARALLEL_RUNS}"
  "BROWSER_AGENT_MAX_STEPS=${BROWSER_AGENT_MAX_STEPS}"
  "BROWSER_AGENT_RUN_TIMEOUT=${BROWSER_AGENT_RUN_TIMEOUT}"
  "BROWSER_AGENT_BROWSER_START_TIMEOUT=${BROWSER_AGENT_BROWSER_START_TIMEOUT}"
  "BROWSER_AGENT_BROWSER_LAUNCH_TIMEOUT=${BROWSER_AGENT_BROWSER_LAUNCH_TIMEOUT}"
  "BROWSER_AGENT_BROWSER_LAUNCH_RETRIES=${BROWSER_AGENT_BROWSER_LAUNCH_RETRIES}"
  "BROWSER_AGENT_BROWSER_RETRY_BACKOFF_SECONDS=${BROWSER_AGENT_BROWSER_RETRY_BACKOFF_SECONDS}"
  "JUDGE_EVALUATION_MAX_CONCURRENCY=${JUDGE_EVALUATION_MAX_CONCURRENCY}"
  "JUDGE_EVALUATION_STEP_MAX_CONCURRENCY=${JUDGE_EVALUATION_STEP_MAX_CONCURRENCY}"
  "JUDGE_EVALUATION_TASK_TIMEOUT_SECONDS=${JUDGE_EVALUATION_TASK_TIMEOUT_SECONDS}"
  "BROWSER_AGENT_FORCE_THREADED_RUN_ON_WINDOWS=true"
  "BROWSER_AGENT_ENABLE_SCREENSHOT_PROCESSING=false"
  "BROWSER_AGENT_MAX_SCREENSHOTS=0"
  "BROWSER_AGENT_INCLUDE_SCREENSHOTS_IN_RUN_RESPONSE=false"
  "BROWSER_AGENT_INCLUDE_SCREENSHOT_BASE64_IN_HISTORY_PAYLOAD=true"
  "ENABLE_OLLAMA=false"
)

[[ -n "$API_KEY" ]] && ENV_VARS+=("OPENAI_API_KEY=${API_KEY}")
[[ -n "$DEEPSEEK_API_KEY_VALUE" ]] && ENV_VARS+=("DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY_VALUE}")
[[ -n "$ANTHROPIC_API_KEY_VALUE" ]] && ENV_VARS+=("ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY_VALUE}")
[[ -n "$GEMINI_API_KEY_VALUE" ]] && ENV_VARS+=("GEMINI_API_KEY=${GEMINI_API_KEY_VALUE}")

GCLOUD_ARGS+=(--set-env-vars "$(IFS=,; echo "${ENV_VARS[*]}")")

echo_info "Executing gcloud command..."

if "$GCLOUD_BIN" "${GCLOUD_ARGS[@]}"; then
  echo_success "Deployment completed successfully!"
else
  echo_error "Deployment failed."
  exit 1
fi