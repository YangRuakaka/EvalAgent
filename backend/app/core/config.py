from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional, List

class Settings(BaseSettings):
    PROJECT_NAME: str = "Value Agent Backend"
    API_V1_PREFIX: str = "/api/v1"
    PUBLIC_API_BASE_URL: Optional[str] = None
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_RELOAD: bool = True
    API_WORKERS: int = 1
    
    # LLM Configuration
    OPENAI_API_KEY: Optional[str] = None
    DEEPSEEK_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    DEFAULT_LLM_MODEL: str = "deepseek-chat"
    DEFAULT_MAX_TOKENS: int = 1000
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    LLM_BASE_URL: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None
    ANTHROPIC_BASE_URL: Optional[str] = None
    GEMINI_BASE_URL: Optional[str] = None
    ENABLE_OLLAMA: bool = False
    # Free fallback LLM (Ollama)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    FALLBACK_LLM_MODEL: str = "llama3.2"  # Default free model for Ollama
    DEFAULT_LLM_TEMPERATURE: float = 0
    LLM_ENABLE_CONSOLE_TRACE: bool = False
    PERSONA_LLM_TEMPERATURE: float = 0
    PERSONA_VARIATION_LLM_TEMPERATURE: float = 0
    PERSONA_VARIATION_MAX_CONCURRENCY: int = 4
    CACHE_HISTORY_LOGS_DIR: str = "history_logs"
    HISTORY_LOGS_PRELOAD_ENABLED: bool = True
    HISTORY_LOGS_PRELOAD_DATASETS: str = "data1,data2,data3"
    HISTORY_LOGS_PRELOAD_SCREENSHOT_MODE: str = "proxy"
    HISTORY_LOGS_PRELOAD_WRITE_MISSING_HASHES: bool = False
    BROWSER_AGENT_RUN_OUTPUT_DIR: str = "browser_agent_runs"
    # Legacy setting kept for backward compatibility with existing deployments.
    BROWSER_AGENT_OUTPUT_DIR: str = "history_logs"
    BROWSER_AGENT_MAX_STEPS: int = 20
    BROWSER_AGENT_MAX_CONCURRENT: int = 4  # Max concurrent browser agents per run
    BROWSER_AGENT_MAX_CONCURRENT_CAP: int = 4  # Safety cap to avoid too many concurrent browser sessions
    BROWSER_AGENT_CONCURRENCY_FALLBACK_ENABLED: bool = True  # Auto rollback to lower concurrency on resource/startup pressure
    BROWSER_AGENT_CONCURRENCY_FALLBACK_MAX_RETRIES: int = 2  # Max fallback stages (e.g. 4 -> 2 -> 1)
    BROWSER_AGENT_CONCURRENCY_FALLBACK_MIN: int = 1  # Minimum concurrency floor when rollback is triggered
    BROWSER_AGENT_MAX_PARALLEL_RUNS: int = 1  # Max concurrent run_id jobs in the API queue
    BROWSER_AGENT_FORCE_THREADED_RUN_ON_WINDOWS: bool = True  # Run each agent in dedicated Proactor loop thread on Windows
    BROWSER_AGENT_RUN_TIMEOUT: int = 0  # Max seconds for entire run; <=0 disables timeout
    BROWSER_AGENT_BROWSER_START_TIMEOUT: int = 120  # Max seconds to wait for browser to start
    BROWSER_AGENT_BROWSER_LAUNCH_TIMEOUT: int = 120  # Timeout for BrowserLaunchEvent (browser_use internal)
    BROWSER_AGENT_BROWSER_LAUNCH_RETRIES: int = 2
    BROWSER_AGENT_BROWSER_RETRY_BACKOFF_SECONDS: float = 2.0
    BROWSER_AGENT_ENABLE_SCREENSHOTS: bool = True
    BROWSER_AGENT_ENABLE_SCREENSHOT_PROCESSING: bool = False
    BROWSER_AGENT_MAX_SCREENSHOTS: int = 0  # 0 means no limit: persist all available screenshots
    BROWSER_AGENT_INCLUDE_SCREENSHOTS_IN_RUN_RESPONSE: bool = False
    BROWSER_AGENT_INCLUDE_SCREENSHOT_BASE64_IN_HISTORY_PAYLOAD: bool = False
    BROWSER_AGENT_STATUS_LOG_BUFFER_SIZE: int = 0  # 0 means unlimited (keep all captured logs)
    BROWSER_AGENT_STATUS_LOG_LEVEL: str = "INFO"  # Log level captured into run-status logs (e.g. INFO/DEBUG)
    BROWSER_AGENT_EXTERNAL_LOG_LEVEL: str = "INFO"  # Source logger level for browser_use/cdp_use capture
    BROWSER_AGENT_STREAM_RUN_LOGS_TO_STDOUT: bool = True  # Mirror per-run logs to server stdout
    BROWSER_AGENT_EVENTS_POLL_INTERVAL_SECONDS: float = 0.25
    
    # Persona Generation Settings
    MAX_KEYWORDS_PER_REQUEST: int = 10
    MIN_KEYWORD_LENGTH: int = 2
    DEFAULT_PERSONA_TYPE: str = "consumer"
    CORS_ALLOW_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "https://evalagent-67802.web.app",
        "https://evalagent-67802.firebaseapp.com",
    ]
    CORS_ALLOW_ORIGIN_REGEX: str = r"https://evalagent-67802(--[a-zA-Z0-9-]+)?\.web\.app"
    CORS_ALLOW_LOCALHOST_REGEX: str = r"http://(localhost|127\.0\.0\.1):\d+"
    JUDGE_EVALUATION_MAX_CONCURRENCY: int = 8
    JUDGE_EVALUATION_STEP_MAX_CONCURRENCY: int = 12
    JUDGE_EVALUATION_TOTAL_LLM_CONCURRENCY_BUDGET: int = 32
    JUDGE_EVALUATION_TASK_TIMEOUT_SECONDS: int = 1800
    JUDGE_EVALUATION_OVERALL_ASSESSMENT_CONFIDENCE_THRESHOLD: float = 0.7
    JUDGE_EVALUATION_VERBOSE_STEP_LOGS: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()
