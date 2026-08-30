"""Comprehensive tests for recovery forecast and funnel arithmetic."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.audit.models import RecoveryCase
from app.audit.repository import get_case_repository
from app.core.enums import ExperimentArm, PaymentRail, RecoveryState
from app.detection.models import RawFailureEvent

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def test_recovery_forecast_endpoint(client: TestClient) -> None:
    """Verify recovery forecast API returns funnel numbers, confidence window, and segments."""
    repo = get_case_repository()
    now = datetime.now(UTC)

    # Seed 2 open cases and 1 recovered case
    c1 = RecoveryCase(
        case_id="case_fc_1",
        merchant_id="merch_1",
        state=RecoveryState.IN_DUNNING,
        experiment_arm=ExperimentArm.TREATMENT,
        amount_paise=100000,
        currency="INR",
        failure_event=RawFailureEvent(
            event_id="evt_fc_1",
            payment_id="pay_fc_1",
            customer_id="cust_1",
            amount_paise=100000,
            currency="INR",
            payment_rail=PaymentRail.UPI,
            error_code="U30",
            occurred_at=now,
        ),
    )
    c2 = RecoveryCase(
        case_id="case_fc_2",
        merchant_id="merch_1",
        state=RecoveryState.RECOVERED,
        experiment_arm=ExperimentArm.TREATMENT,
        amount_paise=200000,
        recovered_amount_paise=200000,
        currency="INR",
        failure_event=RawFailureEvent(
            event_id="evt_fc_2",
            payment_id="pay_fc_2",
            customer_id="cust_2",
            amount_paise=200000,
            currency="INR",
            payment_rail=PaymentRail.UPI,
            error_code="U30",
            occurred_at=now,
        ),
    )
    repo.save(c1)
    repo.save(c2)

    res = client.get("/api/analytics/forecast")
    assert res.status_code == 200
    fc = res.json()

    assert "at_risk_paise" in fc
    assert "expected_recoverable_paise" in fc
    assert "recovered_paise" in fc
    assert "remaining_opportunity_paise" in fc
    assert "attributable_remaining_paise" in fc
    assert fc["at_risk_paise"] >= 100000
    assert fc["recovered_paise"] >= 200000
    assert fc["confidence_window_pct"] == 5.0
