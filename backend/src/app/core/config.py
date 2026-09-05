"""Application configuration. Never read os.environ elsewhere: add a field here so
every knob is discoverable in one place and validated at startup.
"""

from functools import lru_cache
from typing import Annotated, Literal

from fastapi import Depends
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.constants import DEFAULT_AGENTIC_MODEL, DEFAULT_ANTHROPIC_MODEL


class Settings(BaseSettings):
    """Environment-backed settings, all APP_-prefixed except provider API keys,
    which keep conventional names so the SDKs pick them up unchanged.
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
        default="openrouter/meta-llama/llama-3.3-70b-instruct",
        validation_alias="OPENROUTER_MODEL",
    )
    anthropic_api_key: SecretStr | None = Field(
        default=None, validation_alias="ANTHROPIC_API_KEY"
    )
    anthropic_model: str = Field(
        default=DEFAULT_ANTHROPIC_MODEL,
        validation_alias="ANTHROPIC_MODEL",
    )
    openai_api_key: SecretStr | None = Field(
        default=None, validation_alias="OPENAI_API_KEY"
    )
    groq_api_key: SecretStr | None = Field(
        default=None, validation_alias="GROQ_API_KEY"
    )
    fleet_time_compression: int = Field(
        default=1,
        ge=1,
        le=3600,
        validation_alias="APP_FLEET_TIME_COMPRESSION",
        description="Divides intervention delays for fleet-generated cases so a "
        "demo run shows the queue draining. Production delays (a 4h bank "
        "cutoff, a 48h salary cycle) are correct but leave nothing due for "
        "hours, making the worker look stalled. 1 disables compression.",
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
    # Fetches the linked merchant profile via GET /v2/accounts/:account_id.
    # Needs a real partner token; the fetch is skipped in test mode.
    razorpay_access_token: SecretStr | None = Field(
        default=None, validation_alias="RAZORPAY_ACCESS_TOKEN"
    )
    razorpay_account_id: str | None = Field(
        default=None, validation_alias="RAZORPAY_ACCOUNT_ID"
    )

    # Issued when registering an app on the Partner Dashboard; the redirect URI
    # must be whitelisted there or the authorize call is rejected.
    razorpay_oauth_client_id: str | None = Field(
        default=None, validation_alias="RAZORPAY_OAUTH_CLIENT_ID"
    )
    razorpay_oauth_client_secret: SecretStr | None = Field(
        default=None, validation_alias="RAZORPAY_OAUTH_CLIENT_SECRET"
    )
    razorpay_oauth_mode: str = Field(
        default="test",
        validation_alias="RAZORPAY_OAUTH_MODE",
        description="test or live. Production partner clients are restricted to "
        "live by Razorpay.",
    )
    # Where the OAuth callback sends the operator back to. The callback lands on
    # the backend (the frontend has no route files), so it needs the UI's origin.
    app_public_base_url: str = Field(
        default="http://127.0.0.1:5173",
        validation_alias="APP_PUBLIC_BASE_URL",
        description="Public origin of the dashboard, used to redirect after the "
        "OAuth callback.",
    )

    # Operator authentication. Unset password disables the gate entirely, which is
    # what keeps local development and the test suite working.
    operator_password: SecretStr | None = Field(
        default=None, validation_alias="APP_OPERATOR_PASSWORD"
    )
    session_secret: SecretStr | None = Field(
        default=None,
        validation_alias="APP_SESSION_SECRET",
        description="HMAC key for session cookies. A random per-process key is "
        "generated when unset, which logs every operator out on restart.",
    )
    session_ttl_hours: int = Field(
        default=12, ge=1, le=720, validation_alias="APP_SESSION_TTL_HOURS"
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
