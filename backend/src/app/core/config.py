"""Application configuration, read from the environment.

Never hardcode config values or read ``os.environ`` directly elsewhere - add a
field here instead, so every knob is discoverable in one place and validated at
startup rather than at first use.
"""

from functools import lru_cache
from typing import Annotated, Literal

from fastapi import Depends
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.constants import DEFAULT_AGENTIC_MODEL


class Settings(BaseSettings):
    """Environment-backed settings.

    Every variable is prefixed ``APP_`` (e.g. ``APP_LOG_LEVEL``), except the
    provider API keys, which keep their conventional names so the provider SDKs
    and the wider ecosystem pick them up unchanged.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="APP_",
        env_nested_delimiter="__",
        case_sensitive=False,
        # BaseSettings defaults to extra="forbid", which would make any unrelated
        # variable in .env a hard startup failure.
        extra="ignore",
    )

    env: Literal["local", "ci", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = Field(
        default=False,
        description="Emit JSON logs. Off locally for readability, on in deployment.",
    )

    cors_origins: list[str] = Field(
        default=["*"],
        description="Allowed browser origins for local development and network access.",
    )

    # LLM Providers (OpenRouter is primary; Anthropic and OpenAI optional)
    openrouter_api_key: SecretStr | None = Field(
        default=None, validation_alias="OPENROUTER_API_KEY"
    )
    openrouter_model: str = Field(
        default="openrouter/nvidia/nemotron-3.5-lightning:free",
        validation_alias="OPENROUTER_MODEL",
    )
    anthropic_api_key: SecretStr | None = Field(
        default=None, validation_alias="ANTHROPIC_API_KEY"
    )
    openai_api_key: SecretStr | None = Field(
        default=None, validation_alias="OPENAI_API_KEY"
    )
    groq_api_key: SecretStr | None = Field(
        default=None, validation_alias="GROQ_API_KEY"
    )
    agentic_model: str = Field(
        default=DEFAULT_AGENTIC_MODEL,
        validation_alias="APP_AGENTIC_MODEL",
        description="Model used for agentic recovery simulation and served as the "
        "Groq default. Single source of truth; consumers must not hardcode it.",
    )

    # Razorpay Gateway & Webhook Credentials
    razorpay_key_id: str | None = Field(
        default=None, validation_alias="RAZORPAY_KEY_ID"
    )
    razorpay_key_secret: SecretStr | None = Field(
        default=None, validation_alias="RAZORPAY_KEY_SECRET"
    )
    razorpay_webhook_secret: SecretStr | None = Field(
        default=None, validation_alias="RAZORPAY_WEBHOOK_SECRET"
    )
    # Partner/OAuth access token and target account id for fetching the linked
    # merchant account profile via GET /v2/accounts/:account_id. Requires a
    # real RazorpayX/partner token; absent in test mode the fetch is skipped.
    razorpay_access_token: SecretStr | None = Field(
        default=None, validation_alias="RAZORPAY_ACCESS_TOKEN"
    )
    razorpay_account_id: str | None = Field(
        default=None, validation_alias="RAZORPAY_ACCOUNT_ID"
    )

    # Customer Outreach & Notification Webhook
    notification_webhook_url: str | None = Field(
        default=None, validation_alias="NOTIFICATION_WEBHOOK_URL"
    )
    whatsapp_api_token: SecretStr | None = Field(
        default=None, validation_alias="WHATSAPP_API_TOKEN"
    )

    # PostgreSQL ACID persistence datasource
    database_url: str = Field(
        default="postgresql://postgres:postgres@127.0.0.1:5432/fortx",
        validation_alias="DATABASE_URL",
        description="PostgreSQL DSN for the shared relational store.",
    )
    postgres_pool_size: int = Field(
        default=10,
        validation_alias="POSTGRES_POOL_SIZE",
        description="Maximum persistent connections in the engine pool.",
    )
    postgres_max_overflow: int = Field(
        default=20,
        validation_alias="POSTGRES_MAX_OVERFLOW",
        description="Maximum temporary connections beyond pool_size.",
    )
    postgres_pool_timeout_seconds: float = Field(
        default=30.0,
        validation_alias="POSTGRES_POOL_TIMEOUT_SECONDS",
        description="Seconds to wait before raising a pool timeout error.",
    )
    postgres_statement_timeout_ms: int = Field(
        default=30000,
        validation_alias="POSTGRES_STATEMENT_TIMEOUT_MS",
        description="Statement execution timeout in milliseconds.",
    )

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, constructed once."""
    return Settings()


SettingsDep = Annotated[Settings, Depends(get_settings)]
"""Inject settings into a route: ``def handler(settings: SettingsDep) -> ...``."""
