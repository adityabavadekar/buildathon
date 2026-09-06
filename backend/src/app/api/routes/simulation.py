"""Simulation harness and system status inspection API."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.audit.repository import get_case_repository
from app.core.cache import cached_json_value, flush_all
from app.core.config import get_settings
from app.core.enums import RecoveryState
from app.core.operator import OperatorMode, get_operator_mode
from app.intervention.orchestrator import get_recovery_orchestrator
from app.llm.client import configured_providers
from app.llm.settings_store import MANDATORY_PROVIDER_NAME, get_llm_settings_store
from app.simulation.seeder import reset_simulation_data

router = APIRouter(prefix="/simulation", tags=["simulation"])

_PROCESS_START_TIME = time.time()


class ResolveCaseRequest(BaseModel):
    """Simulate customer payment resolution."""

    case_id: str
    amount_paise: int | None = None


class LLMEngineStatus(BaseModel):
    """LLM reasoning engine status. active_model is None, not a placeholder
    string, when no real provider is configured -- deterministic_fallback_active
    is the field the UI must branch on for that case.
    """

    configured_providers: list[str]
    active_provider: str | None
    active_model: str | None
    deterministic_fallback_active: bool
    circuit_breaker: str
    operator_mode: str | None = None
    offline_fallback_operational: bool


class SystemStatusResponse(BaseModel):
    """Detailed operational health and telemetry status for the system status page."""

    system_status: str
    uptime_seconds: int
    environment: str
    database_cases_count: int
    active_recovery_queue: int
    escalated_queue_count: int
    gateway_integration: dict[str, Any]
    llm_engine: LLMEngineStatus
    policy_enforcement: dict[str, Any]
    timestamp: datetime


@router.post("/reset", summary="Reset Simulation Data")
async def reset_simulation() -> dict[str, str]:
    """Reset repository and purge test simulation state."""
    result = reset_simulation_data()
    await flush_all()
    return result


@router.post("/resolve-case", summary="Simulate Case Resolution")
async def simulate_resolve_case(req: ResolveCaseRequest) -> dict[str, Any]:
    """Simulate a customer completing payment for an at-risk transaction."""
    repo = get_case_repository()
    case = repo.get_by_id(req.case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if case.state == RecoveryState.RECOVERED:
        return {
            "status": "already_resolved",
            "case_id": case.case_id,
            "state": case.state.value,
            "recovered_amount_paise": case.recovered_amount_paise,
            "net_recovered_value_paise": case.net_recovered_value_paise,
        }

    amount = req.amount_paise or (case.amount_paise - case.discount_paise_granted)
    orchestrator = get_recovery_orchestrator()
    updated = orchestrator.process_payment_captured(
        payment_id=case.failure_event.payment_id,
        amount_paise=amount,
        gateway_capture_id=f"sim_cap_{int(time.time())}",
    )
    if not updated:
        raise HTTPException(status_code=400, detail="Failed to resolve case")

    return {
        "status": "resolved",
        "case_id": updated.case_id,
        "state": updated.state.value,
        "recovered_amount_paise": updated.recovered_amount_paise,
        "net_recovered_value_paise": updated.net_recovered_value_paise,
    }


@router.get(
    "/status", response_model=SystemStatusResponse, summary="Get Full System Status"
)
async def get_system_status() -> SystemStatusResponse:
    """Retrieve comprehensive system telemetry, gateway health, and active queues."""
    settings = get_settings()
    uptime = int(time.time() - _PROCESS_START_TIME)

    async def _compute_queue_counts() -> dict[str, int]:
        repo = get_case_repository()
        cases = list(repo.list_cases(limit=10000))
        return {
            "total_cases": len(cases),
            "active_queue": sum(
                1
                for c in cases
                if c.state.value
                in ("IN_DUNNING", "OUTREACH_PENDING", "RETRY_SCHEDULED")
            ),
            "escalated_queue": sum(1 for c in cases if c.state.value == "ESCALATED"),
        }

    # Only the case-count scan is cached -- live config/mode/provider state
    # must reflect an operator's change immediately, not after a TTL.
    queue_counts_raw = await cached_json_value(
        "system:status:queue_counts:v1",
        settings.analytics_cache_ttl_seconds,
        _compute_queue_counts,
    )
    queue_counts = cast("dict[str, int]", queue_counts_raw)
    total_cases = queue_counts["total_cases"]
    active_queue = queue_counts["active_queue"]
    escalated_queue = queue_counts["escalated_queue"]

    providers = configured_providers()
    rzp_configured = bool(settings.razorpay_key_id and settings.razorpay_key_secret)
    operator_mode = get_operator_mode()
    orchestrator = get_recovery_orchestrator()
    policy = orchestrator.policy

    store_state = get_llm_settings_store().get_state()
    # deterministic_rules is a fallback state, not a model: excluded here so an
    # unconfigured LLM resolves to None instead of its placeholder model name.
    active_provider_obj = next(
        (
            p
            for p in sorted(store_state.providers, key=lambda x: x.priority)
            if p.enabled and p.has_api_key and p.name != MANDATORY_PROVIDER_NAME
        ),
        None,
    )

    return SystemStatusResponse(
        system_status="OPERATIONAL"
        if operator_mode != OperatorMode.MONITORING_ONLY
        else "HELD",
        uptime_seconds=uptime,
        environment=settings.env,
        database_cases_count=total_cases,
        active_recovery_queue=active_queue,
        escalated_queue_count=escalated_queue,
        gateway_integration={
            "provider": "Razorpay",
            "mode": "TEST"
            if settings.razorpay_key_id and "test" in settings.razorpay_key_id
            else "PROD",
            "authenticated": rzp_configured,
            "key_id": settings.razorpay_key_id,
            "webhook_endpoint": "/api/webhooks/razorpay",
            "supported_rails": ["UPI", "MANDATES", "CARDS", "NETBANKING", "INVOICES"],
        },
        llm_engine=LLMEngineStatus(
            configured_providers=providers,
            active_provider=active_provider_obj.name if active_provider_obj else None,
            active_model=active_provider_obj.active_model
            if active_provider_obj
            else None,
            deterministic_fallback_active=active_provider_obj is None,
            circuit_breaker="ACTIVE"
            if operator_mode == OperatorMode.MONITORING_ONLY
            else "INACTIVE",
            operator_mode=operator_mode.value,
            offline_fallback_operational=True,
        ),
        policy_enforcement={
            "guardrail_status": "ACTIVE",
            "max_attempts_cap": policy.max_attempts,
            "cooldown_hours": policy.min_cooldown_hours,
            "discount_cap_bps": policy.max_discount_bps,
            "holdout_ratio_pct": policy.holdout_percentage,
        },
        timestamp=datetime.now(UTC),
    )
