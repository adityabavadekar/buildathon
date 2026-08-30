"""API endpoints for payment rail health observability and simulation controls."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.detection.rail_health import (
    RailHealthMetrics,
    get_rail_health_registry,
)

router = APIRouter(prefix="/rails", tags=["Rail Health"])


class DegradeOverrideRequest(BaseModel):
    """Payload for triggering a simulated degradation incident on a payment rail."""

    rail: str
    ratio: float = 3.5
    current_rate: float = 0.45
    baseline_rate: float = 0.10
    hold_minutes: int = 60


@router.get("/health", response_model=list[RailHealthMetrics])
def get_all_rails_health() -> list[RailHealthMetrics]:
    """Return real-time statistical health telemetry for all recognized payment rails."""
    registry = get_rail_health_registry()
    return registry.get_all_rails_health()


@router.post("/override/degrade", response_model=RailHealthMetrics)
def set_rail_degrade_override(req: DegradeOverrideRequest) -> RailHealthMetrics:
    """Manually trigger degraded circuit breaker on a rail (for incident drills/simulation)."""
    registry = get_rail_health_registry()
    return registry.set_degraded_override(
        rail=req.rail,
        ratio=req.ratio,
        current_rate=req.current_rate,
        baseline_rate=req.baseline_rate,
        hold_minutes=req.hold_minutes,
    )


@router.post("/override/release", response_model=RailHealthMetrics)
def release_rail_override(rail: str) -> RailHealthMetrics:
    """Manually release a payment rail back to NORMAL health state."""
    registry = get_rail_health_registry()
    return registry.release_rail(rail)
