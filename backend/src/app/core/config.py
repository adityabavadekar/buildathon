"""Application configuration, read from the environment.

Never hardcode config values or read ``os.environ`` directly elsewhere — add a
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

    # -- Service ------------------------------------------------------------
    env: Literal["local", "ci", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = Field(
        default=False,
        description="Emit JSON logs. Off locally for readability, on in deployment.",
    )

    # -- CORS ---------------------------------------------------------------
    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        description="Allowed browser origins. The defaults are the Vite dev server.",
    )

    # -- LLM providers ------------------------------------------------------
    # These deliberately keep their conventional names rather than taking the
    # APP_ prefix, so provider SDKs and other tooling find them unchanged.
    anthropic_api_key: SecretStr | None = Field(
        default=None, validation_alias="ANTHROPIC_API_KEY"
    )
    openai_api_key: SecretStr | None = Field(
        default=None, validation_alias="OPENAI_API_KEY"
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
