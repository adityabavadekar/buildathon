"""Razorpay subscription lifecycle webhook handling: charged (recovery),
cancelled (escalation), completed (informational no-op), and confirming the
untouched administrative events still fall through to UNSUPPORTED_EVENT.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.audit.models import RecoveryCase
from app.audit.repository import get_case_repository
from app.core.enums import ExperimentArm, PaymentRail, RecoveryState
from app.detection.models import RawFailureEvent

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def _seed_halted_case(
    case_id: str,
    subscription_id: str,
    payment_id: str,
    amount_paise: int,
    *,
    state: RecoveryState = RecoveryState.OUTREACH_PENDING,
) -> None:
    repo = get_case_repository()
    now = datetime.now(UTC)
    case = RecoveryCase(
        case_id=case_id,
        merchant_id="merch_sub_lifecycle",
        state=state,
        experiment_arm=ExperimentArm.TREATMENT,
        amount_paise=amount_paise,
        currency="INR",
        failure_event=RawFailureEvent(
            event_id=f"evt_{case_id}",
            payment_id=payment_id,
            customer_id=f"cust_{case_id}",
            amount_paise=amount_paise,
            currency="INR",
            payment_rail=PaymentRail.ENACH,
            error_code="SUBSCRIPTION_HALTED",
            error_reason="mandate_exhausted",
            occurred_at=now,
            subscription_id=subscription_id,
        ),
    )
    repo.save(case)


def test_subscription_charged_resolves_open_case_to_recovered(
    client: TestClient,
) -> None:
    case_id = "case_sub_charged_1"
    sub_id = "sub_charged_1"
    payment_id = "pay_halted_sub_charged_1"
    _seed_halted_case(case_id, sub_id, payment_id, amount_paise=99900)

    payload = {
        "event": "subscription.charged",
        "payload": {
            "subscription": {"entity": {"id": sub_id}},
            "payment": {"entity": {"id": "pay_charge_1", "amount": 99900}},
        },
    }

    response = client.post("/api/webhooks/razorpay", json=payload)
    assert response.status_code == 200
    assert response.json()["action_taken"] == "RECOVERED"
    assert response.json()["case_id"] == case_id

    repo = get_case_repository()
    case = repo.get_by_id(case_id)
    assert case is not None
    assert case.state == RecoveryState.RECOVERED
    assert case.recovered_amount_paise == 99900


def test_redelivered_subscription_charged_is_idempotent(client: TestClient) -> None:
    case_id = "case_sub_charged_redelivery"
    sub_id = "sub_charged_redelivery"
    payment_id = "pay_halted_sub_charged_redelivery"
    _seed_halted_case(case_id, sub_id, payment_id, amount_paise=149900)

    payload = {
        "event": "subscription.charged",
        "payload": {
            "subscription": {"entity": {"id": sub_id}},
            "payment": {"entity": {"id": "pay_charge_redelivery", "amount": 149900}},
        },
    }

    first = client.post("/api/webhooks/razorpay", json=payload)
    assert first.status_code == 200
    assert first.json()["action_taken"] == "RECOVERED"

    second = client.post("/api/webhooks/razorpay", json=payload)
    assert second.status_code == 200
    assert second.json()["action_taken"] == "RECOVERED"

    repo = get_case_repository()
    case = repo.get_by_id(case_id)
    assert case is not None
    assert case.recovered_amount_paise == 149900
    recovered_entries = [
        entry for entry in case.audit_trail if entry.event_name == "payment.recovered"
    ]
    assert len(recovered_entries) == 1


def test_subscription_cancelled_escalates_open_case(client: TestClient) -> None:
    case_id = "case_sub_cancelled_1"
    sub_id = "sub_cancelled_1"
    payment_id = "pay_halted_sub_cancelled_1"
    _seed_halted_case(
        case_id, sub_id, payment_id, amount_paise=199900, state=RecoveryState.IN_DUNNING
    )

    payload = {
        "event": "subscription.cancelled",
        "payload": {"subscription": {"entity": {"id": sub_id}}},
    }

    response = client.post("/api/webhooks/razorpay", json=payload)
    assert response.status_code == 200
    assert response.json()["action_taken"] == "ESCALATED"
    assert response.json()["case_id"] == case_id

    repo = get_case_repository()
    case = repo.get_by_id(case_id)
    assert case is not None
    assert case.state == RecoveryState.ESCALATED
    escalation_entries = [
        entry
        for entry in case.audit_trail
        if entry.event_name == "subscription.cancelled"
    ]
    assert len(escalation_entries) == 1
    assert "mandate cancelled" in (escalation_entries[0].notes or "")


def test_subscription_completed_noops_when_case_already_terminal(
    client: TestClient,
) -> None:
    case_id = "case_sub_completed_terminal"
    sub_id = "sub_completed_terminal"
    payment_id = "pay_halted_sub_completed_terminal"
    _seed_halted_case(
        case_id,
        sub_id,
        payment_id,
        amount_paise=299900,
        state=RecoveryState.RECOVERED,
    )

    payload = {
        "event": "subscription.completed",
        "payload": {"subscription": {"entity": {"id": sub_id}}},
    }

    response = client.post("/api/webhooks/razorpay", json=payload)
    assert response.status_code == 200
    assert response.json()["action_taken"] == "NOOP"

    repo = get_case_repository()
    case = repo.get_by_id(case_id)
    assert case is not None
    assert case.state == RecoveryState.RECOVERED
    completion_entries = [
        entry
        for entry in case.audit_trail
        if entry.event_name == "subscription.completed"
    ]
    assert len(completion_entries) == 0


def test_subscription_paused_returns_unsupported_event(client: TestClient) -> None:
    payload = {
        "event": "subscription.paused",
        "payload": {"subscription": {"entity": {"id": "sub_paused_1"}}},
    }

    response = client.post("/api/webhooks/razorpay", json=payload)
    assert response.status_code == 200
    assert response.json()["action_taken"] == "UNSUPPORTED_EVENT"
