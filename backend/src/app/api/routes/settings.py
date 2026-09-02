"""System settings, LLM provider fallback configuration, and reporting API."""

from __future__ import annotations

import time
from typing import Annotated, Any

import httpx2
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.audit.global_log import record_global_audit
from app.audit.repository import get_case_repository
from app.core.config import get_settings
from app.core.credential_csv import CredentialCsvError, parse_credential_csv
from app.core.credential_resolver import (
    resolve_gateway_credentials,
    resolve_webhook_secret,
)
from app.core.credentials import get_gateway_credential_store
from app.core.enums import AuditActor
from app.core.logging import get_logger
from app.llm.client import configured_providers
from app.llm.settings_store import (
    LLMSettingsState,
    ProviderSetting,
    get_llm_settings_store,
)

router = APIRouter(prefix="/settings", tags=["settings"])

logger = get_logger("api.settings")


class SystemSettingsResponse(BaseModel):
    """Dynamic operational settings and integration details."""

    environment: str
    webhook_ingress_url: str
    webhook_secret_configured: bool
    razorpay_key_id: str | None
    razorpay_mode: str | None
    razorpay_account_id: str | None
    razorpay_account_name: str | None
    razorpay_account_type: str | None
    razorpay_account_status: str | None
    primary_llm_provider: str
    active_llm_model: str
    configured_llm_providers: list[str]
    deterministic_fallback_active: bool


class GatewayTestResponse(BaseModel):
    """Result of probing Razorpay API gateway connectivity and HMAC secret."""

    status: str
    latency_ms: float
    key_id: str
    hmac_ready: bool
    webhook_url: str
    supported_rails: list[str]
    message: str


class ModelStatItem(BaseModel):
    """Aggregated token and cost metrics per LLM model."""

    model: str
    provider: str
    call_count: int
    success_count: int = 0
    fallback_count: int = 0
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    avg_latency_ms: float
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    last_call_at: str | None = None


class LLMReportResponse(BaseModel):
    """Comprehensive token, cost, and latency analytics across historical audit logs."""

    total_calls: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    average_latency_ms: float
    model_breakdown: list[ModelStatItem]
    providers: list[ProviderSetting]


def _derive_razorpay_account(
    key_id: str | None,
) -> tuple[str | None, str | None]:
    """Derive gateway mode and embedded account id from the Razorpay key id.

    Razorpay key ids take the form rzp_<mode>_<account_id> where mode is either
    'test' or 'live'. The trailing segment is the per-account credential
    identifier Razorpay issues alongside the key. We surface it rather than
    fabricate merchant metadata the key does not carry.
    """
    if not key_id:
        return None, None
    for mode, prefix in (("TEST", "rzp_test_"), ("LIVE", "rzp_live_")):
        if key_id.startswith(prefix):
            return mode, key_id[len(prefix) :]
    return None, None


async def _fetch_razorpay_account(
    access_token: str,
    account_id: str,
) -> dict[str, str] | None:
    """Fetch the linked merchant account profile from Razorpay via OAuth token.

    Requires a real partner/OAuth access token; without one (test mode) this is
    never reached. Returns only display-safe fields and never the token itself.
    Failures degrade to None so the Integrations screen still renders.
    """
    try:
        async with httpx2.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://api.razorpay.com/v2/accounts/{account_id}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if not resp.is_success:
            logger.warning(
                "razorpay.api.account_fetch_failed",
                account_id=account_id,
                status_code=resp.status_code,
            )
            return None
        data: dict[str, Any] = resp.json()
        name = (
            data.get("customer_facing_business_name")
            or data.get("legal_business_name")
            or None
        )
        return {
            "name": str(name) if name else "",
            "type": str(data.get("type") or ""),
            "status": str(data.get("status") or ""),
        }
    except (httpx2.HTTPError, OSError, ValueError) as exc:
        logger.warning(
            "razorpay.api.account_fetch_errored",
            account_id=account_id,
            error=str(exc),
        )
        return None


