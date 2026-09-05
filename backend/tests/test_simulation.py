"""Tests for the simulation reset, manual case resolution, and system status endpoints.

seed_simulation_batch was removed: it called the orchestrator directly,
bypassing the webhook/HMAC path real Razorpay traffic and the fleet
simulator both go through. Synthetic traffic now only ever enters via
FleetSimulator, which posts through /api/webhooks/razorpay (see
test_pipeline_queue.py::test_fleet_events_are_queued_via_the_real_webhook_route).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from app.core.enums import ExperimentArm, PaymentRail
from app.detection.models import RawFailureEvent
from app.intervention.orchestrator import RecoveryOrchestrator

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def _event(payment_id: str) -> RawFailureEvent:
    return RawFailureEvent(
        event_id=f"evt_{payment_id}",
        payment_id=payment_id,
        customer_id="cust_sim_status",
        amount_paise=150000,
        currency="INR",
        payment_rail=PaymentRail.UPI,
        error_code="GATEWAY_ERROR",
        error_reason="server_error",
        error_description="server_error",
        occurred_at=datetime.now(UTC),
    )


@pytest.mark.anyio
async def test_reset_simulation_clears_repository(client: TestClient) -> None:
    orchestrator = RecoveryOrchestrator()
    await orchestrator.process_failure_event(
        _event("pay_sim_reset_1"), experiment_arm_override=ExperimentArm.TREATMENT
    )

    res_analytics = client.get("/api/analytics")
    assert res_analytics.json()["total_cases"] >= 1

    res_reset = client.post("/api/simulation/reset")
    assert res_reset.status_code == 200
    assert res_reset.json()["status"] == "cleared"

    res_after = client.get("/api/analytics")
    assert res_after.json()["total_cases"] == 0


@pytest.mark.anyio
async def test_resolve_case_marks_case_recovered(client: TestClient) -> None:
    orchestrator = RecoveryOrchestrator()
    case = await orchestrator.process_failure_event(
        _event("pay_sim_resolve_1"),
        experiment_arm_override=ExperimentArm.TREATMENT,
    )

    res = client.post(
        "/api/simulation/resolve-case",
        json={"case_id": case.case_id},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "resolved"
    assert data["state"] == "RECOVERED"
    assert data["recovered_amount_paise"] > 0


@pytest.mark.anyio
async def test_resolve_case_on_already_recovered_case_is_idempotent(
    client: TestClient,
) -> None:
    """Resolving a case a second time must not re-run recovery accounting --
    the route has an explicit already_resolved branch precisely so a repeat
    call reports the existing terminal state rather than double-processing it.
    """
    orchestrator = RecoveryOrchestrator()
    case = await orchestrator.process_failure_event(
        _event("pay_sim_resolve_twice"),
        experiment_arm_override=ExperimentArm.TREATMENT,
    )

    first = client.post("/api/simulation/resolve-case", json={"case_id": case.case_id})
    assert first.status_code == 200
    first_amount = first.json()["recovered_amount_paise"]

    second = client.post("/api/simulation/resolve-case", json={"case_id": case.case_id})
    assert second.status_code == 200
    second_data = second.json()
    assert second_data["status"] == "already_resolved"
    assert second_data["recovered_amount_paise"] == first_amount


def test_system_status_reports_operational_state(client: TestClient) -> None:
    res = client.get("/api/simulation/status")
    assert res.status_code == 200
    data = res.json()
    assert data["system_status"] in ("OPERATIONAL", "HELD")
    assert data["gateway_integration"]["provider"] == "Razorpay"
    assert data["gateway_integration"]["webhook_endpoint"] == "/api/webhooks/razorpay"
    assert "llm_engine" in data
    assert "policy_enforcement" in data
