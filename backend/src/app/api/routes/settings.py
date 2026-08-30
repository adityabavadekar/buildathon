"""System settings and integration configuration inspection API."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.config import get_settings
from app.llm.client import configured_providers

router = APIRouter(prefix="/settings", tags=["settings"])


class SystemSettingsResponse(BaseModel):
    """Dynamic operational settings and integration details."""

    environment: str
    webhook_ingress_url: str
    webhook_secret_configured: bool
    razorpay_key_id: str | None
    primary_llm_provider: str
    active_llm_model: str
    configured_llm_providers: list[str]
    deterministic_fallback_active: bool


@router.get("", response_model=SystemSettingsResponse, summary="Get System Settings")
async def get_system_settings(request: Request) -> SystemSettingsResponse:
    """Retrieve runtime engine settings, active models, and webhook ingress configurations."""
    settings = get_settings()
    providers = configured_providers()

    if "openrouter" in providers:
        primary_provider = "openrouter"
        active_model = settings.openrouter_model
    elif "anthropic" in providers:
        primary_provider = "anthropic"
        active_model = "anthropic/claude-sonnet-5"
    elif "openai" in providers:
        primary_provider = "openai"
        active_model = "openai/gpt-4o"
    else:
        primary_provider = "deterministic_offline_taxonomy"
        active_model = "NPCI & Razorpay Rule Classifier"

    base_url = str(request.base_url).rstrip("/")
    webhook_url = f"{base_url}/api/webhooks/razorpay"

    webhook_secret_configured = bool(
        settings.razorpay_webhook_secret
        and settings.razorpay_webhook_secret.get_secret_value().strip()
    )

    return SystemSettingsResponse(
        environment=settings.env,
        webhook_ingress_url=webhook_url,
        webhook_secret_configured=webhook_secret_configured,
        razorpay_key_id=settings.razorpay_key_id,
        primary_llm_provider=primary_provider,
        active_llm_model=active_model,
        configured_llm_providers=providers,
        deterministic_fallback_active=True,
    )