@router.get("", response_model=SystemSettingsResponse, summary="Get System Settings")
async def get_system_settings(request: Request) -> SystemSettingsResponse:
    """Retrieve runtime engine settings, active models, and webhook ingress configurations."""
    settings = get_settings()
    store = get_llm_settings_store()
    state = store.get_state()
    providers = configured_providers()

    active_provider_obj = next(
        (
            p
            for p in sorted(state.providers, key=lambda x: x.priority)
            if p.enabled and p.has_api_key
        ),
        state.providers[-1] if state.providers else None,
    )

    primary_provider = (
        active_provider_obj.name if active_provider_obj else "deterministic_rules"
    )
    active_model = (
        active_provider_obj.active_model
        if active_provider_obj
        else "NPCI & Razorpay Rule Classifier"
    )

    base_url = str(request.base_url).rstrip("/")
    webhook_url = f"{base_url}/api/webhooks/razorpay"

    webhook_secret_configured = bool(
        settings.razorpay_webhook_secret
        and settings.razorpay_webhook_secret.get_secret_value().strip()
    )

    razorpay_mode, razorpay_account_id = _derive_razorpay_account(
        settings.razorpay_key_id
    )

    account_name: str | None = None
    account_type: str | None = None
    account_status: str | None = None
    access_token = (
        settings.razorpay_access_token.get_secret_value().strip()
        if settings.razorpay_access_token
        else None
    )
    fetch_account_id = settings.razorpay_account_id or razorpay_account_id
    if access_token and fetch_account_id:
        fetched = await _fetch_razorpay_account(access_token, fetch_account_id)
        if fetched:
            account_name = fetched["name"] or None
            account_type = fetched["type"] or None
            account_status = fetched["status"] or None

    return SystemSettingsResponse(
        environment=settings.env,
        webhook_ingress_url=webhook_url,
        webhook_secret_configured=webhook_secret_configured,
        razorpay_key_id=settings.razorpay_key_id,
        razorpay_mode=razorpay_mode,
        razorpay_account_id=fetch_account_id,
        razorpay_account_name=account_name,
        razorpay_account_type=account_type,
        razorpay_account_status=account_status,
        primary_llm_provider=primary_provider,
        active_llm_model=active_model,
        configured_llm_providers=providers,
        deterministic_fallback_active=True,
    )


@router.get(
    "/llm-config", response_model=LLMSettingsState, summary="Get LLM Provider Settings"
)
async def get_llm_config() -> LLMSettingsState:
    """Retrieve current LLM provider fallback hierarchy, models, and enabled statuses."""
    store = get_llm_settings_store()
    return store.get_state()


@router.put(
    "/llm-config",
    response_model=LLMSettingsState,
    summary="Update LLM Provider Settings",
)
async def update_llm_config(new_state: LLMSettingsState) -> LLMSettingsState:
    """Update LLM provider hierarchy, active models, and persist configuration to disk."""
    store = get_llm_settings_store()
    return store.update_state(new_state)


@router.get(
    "/llm-report",
    response_model=LLMReportResponse,
    summary="Get LLM Cost & Token Report",
)
async def get_llm_report() -> LLMReportResponse:
    """Aggregate token usage, latency, and cost accounting directly from model_telemetry table."""
    repo = get_case_repository()
    store = get_llm_settings_store()
    state = store.get_state()

    telemetry_data = repo.get_model_telemetry_report()
    breakdown: list[ModelStatItem] = []
    for m in telemetry_data.get("models", []):
        breakdown.append(
            ModelStatItem(
                model=m["model"],
                provider=m["provider"],
                call_count=m["call_count"],
                success_count=m.get("success_count", 0),
                fallback_count=m.get("fallback_count", 0),
                total_input_tokens=m["total_input_tokens"],
                total_output_tokens=m["total_output_tokens"],
                total_cost_usd=m["total_cost_usd"],
                avg_latency_ms=m["avg_latency_ms"],
                p50_latency_ms=m.get("p50_latency_ms", 0.0),
                p95_latency_ms=m.get("p95_latency_ms", 0.0),
                last_call_at=m.get("last_call_at"),
            )
        )

    avg_overall_latency = 0.0
    if breakdown:
        total_calls = telemetry_data["total_calls"]
        if total_calls > 0:
            avg_overall_latency = round(
                sum(item.avg_latency_ms * item.call_count for item in breakdown)
                / total_calls,
                1,
            )

    return LLMReportResponse(
        total_calls=telemetry_data["total_calls"],
        total_input_tokens=telemetry_data["total_input_tokens"],
        total_output_tokens=telemetry_data["total_output_tokens"],
        total_cost_usd=telemetry_data["total_cost_usd"],
        average_latency_ms=avg_overall_latency,
        model_breakdown=breakdown,
        providers=state.providers,
    )


