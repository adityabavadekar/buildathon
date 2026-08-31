"""Durable file-backed persistence for dynamic LLM provider settings and fallback priority."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_MODELS: dict[str, list[str]] = {
    "openrouter": [
        "nvidia/nemotron-3.5-lightning:free",
        "google/gemma-4-26b-a4b-it:free",
        "liquid/lfm-2.5-2.6b:free",
        "nvidia/nemotron-nano-9b-v2:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
        "poolside/laguna-s-2.1:free",
        "openai/gpt-4o",
        "deepseek/deepseek-r1",
        "meta-llama/llama-3.3-70b-instruct",
    ],
    "anthropic": [
        "anthropic/claude-3-5-sonnet-20241022",
        "anthropic/claude-3-5-haiku-20241022",
    ],
    "openai": [
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
        "openai/o3-mini",
    ],
    "groq": [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "groq/compound",
        "groq/compound-mini",
        "qwen/qwen3.6-27b",
        "qwen/qwen3.8-27b",
    ],
    "deterministic_rules": [
        "NPCI & Razorpay Rule Classifier",
    ],
}


class ProviderSetting(BaseModel):
    """Configuration for a single LLM provider in the fallback chain."""

    name: str
    label: str
    enabled: bool = True
    priority: int = Field(ge=1, le=10)
    active_model: str
    available_models: list[str]
    has_api_key: bool = False


class LLMSettingsState(BaseModel):
    """Full configurable state for LLM reasoning engine."""

    providers: list[ProviderSetting]
    timeout_seconds: int = 30
    temperature: float = 0.2


class LLMSettingsStore:
    """Thread-safe file-backed store for LLM provider preferences."""

    def __init__(self, file_path: str = "data/llm_config.json") -> None:
        self.file_path = Path(file_path)
        self._state = self._load_or_default()

    def _default_state(self) -> LLMSettingsState:
        settings = get_settings()
        primary_active_model = (
            settings.openrouter_model or DEFAULT_MODELS["openrouter"][0]
        )
        anthropic_available = [primary_active_model, *DEFAULT_MODELS["anthropic"]]
        has_openrouter = bool(
            settings.openrouter_api_key
            and settings.openrouter_api_key.get_secret_value().strip()
        )
        has_anthropic = bool(
            settings.anthropic_api_key
            and settings.anthropic_api_key.get_secret_value().strip()
        )
        has_openai = bool(
            settings.openai_api_key
            and settings.openai_api_key.get_secret_value().strip()
        )
        has_groq = bool(
            settings.groq_api_key and settings.groq_api_key.get_secret_value().strip()
        )

        return LLMSettingsState(
            providers=[
                ProviderSetting(
                    name="openrouter",
                    label="OpenRouter (Multi-Model Gateway)",
                    enabled=True,
                    priority=1,
                    active_model=primary_active_model,
                    available_models=DEFAULT_MODELS["openrouter"],
                    has_api_key=has_openrouter,
                ),
                ProviderSetting(
                    name="anthropic",
                    label="Anthropic Claude API",
                    enabled=True,
                    priority=2,
                    active_model=primary_active_model,
                    available_models=anthropic_available,
                    has_api_key=has_anthropic,
                ),
                ProviderSetting(
                    name="groq",
                    label="Groq (Fast OpenAI-Compat, Free Models)",
                    enabled=True,
                    priority=3,
                    active_model="openai/gpt-oss-120b",
                    available_models=DEFAULT_MODELS["groq"],
                    has_api_key=has_groq,
                ),
                ProviderSetting(
                    name="openai",
                    label="OpenAI GPT API",
                    enabled=True,
                    priority=4,
                    active_model="openai/gpt-4o",
                    available_models=DEFAULT_MODELS["openai"],
                    has_api_key=has_openai,
                ),
                ProviderSetting(
                    name="deterministic_rules",
                    label="Deterministic Taxonomy Rule Fallback (Offline)",
                    enabled=True,
                    priority=5,
                    active_model="NPCI & Razorpay Rule Classifier",
                    available_models=DEFAULT_MODELS["deterministic_rules"],
                    has_api_key=True,
                ),
            ],
            timeout_seconds=30,
            temperature=0.2,
        )

    def _load_or_default(self) -> LLMSettingsState:
        default = self._default_state()
        if not self.file_path.exists():
            return default

        try:
            raw_text = self.file_path.read_text(encoding="utf-8")
            data: Any = json.loads(raw_text)
            state = LLMSettingsState.model_validate(data)
            settings = get_settings()
            key_map = {
                "openrouter": bool(
                    settings.openrouter_api_key
                    and settings.openrouter_api_key.get_secret_value().strip()
                ),
                "anthropic": bool(
                    settings.anthropic_api_key
                    and settings.anthropic_api_key.get_secret_value().strip()
                ),
                "openai": bool(
                    settings.openai_api_key
                    and settings.openai_api_key.get_secret_value().strip()
                ),
                "groq": bool(
                    settings.groq_api_key
                    and settings.groq_api_key.get_secret_value().strip()
                ),
                "deterministic_rules": True,
            }
            for p in state.providers:
                if p.name in key_map:
                    p.has_api_key = key_map[p.name]
                if p.name == "openrouter" and settings.openrouter_model:
                    clean_env_model = settings.openrouter_model.removeprefix(
                        "openrouter/"
                    )
                    if clean_env_model not in p.available_models:
                        p.available_models.insert(0, clean_env_model)
                    if settings.openrouter_model not in p.available_models:
                        p.available_models.insert(0, settings.openrouter_model)
                    p.active_model = clean_env_model
            existing_names = {provider.name for provider in state.providers}
            for provider in default.providers:
                if provider.name not in existing_names:
                    state.providers.append(provider)
            state.providers.sort(key=lambda provider: provider.priority)
            state.providers = [
                provider.model_copy(update={"priority": index})
                for index, provider in enumerate(state.providers, start=1)
            ]
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
            return state
        except Exception as exc:  # noqa: BLE001
            logger.warning("llm.settings_store.load_error", error=str(exc))
            return default

    def get_state(self) -> LLMSettingsState:
        """Return current provider settings state."""
        return self._state

    def update_state(self, new_state: LLMSettingsState) -> LLMSettingsState:
        """Update provider settings and persist to disk."""
        self._state = new_state
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.file_path.with_suffix(".tmp")
        tmp_path.write_text(self._state.model_dump_json(indent=2), encoding="utf-8")
        tmp_path.replace(self.file_path)
        logger.info(
            "llm.settings_store.persisted", providers_count=len(new_state.providers)
        )
        return self._state


@lru_cache(maxsize=1)
def get_llm_settings_store() -> LLMSettingsStore:
    """Return singleton LLM settings store."""
    return LLMSettingsStore()
