"""Tests for Razorpay invoice lifecycle webhook reconciliation (B2B receivables).

Mirrors test_payment_link_lifecycle.py and test_webhook_redelivery_idempotency.py
for the parallel invoice.* event family: invoice.paid, invoice.partially_paid,
invoice.expired.
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


def _seed_case(case_id: str, invoice_id: str, amount_paise: int) -> None:
    repo = get_case_repository()
    now = datetime.now(UTC)
    case = RecoveryCase(
        case_id=case_id,
        merchant_id="merch_invoice",
        state=RecoveryState.OUTREACH_PENDING,
        experiment_arm=ExperimentArm.TREATMENT,
        amount_paise=amount_paise,
        currency="INR",
        failure_event=RawFailureEvent(
            event_id=f"evt_{case_id}",
            payment_id=f"pay_{case_id}",
            customer_id="cust_invoice_1",
            amount_paise=amount_paise,
            currency="INR",
            payment_rail=PaymentRail.B2B_INVOICE,
            error_code="RECEIVABLE_OVERDUE",
            occurred_at=now,
            invoice_id=invoice_id,
        ),
    )
    repo.save(case)


def test_invoice_paid_resolves_case_to_recovered(client: TestClient) -> None:
    """invoice.paid should find the case by invoice_id and mark it RECOVERED."""
    case_id = "case_inv_paid_1"
    invoice_id = "inv_test_paid_1"
    _seed_case(case_id, invoice_id, amount_paise=300000)

    payload = {
        "event": "invoice.paid",
        "payload": {
            "invoice": {
                "entity": {
                    "id": invoice_id,
                    "amount_paid": 300000,
                    "notes": {"case_id": case_id},
                }
            }
        },
    }
    res = client.post("/api/webhooks/razorpay", json=payload)
    assert res.status_code == 200
    assert res.json()["action_taken"] == "RECOVERED"

    repo = get_case_repository()
    updated = repo.get_by_id(case_id)
    assert updated is not None
    assert updated.state == RecoveryState.RECOVERED
    assert updated.recovered_amount_paise == 300000


def test_invoice_partially_paid_increments_recovered_amount(
    client: TestClient,
) -> None:
    """invoice.partially_paid should increment recovered_amount_paise without changing state."""
    case_id = "case_inv_partial_1"
    invoice_id = "inv_test_partial_1"
    _seed_case(case_id, invoice_id, amount_paise=400000)

    payload = {
        "event": "invoice.partially_paid",
        "payload": {
            "invoice": {
                "entity": {
                    "id": invoice_id,
                    "amount_paid": 100000,
                    "notes": {"case_id": case_id},
                }
            },
            "payment": {"entity": {"id": "pay_inv_partial_first"}},
        },
    }
    res = client.post("/api/webhooks/razorpay", json=payload)
    assert res.status_code == 200
    assert res.json()["action_taken"] == "PARTIAL_PAYMENT_RECORDED"

    repo = get_case_repository()
    updated = repo.get_by_id(case_id)
    assert updated is not None
    assert updated.recovered_amount_paise == 100000
    assert updated.state == RecoveryState.OUTREACH_PENDING


def test_two_distinct_invoice_partial_payments_both_count(
    client: TestClient,
) -> None:
    """Two distinct partial payments on the same invoice should both be recorded."""
    case_id = "case_inv_partial_2"
    invoice_id = "inv_test_partial_2"
    _seed_case(case_id, invoice_id, amount_paise=500000)

    first = client.post(
        "/api/webhooks/razorpay",
        json={
            "event": "invoice.partially_paid",
            "payload": {
                "invoice": {
                    "entity": {
                        "id": invoice_id,
                        "amount_paid": 100000,
                        "notes": {"case_id": case_id},
                    }
                },
                "payment": {"entity": {"id": "pay_inv_partial_a"}},
            },
        },
    )
    second = client.post(
        "/api/webhooks/razorpay",
        json={
            "event": "invoice.partially_paid",
            "payload": {
                "invoice": {
                    "entity": {
                        "id": invoice_id,
                        "amount_paid": 150000,
                        "notes": {"case_id": case_id},
                    }
                },
                "payment": {"entity": {"id": "pay_inv_partial_b"}},
            },
        },
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["action_taken"] == "PARTIAL_PAYMENT_RECORDED"
    assert second.json()["action_taken"] == "PARTIAL_PAYMENT_RECORDED"

    repo = get_case_repository()
    updated = repo.get_by_id(case_id)
    assert updated is not None
    assert updated.recovered_amount_paise == 250000


def test_redelivered_invoice_paid_is_idempotent(client: TestClient) -> None:
    """A redelivered invoice.paid must not double-count or duplicate audit entries."""
    case_id = "case_inv_redelivery_paid"
    invoice_id = "inv_test_redelivery_paid"
    _seed_case(case_id, invoice_id, amount_paise=200000)

    payload = {
        "event": "invoice.paid",
        "payload": {
            "invoice": {
                "entity": {
                    "id": invoice_id,
                    "amount_paid": 200000,
                    "notes": {"case_id": case_id},
                }
            }
        },
    }
    first = client.post("/api/webhooks/razorpay", json=payload)
    second = client.post("/api/webhooks/razorpay", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200

    repo = get_case_repository()
    updated = repo.get_by_id(case_id)
    assert updated is not None
    assert updated.state == RecoveryState.RECOVERED
    assert updated.recovered_amount_paise == 200000

    reconciled_entries = [
        entry
        for entry in updated.audit_trail
        if entry.event_name == "invoice.paid_reconciled"
    ]
    assert len(reconciled_entries) == 1


def test_redelivered_invoice_partially_paid_does_not_double_count(
    client: TestClient,
) -> None:
    """A redelivered invoice.partially_paid with the same payment id must not double-count."""
    case_id = "case_inv_redelivery_partial"
    invoice_id = "inv_test_redelivery_partial"
    _seed_case(case_id, invoice_id, amount_paise=400000)

    payload = {
        "event": "invoice.partially_paid",
        "payload": {
            "invoice": {
                "entity": {
                    "id": invoice_id,
                    "amount_paid": 100000,
                    "notes": {"case_id": case_id},
                }
            },
            "payment": {"entity": {"id": "pay_inv_redelivery_1"}},
        },
    }
    first = client.post("/api/webhooks/razorpay", json=payload)
    assert first.status_code == 200
    assert first.json()["action_taken"] == "PARTIAL_PAYMENT_RECORDED"

    second = client.post("/api/webhooks/razorpay", json=payload)
    assert second.status_code == 200
    assert second.json()["action_taken"] == "ALREADY_RECORDED"

    repo = get_case_repository()
    updated = repo.get_by_id(case_id)
    assert updated is not None
    assert updated.recovered_amount_paise == 100000

    partial_entries = [
        entry
        for entry in updated.audit_trail
        if entry.event_name == "invoice.partially_paid"
    ]
    assert len(partial_entries) == 1


def test_redelivered_invoice_expired_is_not_logged_twice(client: TestClient) -> None:
    """A redelivered invoice.expired must not create a duplicate audit entry."""
    case_id = "case_inv_redelivery_expired"
    invoice_id = "inv_test_redelivery_expired"
    _seed_case(case_id, invoice_id, amount_paise=250000)

    payload = {
        "event": "invoice.expired",
        "payload": {
            "invoice": {
                "entity": {
                    "id": invoice_id,
                    "notes": {"case_id": case_id},
                }
            }
        },
    }
    first = client.post("/api/webhooks/razorpay", json=payload)
    assert first.status_code == 200
    assert first.json()["action_taken"] == "EXPIRY_LOGGED"

    second = client.post("/api/webhooks/razorpay", json=payload)
    assert second.status_code == 200
    assert second.json()["action_taken"] == "ALREADY_RECORDED"

    repo = get_case_repository()
    updated = repo.get_by_id(case_id)
    assert updated is not None
    expired_entries = [
        entry for entry in updated.audit_trail if entry.event_name == "invoice.expired"
    ]
    assert len(expired_entries) == 1
    assert updated.state == RecoveryState.OUTREACH_PENDING
