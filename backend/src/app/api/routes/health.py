"""Liveness and capability reporting."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import __version__
from app.core.config import SettingsDep
from app.llm.client import configured_providers

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Service liveness and what it is currently able to do."""

    status: Literal["ok"] = "ok"
    version: str = Field(description="Backend package version.")
    env: str = Field(description="Which environment this process thinks it is in.")
    llm_providers: list[str] = Field(
        description="Providers with an API key configured. Names only, never values."
    )


@router.get("/health", summary="Liveness check")
async def health(settings: SettingsDep) -> HealthResponse:
    """Report that the service is up, and which LLM providers are configured."""
    return HealthResponse(
        version=__version__,
        env=settings.env,
        llm_providers=configured_providers(),
    )
