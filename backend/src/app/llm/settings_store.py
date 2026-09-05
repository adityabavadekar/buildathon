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

# The rule-based classifier is the mandatory fallback the whole system rests
# on when no real LLM provider is configured or available -- client.py
# excludes it from active_providers by this exact name regardless of its
# enabled flag, so it always runs. enabled must therefore never persist as
# False for this provider, or the Settings UI would show a compliance-facing
# control as "Disabled" while the classifier it names keeps running unchanged.
MANDATORY_PROVIDER_NAME = "deterministic_rules"


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
        openrouter_active_stripped = primary_active_model.removeprefix("openrouter/")
        # The .env-configured model may not be one of the curated defaults --
        # an active_model absent from available_models renders as unselected
        # in the operator UI even though the backend state is correct.
        openrouter_available = (
            [openrouter_active_stripped, *DEFAULT_MODELS["openrouter"]]
            if openrouter_active_stripped not in DEFAULT_MODELS["openrouter"]
            else DEFAULT_MODELS["openrouter"]
        )
        anthropic_configured = f"anthropic/{settings.anthropic_model}"
        anthropic_available = (
            [anthropic_configured, *DEFAULT_MODELS["anthropic"]]
            if anthropic_configured not in DEFAULT_MODELS["anthropic"]
            else DEFAULT_MODELS["anthropic"]
        )
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
                    label="OpenRouter",
                    enabled=True,
                    priority=1,
                    active_model=openrouter_active_stripped,
                    available_models=openrouter_available,
                    has_api_key=has_openrouter,
                ),
                ProviderSetting(
                    name="groq",
                    label="Groq",
                    enabled=True,
                    priority=2,
                    active_model=settings.agentic_model,
                    available_models=DEFAULT_MODELS["groq"],
                    has_api_key=has_groq,
                ),
                ProviderSetting(
                    name="anthropic",
                    label="Anthropic",
                    enabled=True,
                    priority=3,
                    active_model=f"anthropic/{settings.anthropic_model}",
                    available_models=anthropic_available,
                    has_api_key=has_anthropic,
                ),
                ProviderSetting(
                    name="openai",
                    label="OpenAI",
                    enabled=True,
                    priority=4,
                    active_model="openai/gpt-4o",
                    available_models=DEFAULT_MODELS["openai"],
                    has_api_key=has_openai,
                ),
                ProviderSetting(
                    name=MANDATORY_PROVIDER_NAME,
                    label="Deterministic Taxonomy Rule Fallback",
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
                # A row persisted before an operator's active_model change (or
                # from an older server build) must not clobber that choice on
                # every restart -- only ensure it stays selectable, never force
                # it. See docs/DECISIONS.md 2026-08-31 for the outage this
                # class of bug already caused once via a stale persisted model.
                default_by_name = {p.name: p for p in default.providers}
                for p in state.providers:
                    if p.name in key_map:
                        p.has_api_key = key_map[p.name]
                    if p.active_model not in p.available_models:
                        p.available_models.insert(0, p.active_model)
                    fallback = default_by_name.get(p.name)
                    if fallback and fallback.active_model not in p.available_models:
                        p.available_models.insert(0, fallback.active_model)
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
        """Update provider settings and persist to PostgreSQL.

        The mandatory rule-classifier provider is forced back to enabled
        regardless of what the caller sent -- it always runs (see
        MANDATORY_PROVIDER_NAME), so persisting it as disabled would let an
        operator believe they turned off something they cannot turn off.
        """
        for provider in new_state.providers:
            if provider.name == MANDATORY_PROVIDER_NAME:
                provider.enabled = True

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
