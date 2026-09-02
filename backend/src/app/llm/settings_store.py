"""Durable PostgreSQL-backed persistence for dynamic LLM provider settings and fallback priority."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import get_db_connection
from app.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_MODELS: dict[str, list[str]] = {
    "openrouter": [
        "meta-llama/llama-3.3-70b-instruct",
        "nvidia/nemotron-nano-9b-v2:free",
        "deepseek/deepseek-r1",
        "openai/gpt-4o",
    ],
    "anthropic": [
        "anthropic/claude-opus-5",
        "anthropic/claude-sonnet-5",
        "anthropic/claude-haiku-4-5",
    ],
    "openai": [
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
        "openai/o3-mini",
    ],
    "groq": [
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "groq/compound",
        "groq/compound-mini",
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
    """PostgreSQL-backed store for LLM provider preferences."""

    def __init__(self) -> None:
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
                    label="OpenRouter (Primary Frontier & Open-Weights Router)",
                    enabled=True,
                    priority=1,
                    active_model=primary_active_model.removeprefix("openrouter/"),
                    available_models=DEFAULT_MODELS["openrouter"],
                    has_api_key=has_openrouter,
                ),
                ProviderSetting(
                    name="groq",
                    label="Groq (Ultra-Low Latency Inference)",
                    enabled=True,
                    priority=2,
                    active_model=settings.agentic_model,
                    available_models=DEFAULT_MODELS["groq"],
                    has_api_key=has_groq,
                ),
                ProviderSetting(
                    name="anthropic",
                    label="Anthropic Claude Direct API",
                    enabled=True,
                    priority=3,
                    active_model=f"anthropic/{settings.anthropic_model}",
                    available_models=anthropic_available,
                    has_api_key=has_anthropic,
                ),
                ProviderSetting(
                    name="openai",
                    label="OpenAI Direct API",
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
        try:
            with get_db_connection() as conn:
                row = conn.execute(
                    text("SELECT settings_json FROM llm_settings WHERE id = 1")
                ).fetchone()
                if not row or not row[0]:
                    return default

                data: Any = row[0] if isinstance(row[0], dict) else json.loads(row[0])
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
                return state
        except Exception as exc:  # noqa: BLE001
            logger.warning("llm.settings_store.load_error", error=str(exc))
            return default

    def get_state(self) -> LLMSettingsState:
        """Return current provider settings state."""
        return self._state

    def update_state(self, new_state: LLMSettingsState) -> LLMSettingsState:
        """Update provider settings and persist to PostgreSQL."""
        self._state = new_state
        now = datetime.now(UTC)
        try:
            with get_db_connection() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO llm_settings (id, settings_json, updated_at)
                        VALUES (1, CAST(:settings_json AS jsonb), :updated_at)
                        ON CONFLICT (id) DO UPDATE SET
                            settings_json = EXCLUDED.settings_json,
                            updated_at = EXCLUDED.updated_at;
                        """
                    ),
                    {
                        "settings_json": json.dumps(new_state.model_dump(mode="json")),
                        "updated_at": now,
                    },
                )
            logger.info(
                "llm.settings_store.persisted",
                providers_count=len(new_state.providers),
            )
            return self._state
        except Exception as exc:
            logger.error("llm.settings_store.save_error", error=str(exc))
            raise


@lru_cache(maxsize=1)
def get_llm_settings_store() -> LLMSettingsStore:
    """Return singleton LLM settings store."""
    return LLMSettingsStore()
