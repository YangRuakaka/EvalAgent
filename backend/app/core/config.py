from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Value Agent Backend"
    API_V1_PREFIX: str = "/api/v1"
    
    # LLM Configuration
    OPENAI_API_KEY: Optional[str] = None
    DEEPSEEK_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    DEFAULT_LLM_MODEL: str = "deepseek-chat"
    DEFAULT_MAX_TOKENS: int = 1000
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    LLM_BASE_URL: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None
    ANTHROPIC_BASE_URL: Optional[str] = None
    GEMINI_BASE_URL: Optional[str] = None
    # Free fallback LLM (Ollama)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    FALLBACK_LLM_MODEL: str = "llama3.2"  # Default free model for Ollama
    DEFAULT_LLM_TEMPERATURE: float = 0
    PERSONA_LLM_TEMPERATURE: float = 0
    PERSONA_VARIATION_LLM_TEMPERATURE: float = 0
    BROWSER_AGENT_OUTPUT_DIR: str = "history_logs"
    BROWSER_AGENT_MAX_STEPS: int = 100
    BROWSER_AGENT_MAX_CONCURRENT: int = 2  # Max concurrent browser agent runs
    
    # Persona Generation Settings
    MAX_KEYWORDS_PER_REQUEST: int = 10
    MIN_KEYWORD_LENGTH: int = 2
    DEFAULT_PERSONA_TYPE: str = "consumer"

    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()
