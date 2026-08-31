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
        default=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://192.168.1.4:5173",
            "http://192.168.1.4:3000",
        ],
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

    # Customer Outreach & Notification Webhook
    notification_webhook_url: str | None = Field(
        default=None, validation_alias="NOTIFICATION_WEBHOOK_URL"
    )
    whatsapp_api_token: SecretStr | None = Field(
        default=None, validation_alias="WHATSAPP_API_TOKEN"
    )

    # Durable merchant policy store
    policy_config_path: str = Field(
        default="data/policy_config.json",
        description="File path for the persisted active MerchantPolicy.",
    )

    # ACID case storage database
    database_path: str = Field(
        default="data/recovery_engine.db",
        description="File path for the relational case engine database.",
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
