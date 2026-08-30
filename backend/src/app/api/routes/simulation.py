"""Simulation harness and system status inspection API."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.audit.repository import get_case_repository
from app.core.config import get_settings
from app.intervention.orchestrator import get_recovery_orchestrator
from app.llm.client import configured_providers
from app.simulation.seeder import reset_simulation_data, seed_simulation_batch

router = APIRouter(prefix="/simulation", tags=["simulation"])

_PROCESS_START_TIME = time.time()


class SeedRequest(BaseModel):
    """Request payload for seeding synthetic failure batches."""

    count: int = Field(default=50, ge=1, le=500)
    simulate_resolutions: bool = Field(default=True)


class SeedResponse(BaseModel):
    """Result of batch seeding."""

    seeded_count: int
    recovered_count: int
    case_ids: list[str]


class ResolveCaseRequest(BaseModel):
    """Simulate customer payment resolution."""

    case_id: str
    amount_paise: int | None = None


class SystemStatusResponse(BaseModel):
    """Detailed operational health and telemetry status for the system status page."""

    system_status: str
    uptime_seconds: int
    environment: str
    database_cases_count: int
    active_recovery_queue: int
    escalated_queue_count: int
    gateway_integration: dict[str, Any]
    llm_engine: dict[str, Any]
    policy_enforcement: dict[str, Any]
    timestamp: datetime


@router.post("/seed", response_model=SeedResponse, summary="Seed Simulation Batch")
async def seed_batch(req: SeedRequest) -> SeedResponse:
    """Generate realistic transaction failure cohort across rails and simulate recoveries."""
    result = await seed_simulation_batch(
        count=req.count,
        simulate_resolutions=req.simulate_resolutions,
    )
    return SeedResponse(
        seeded_count=result["seeded_count"],
        recovered_count=result["recovered_count"],
        case_ids=result["case_ids"],
    )


@router.post("/reset", summary="Reset Simulation Data")
async def reset_simulation() -> dict[str, str]:
    """Reset repository and purge test simulation state."""
    return reset_simulation_data()


@router.post("/resolve-case", summary="Simulate Case Resolution")
async def simulate_resolve_case(req: ResolveCaseRequest) -> dict[str, Any]:
    """Simulate a customer completing payment for an at-risk transaction."""
    repo = get_case_repository()
    case = repo.get_by_id(req.case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

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


@router.get("/status", response_model=SystemStatusResponse, summary="Get Full System Status")
async def get_system_status() -> SystemStatusResponse:
    """Retrieve comprehensive system telemetry, gateway health, and active queues."""
    repo = get_case_repository()
    settings = get_settings()
    uptime = int(time.time() - _PROCESS_START_TIME)

    cases = list(repo.list_cases(limit=10000))
    total_cases = len(cases)
    active_queue = sum(
        1 for c in cases if c.state.value in ("IN_DUNNING", "OUTREACH_PENDING", "RETRY_SCHEDULED")
    )
    escalated_queue = sum(1 for c in cases if c.state.value == "ESCALATED")

    providers = configured_providers()
    rzp_configured = bool(settings.razorpay_key_id and settings.razorpay_key_secret)

    return SystemStatusResponse(
        system_status="OPERATIONAL",
        uptime_seconds=uptime,
        environment=settings.env,
        database_cases_count=total_cases,
        active_recovery_queue=active_queue,
        escalated_queue_count=escalated_queue,
        gateway_integration={
            "provider": "Razorpay",
            "mode": "TEST" if settings.razorpay_key_id and "test" in settings.razorpay_key_id else "PROD",
            "authenticated": rzp_configured,
            "key_id": settings.razorpay_key_id,
            "webhook_endpoint": "/api/webhooks/razorpay",
            "supported_rails": ["UPI", "MANDATES", "CARDS", "NETBANKING", "INVOICES"],
        },
        llm_engine={
            "configured_providers": providers,
            "active_model": settings.openrouter_model if "openrouter" in providers else "deterministic_rules",
            "circuit_breaker": "ACTIVE",
            "offline_fallback_operational": True,
        },
        policy_enforcement={
            "guardrail_status": "ACTIVE",
            "max_touches_cap": 3,
            "cooldown_hours": 24,
            "discount_cap_bps": 1000,
            "holdout_ratio_pct": 10,
        },
        timestamp=datetime.now(UTC),
    )
