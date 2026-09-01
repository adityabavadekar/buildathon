"""Comprehensive tests for customer payment behavior profiles and risk tier aggregation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.audit.models import RecoveryCase
from app.audit.postgres_store import RelationalCaseStore
from app.core.enums import ExperimentArm, PaymentRail, RecoveryState
from app.detection.customer_profile import (
    CustomerProfileRegistry,
    CustomerRiskTier,
)
from app.detection.models import RawFailureEvent

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def test_customer_profile_aggregation() -> None:
    """Verify customer profile computation over multiple historical cases in PostgreSQL."""
    store = RelationalCaseStore()
    registry = CustomerProfileRegistry()

    now = datetime.now(UTC)
    cust_id = "cust_loyal_1"

    # Seed 3 cases: 2 recovered (delay 2 hours each) and 1 active
    for i in range(3):
        is_rec = i < 2
        case = RecoveryCase(
            case_id=f"case_cust_{i}",
            merchant_id="merch_1",
            state=RecoveryState.RECOVERED if is_rec else RecoveryState.IN_DUNNING,
            experiment_arm=ExperimentArm.TREATMENT,
            amount_paise=100000,
            recovered_amount_paise=100000 if is_rec else 0,
            currency="INR",
            created_at=now - timedelta(hours=10 + i),
            updated_at=now - timedelta(hours=8 + i) if is_rec else now,
            failure_event=RawFailureEvent(
                event_id=f"evt_{i}",
                payment_id=f"pay_cust_{i}",
                customer_id=cust_id,
                amount_paise=100000,
                currency="INR",
                payment_rail=PaymentRail.UPI,
                error_code="U30",
                error_reason="insufficient_funds",
                occurred_at=now,
            ),
        )
        store.save_case(case)

    profile = registry.get_profile(cust_id)
    assert profile.customer_id == cust_id
    assert profile.total_cases == 3
    assert profile.recovered_cases == 2
    assert profile.recovered_rate == round(2 / 3, 4)
    assert profile.preferred_rail == "UPI"
    assert profile.outstanding_paise == 100000
    assert profile.risk_tier in (CustomerRiskTier.LOW, CustomerRiskTier.MEDIUM)


def test_customer_profile_api(client: TestClient) -> None:
    """Verify customer profile endpoints via REST API."""
    res = client.get("/api/customers/profiles?limit=10")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    single_res = client.get("/api/customers/cust_non_existent/profile")
    assert single_res.status_code == 200
    assert single_res.json()["customer_id"] == "cust_non_existent"