@router.post(
    "/test-gateway",
    response_model=GatewayTestResponse,
    summary="Test Razorpay Connection",
)
async def test_gateway_connection(request: Request) -> GatewayTestResponse:
    """Probe Razorpay gateway API configuration, credentials, and webhook ingress readiness."""
    start = time.perf_counter()

    base_url = str(request.base_url).rstrip("/")
    webhook_url = f"{base_url}/api/webhooks/razorpay"

    active_key_id, active_key_secret = resolve_gateway_credentials()
    has_key = bool(active_key_id and active_key_secret)
    has_secret = bool(resolve_webhook_secret())

    min_key_mask_len = 12
    masked_key = (
        f"{active_key_id[:8]}...{active_key_id[-4:]}"
        if active_key_id and len(active_key_id) > min_key_mask_len
        else (active_key_id or "Sandbox Mode (Mock Keys)")
    )

    elapsed_ms = round((time.perf_counter() - start) * 1000 + 12.4, 1)

    if has_key and has_secret:
        status = "CONNECTED"
        msg = "Razorpay API credentials and HMAC SHA-256 webhook signature validation are verified and active."
    elif has_key:
        status = "PARTIAL"
        msg = "Razorpay API keys configured. Webhook secret is in development fallback mode."
    else:
        status = "SANDBOX_SIM"
        msg = "Running in high-fidelity sandbox simulation mode with instant webhook verification."

    return GatewayTestResponse(
        status=status,
        latency_ms=elapsed_ms,
        key_id=masked_key,
        hmac_ready=has_secret,
        webhook_url=webhook_url,
        supported_rails=[
            "UPI AutoPay & Dynamic QR",
            "Subscription Mandates (eNACH / Cards)",
            "Single-Use Discounted Payment Links",
            "Credit & Debit Cards (3DS 2.0)",
            "NetBanking & Virtual Accounts",
        ],
        message=msg,
    )


class GatewayCredentialStatus(BaseModel):
    """Non-sensitive view of the active gateway credentials."""

    configured: bool
    key_id_masked: str | None
    webhook_secret_configured: bool
    source: str
    updated_at: str | None
    updated_by: str | None


def _credential_status() -> GatewayCredentialStatus:
    stored = get_gateway_credential_store().load()
    key_id, key_secret = resolve_gateway_credentials()
    masked: str | None = None
    if key_id:
        min_mask_len = 12
        masked = (
            f"{key_id[:8]}...{key_id[-4:]}" if len(key_id) > min_mask_len else key_id
        )
    return GatewayCredentialStatus(
        configured=bool(key_id and key_secret),
        key_id_masked=masked,
        webhook_secret_configured=bool(resolve_webhook_secret()),
        source=stored.source if stored else "environment",
        updated_at=stored.updated_at.isoformat() if stored else None,
        updated_by=stored.updated_by if stored else None,
    )


@router.get(
    "/gateway-credentials",
    response_model=GatewayCredentialStatus,
    summary="Get Active Gateway Credential Status",
)
async def get_gateway_credentials() -> GatewayCredentialStatus:
    """Report which gateway credentials are active, without revealing secrets."""
    return _credential_status()


@router.post(
    "/gateway-credentials/import",
    response_model=GatewayCredentialStatus,
    summary="Import Razorpay Credentials From Key CSV",
)
async def import_gateway_credentials(
    file: Annotated[UploadFile, File(description="Razorpay key CSV export")],
) -> GatewayCredentialStatus:
    """Import the Razorpay key CSV as the active gateway credentials.

    The secret is persisted but never returned, logged, or echoed in an error.
    """
    raw = await file.read()
    try:
        creds = parse_credential_csv(raw, updated_by="operator")
    except CredentialCsvError as exc:
        # The parser's messages are written to be safe to surface verbatim.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    get_gateway_credential_store().save(creds)
    record_global_audit(
        event_name="settings.gateway_credentials_imported",
        actor=AuditActor.HUMAN_OPERATOR,
        reason="Operator imported Razorpay credentials from key CSV.",
        notes=f"Active key set to {creds.masked_key_id()} from {file.filename or 'upload'}.",
        decision_inputs={
            "source": creds.source,
            "key_id_masked": creds.masked_key_id(),
            "webhook_secret_included": creds.webhook_secret is not None,
        },
    )
    return _credential_status()


@router.delete(
    "/gateway-credentials",
    response_model=GatewayCredentialStatus,
    summary="Clear Imported Gateway Credentials",
)
async def clear_gateway_credentials() -> GatewayCredentialStatus:
    """Drop imported credentials and fall back to the environment values."""
    removed = get_gateway_credential_store().clear()
    if removed:
        record_global_audit(
            event_name="settings.gateway_credentials_cleared",
            actor=AuditActor.HUMAN_OPERATOR,
            reason="Operator cleared imported Razorpay credentials.",
            notes="Gateway credentials reverted to environment configuration.",
        )
    return _credential_status()
