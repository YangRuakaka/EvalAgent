"""Centralized factory helpers for creating LLM clients across providers.

This module encapsulates all LLM configuration so that services only need to
adjust settings in ``app.core.config.Settings`` to change provider details or
instantiate clients for different runtimes (LangChain, Browser Use, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass
import importlib
from enum import Enum
from typing import Any, Optional

from langchain_openai import ChatOpenAI

from ..core.config import get_settings


class LLMConfigurationError(RuntimeError):
    """Raised when the LLM cannot be configured due to missing settings."""


class LLMTarget(str, Enum):
    """Represents the runtime that will consume the LLM client."""

    LANGCHAIN_CHAT = "langchain-chat"
    BROWSER_USE = "browser-use"


class LLMProvider(str, Enum):
    """Supported LLM providers for the application."""

    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OLLAMA = "ollama"


_BROWSER_USE_CLASS_MAP: dict[LLMProvider, str] = {
    LLMProvider.DEEPSEEK: "ChatDeepSeek",
    LLMProvider.OPENAI: "ChatOpenAI",
    LLMProvider.ANTHROPIC: "ChatAnthropic",
    LLMProvider.GEMINI: "ChatGemini",
    LLMProvider.OLLAMA: "ChatOllama",
}


@dataclass
class LLMConfig:
    """Resolved configuration for instantiating an LLM client."""

    provider: LLMProvider
    model: str
    api_key: str
    base_url: Optional[str]
    max_tokens: Optional[int]
    temperature: Optional[float]


class ChatLLMFactory:
    """Factory responsible for producing configured LLM client instances."""

    def __init__(self) -> None:
        self._settings = get_settings()

    def create(
        self,
        *,
        target: LLMTarget = LLMTarget.LANGCHAIN_CHAT,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Any:
        config = self._build_config(
            provider_override=provider,
            api_key_override=api_key,
            model_override=model,
            base_url_override=base_url,
            max_tokens_override=max_tokens,
            temperature_override=temperature,
        )

        if target is LLMTarget.LANGCHAIN_CHAT:
            return self._create_langchain_chat(config)

        if target is LLMTarget.BROWSER_USE:
            return self._create_browser_use_chat(config)

        raise LLMConfigurationError(f"Unsupported LLM target: {target}")
    
    def get_langchain_llm(
        self,
        model: Optional[str] = None,
        **overrides: Any
    ) -> Any:
        """Get a LangChain-compatible LLM client.
        
        Args:
            model: Optional model name override
            **overrides: Additional parameter overrides (api_key, base_url, etc.)
            
        Returns:
            Configured LangChain chat model
        """
        
        return self.create(
            target=LLMTarget.LANGCHAIN_CHAT,
            model=model,
            **overrides
        )

    def _build_config(
        self,
        *,
        provider_override: Optional[str],
        api_key_override: Optional[str],
        model_override: Optional[str],
        base_url_override: Optional[str],
        max_tokens_override: Optional[int],
        temperature_override: Optional[float],
    ) -> LLMConfig:
        settings = self._settings

        resolved_model = model_override or settings.DEFAULT_LLM_MODEL
        resolved_provider = self._resolve_provider(provider_override, resolved_model)

        resolved_api_key = self._resolve_api_key(resolved_provider, api_key_override)
        # Ollama doesn't require an API key
        if not resolved_api_key and resolved_provider is not LLMProvider.OLLAMA:
            raise LLMConfigurationError(
                "LLM API key not configured. Populate the corresponding environment variable."
            )

        resolved_base_url = self._resolve_base_url(resolved_provider, base_url_override)
        resolved_max_tokens = max_tokens_override or settings.DEFAULT_MAX_TOKENS
        resolved_temperature = (
            temperature_override
            if temperature_override is not None
            else settings.DEFAULT_LLM_TEMPERATURE
        )

        return LLMConfig(
            provider=resolved_provider,
            model=resolved_model,
            api_key=resolved_api_key,
            base_url=resolved_base_url,
            max_tokens=resolved_max_tokens,
            temperature=resolved_temperature,
        )

    def _resolve_provider(
        self,
        provider_override: Optional[str],
        model: Optional[str],
    ) -> LLMProvider:
        if provider_override:
            try:
                return LLMProvider(provider_override.lower())
            except ValueError as exc:
                raise LLMConfigurationError(
                    f"Unsupported provider override: {provider_override}"
                ) from exc

        if model:
            normalised = model.lower()
            if "deepseek" in normalised:
                return LLMProvider.DEEPSEEK
            if normalised.startswith("claude"):
                return LLMProvider.ANTHROPIC
            if "gemini" in normalised:
                return LLMProvider.GEMINI
            if "ollama" in normalised or normalised.startswith("llama") or normalised.startswith("mistral") or normalised.startswith("phi"):
                return LLMProvider.OLLAMA
            if normalised.startswith("gpt") or normalised.startswith("o"):
                return LLMProvider.OPENAI

        # Fallback to OpenAI-compatible defaults
        return LLMProvider.OPENAI

    def _resolve_api_key(
        self,
        provider: LLMProvider,
        api_key_override: Optional[str],
    ) -> Optional[str]:
        settings = self._settings

        # Ollama doesn't require an API key (free/local)
        if provider is LLMProvider.OLLAMA:
            return None

        if api_key_override:
            return api_key_override

        if provider is LLMProvider.DEEPSEEK:
            return settings.DEEPSEEK_API_KEY or settings.OPENAI_API_KEY
        if provider is LLMProvider.ANTHROPIC:
            return settings.ANTHROPIC_API_KEY
        if provider is LLMProvider.GEMINI:
            return settings.GEMINI_API_KEY

        return settings.OPENAI_API_KEY or settings.DEEPSEEK_API_KEY

    def _resolve_base_url(
        self,
        provider: LLMProvider,
        base_url_override: Optional[str],
    ) -> Optional[str]:
        settings = self._settings

        if base_url_override:
            return base_url_override

        if provider is LLMProvider.DEEPSEEK:
            return settings.DEEPSEEK_BASE_URL
        if provider is LLMProvider.OPENAI:
            return settings.OPENAI_BASE_URL or settings.LLM_BASE_URL
        if provider is LLMProvider.ANTHROPIC:
            return settings.ANTHROPIC_BASE_URL
        if provider is LLMProvider.GEMINI:
            return settings.GEMINI_BASE_URL
        if provider is LLMProvider.OLLAMA:
            return settings.OLLAMA_BASE_URL

        return settings.LLM_BASE_URL

    def _create_langchain_chat(self, config: LLMConfig) -> Any:
        provider = config.provider

        if provider in (LLMProvider.OPENAI, LLMProvider.DEEPSEEK):
            return ChatOpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
                model=config.model,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            )

        if provider is LLMProvider.ANTHROPIC:
            try:
                module = importlib.import_module("langchain_anthropic")
                ChatAnthropic = getattr(module, "ChatAnthropic")
            except (ImportError, AttributeError) as exc:
                raise LLMConfigurationError(
                    "langchain-anthropic is required for Anthropic models. Install it via 'pip install langchain-anthropic'."
                ) from exc

            return ChatAnthropic(
                anthropic_api_key=config.api_key,
                model=config.model,
                temperature=config.temperature,
                max_tokens_to_sample=config.max_tokens,
            )

        if provider is LLMProvider.GEMINI:
            try:
                module = importlib.import_module("langchain_google_genai")
                ChatGoogleGenerativeAI = getattr(module, "ChatGoogleGenerativeAI")
            except (ImportError, AttributeError) as exc:
                raise LLMConfigurationError(
                    "langchain-google-genai is required for Gemini models. Install it via 'pip install langchain-google-genai'."
                ) from exc

            return ChatGoogleGenerativeAI(
                api_key=config.api_key,
                model=config.model,
                temperature=config.temperature,
                max_output_tokens=config.max_tokens,
            )

        if provider is LLMProvider.OLLAMA:
            try:
                # Use deprecated langchain_community for compatibility with existing langchain versions
                # Note: langchain-ollama requires langchain-core>=1.0.0 which conflicts with other packages
                import warnings
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain.*")
                    from langchain_community.chat_models import ChatOllama
            except ImportError as exc:
                raise LLMConfigurationError(
                    "langchain-community is required for Ollama models. Install it via 'pip install langchain-community'."
                ) from exc

            # Ollama doesn't need API key, base_url defaults to http://localhost:11434
            ollama_kwargs: dict[str, Any] = {
                "model": config.model,
            }
            if config.base_url:
                ollama_kwargs["base_url"] = config.base_url
            if config.temperature is not None:
                ollama_kwargs["temperature"] = config.temperature
            if config.max_tokens is not None:
                ollama_kwargs["num_ctx"] = config.max_tokens

            return ChatOllama(**ollama_kwargs)

        raise LLMConfigurationError(f"Unsupported provider for LangChain chat: {provider}")

    def _create_browser_use_chat(self, config: LLMConfig) -> Any:
        provider = config.provider

        class_name = _BROWSER_USE_CLASS_MAP.get(provider)
        if not class_name:
            raise LLMConfigurationError(
                f"Unsupported provider for browser-use: {provider.value}"
            )

        try:
            module = importlib.import_module("browser_use.llm")
            BrowserChat = getattr(module, class_name)
        except (ImportError, AttributeError) as exc:
            raise LLMConfigurationError(
                "browser-use LLM adapters are unavailable. Ensure 'browser-use' is installed with the required extras."
            ) from exc

        # browser-use ChatOllama only accepts 'model' parameter
        # It doesn't accept api_key, base_url, max_tokens, or temperature
        if provider is LLMProvider.OLLAMA:
            chat_kwargs: dict[str, Any] = {
                "model": config.model,
            }
        else:
            chat_kwargs: dict[str, Any] = {
                "model": config.model,
            }
            if config.api_key:
                chat_kwargs["api_key"] = config.api_key
            if config.base_url:
                chat_kwargs["base_url"] = config.base_url
            # if config.max_tokens is not None:
            #     chat_kwargs["max_tokens"] = config.max_tokens
            if config.temperature is not None:
                chat_kwargs["temperature"] = config.temperature

        return BrowserChat(**chat_kwargs)


_factory = ChatLLMFactory()


def get_chat_llm(**overrides: Any) -> Any:
    """Create a configured LangChain-compatible chat model instance."""

    return _factory.create(target=LLMTarget.LANGCHAIN_CHAT, **overrides)


def get_browser_use_llm(**overrides: Any) -> Any:
    """Create a configured browser-use chat model instance."""

    return _factory.create(target=LLMTarget.BROWSER_USE, **overrides)
