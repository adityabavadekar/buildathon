"""Comprehensive tests for payment rail degradation detection and automated circuit breaker."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.audit.models import RecoveryCase
from app.core.enums import (
    ExperimentArm,
    InterventionType,
    PaymentRail,
    PolicyCheckResult,
    RecoveryState,
)
from app.detection.models import RawFailureEvent
from app.detection.rail_health import (
    RailHealthRegistry,
    RailHealthState,
    get_rail_health_registry,
)
from app.intervention.models import InterventionPlan, MerchantPolicy
from app.intervention.policy_gate import PolicyGate

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


@pytest.fixture
def clean_registry() -> RailHealthRegistry:
    reg = get_rail_health_registry()
    reg.release_rail(PaymentRail.UPI)
    reg.release_rail(PaymentRail.CARD)
    reg.release_rail(PaymentRail.ENACH)
    return reg


def test_rail_health_detector_and_override(clean_registry: RailHealthRegistry) -> None:
    """Verify rail health metrics, degradation overrides, and auto-release mechanics."""
    # 1. Initial state is normal
    clean_registry.release_rail(PaymentRail.UPI)
    metrics = clean_registry.get_rail_metrics(PaymentRail.UPI)
    assert metrics.state == RailHealthState.NORMAL

    # 2. Trigger degraded override (simulating 4.2x failure rate spike)
    clean_registry.set_degraded_override(
        PaymentRail.UPI,
        ratio=4.2,
        current_rate=0.42,
        baseline_rate=0.10,
        hold_minutes=60,
    )
    assert clean_registry.is_rail_degraded(PaymentRail.UPI) is True
    metrics_deg = clean_registry.get_rail_metrics(PaymentRail.UPI)
    assert metrics_deg.state == RailHealthState.DEGRADED
    assert metrics_deg.ratio == 4.2
    assert metrics_deg.hold_until is not None

    # Other rail unaffected
    assert clean_registry.is_rail_degraded(PaymentRail.CARD) is False


def test_policy_gate_blocks_retries_on_degraded_rail(
    clean_registry: RailHealthRegistry,
) -> None:
    """Verify policy gate halts SMART_RETRY on degraded rail while allowing healthy rails."""
    gate = PolicyGate()
    policy = MerchantPolicy()

    event_upi = RawFailureEvent(
        event_id="evt_upi_1",
        payment_id="pay_upi_deg_1",
        customer_id="cust_1",
        amount_paise=100000,
        currency="INR",
        payment_rail=PaymentRail.UPI,
        error_code="U30",
        error_reason="bank_timeout",
        occurred_at=datetime.now(UTC),
    )
    case_upi = RecoveryCase(
        case_id="case_upi_1",
        merchant_id="merchant_1",
        state=RecoveryState.ANALYSIS_QUEUED,
        experiment_arm=ExperimentArm.TREATMENT,
        amount_paise=100000,
        currency="INR",
        failure_event=event_upi,
    )

    plan_retry = InterventionPlan(
        plan_id="plan_retry_1",
        case_id="case_upi_1",
        intervention_type=InterventionType.SMART_RETRY,
        scheduled_at=datetime.now(UTC) + timedelta(minutes=5),
        idempotency_key="idem_retry_1",
        rationale="Retry after liquidity window",
    )

    # 1. Normal state allows retry
    clean_registry.release_rail(PaymentRail.UPI)
    eval_normal = gate.evaluate(case_upi, plan_retry, policy)
    assert eval_normal.is_allowed is True

    # 2. Degraded rail blocks retry
    clean_registry.set_degraded_override(PaymentRail.UPI, ratio=3.8)
    eval_degraded = gate.evaluate(case_upi, plan_retry, policy)
    assert eval_degraded.is_allowed is False
    assert eval_degraded.result == PolicyCheckResult.BLOCKED_COOLDOWN
    assert "currently degraded" in eval_degraded.reason


def test_rail_health_api_endpoints(
    client: TestClient, clean_registry: RailHealthRegistry
) -> None:
    """Verify API endpoints for rail health telemetry and incident simulation."""
    # 1. Fetch health
    res = client.get("/api/rails/health")
    assert res.status_code == 200
    rails = res.json()
    assert isinstance(rails, list)
    assert any(r["rail"] == "UPI" for r in rails)

    # 2. Trigger override
    deg_res = client.post(
        "/api/rails/override/degrade",
        json={
            "rail": "UPI",
            "ratio": 3.5,
            "current_rate": 0.35,
            "baseline_rate": 0.10,
            "hold_minutes": 30,
        },
    )
    assert deg_res.status_code == 200
    assert deg_res.json()["state"] == "DEGRADED"

    # 3. Release override
    rel_res = client.post("/api/rails/override/release?rail=UPI")
    assert rel_res.status_code == 200
    assert rel_res.json()["state"] == "NORMAL"
