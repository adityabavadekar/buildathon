"""Webhook redelivery idempotency: Razorpay uses at-least-once delivery, so
the same event can arrive more than once (razorpay.com/docs/webhooks/best-practices).
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


def _seed_case(case_id: str, link_id: str, amount_paise: int) -> None:
    repo = get_case_repository()
    now = datetime.now(UTC)
    case = RecoveryCase(
        case_id=case_id,
        merchant_id="merch_redelivery",
        state=RecoveryState.OUTREACH_PENDING,
        experiment_arm=ExperimentArm.TREATMENT,
        amount_paise=amount_paise,
        currency="INR",
        payment_link_id=link_id,
        failure_event=RawFailureEvent(
            event_id=f"evt_{case_id}",
            payment_id=f"pay_{case_id}",
            customer_id=f"cust_{case_id}",
            amount_paise=amount_paise,
            currency="INR",
            payment_rail=PaymentRail.CARD,
            error_code="AUTH_FAIL",
            occurred_at=now,
        ),
    )
    repo.save(case)


def test_redelivered_partially_paid_does_not_double_count(client: TestClient) -> None:
    case_id = "case_redelivery_partial"
    link_id = "plink_redelivery_partial"
    _seed_case(case_id, link_id, amount_paise=200000)

    payload = {
        "event": "payment_link.partially_paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": link_id,
                    "amount_paid": 50000,
                    "notes": {"case_id": case_id},
                }
            },
            "payment": {"entity": {"id": "pay_partial_redelivered_1"}},
        },
    }

    first = client.post("/api/webhooks/razorpay", json=payload)
    assert first.status_code == 200
    assert first.json()["action_taken"] == "PARTIAL_PAYMENT_RECORDED"

    repo = get_case_repository()
    after_first = repo.get_by_id(case_id)
    assert after_first is not None
    assert after_first.recovered_amount_paise == 50000

    second = client.post("/api/webhooks/razorpay", json=payload)
    assert second.status_code == 200
    assert second.json()["action_taken"] == "ALREADY_RECORDED"

    after_second = repo.get_by_id(case_id)
    assert after_second is not None
    assert after_second.recovered_amount_paise == 50000


def test_two_distinct_partial_payments_both_count(client: TestClient) -> None:
    case_id = "case_redelivery_distinct_partials"
    link_id = "plink_redelivery_distinct_partials"
    _seed_case(case_id, link_id, amount_paise=300000)

    def partial_payload(payment_id: str, amount_paid: int) -> dict[str, object]:
        return {
            "event": "payment_link.partially_paid",
            "payload": {
                "payment_link": {
                    "entity": {
                        "id": link_id,
                        "amount_paid": amount_paid,
                        "notes": {"case_id": case_id},
                    }
                },
                "payment": {"entity": {"id": payment_id}},
            },
        }

    first = client.post(
        "/api/webhooks/razorpay", json=partial_payload("pay_partial_a", 100000)
    )
    assert first.json()["action_taken"] == "PARTIAL_PAYMENT_RECORDED"

    second = client.post(
        "/api/webhooks/razorpay", json=partial_payload("pay_partial_b", 100000)
    )
    assert second.json()["action_taken"] == "PARTIAL_PAYMENT_RECORDED"

    repo = get_case_repository()
    case = repo.get_by_id(case_id)
    assert case is not None
    assert case.recovered_amount_paise == 200000


def test_redelivered_expired_is_not_logged_twice(client: TestClient) -> None:
    case_id = "case_redelivery_expired"
    link_id = "plink_redelivery_expired"
    _seed_case(case_id, link_id, amount_paise=150000)

    payload = {
        "event": "payment_link.expired",
        "payload": {
            "payment_link": {"entity": {"id": link_id, "notes": {"case_id": case_id}}}
        },
    }

    first = client.post("/api/webhooks/razorpay", json=payload)
    assert first.status_code == 200
    assert first.json()["action_taken"] == "EXPIRY_LOGGED"

    second = client.post("/api/webhooks/razorpay", json=payload)
    assert second.status_code == 200
    assert second.json()["action_taken"] == "ALREADY_RECORDED"

    repo = get_case_repository()
    case = repo.get_by_id(case_id)
    assert case is not None
    expiry_entries = [
        entry
        for entry in case.audit_trail
        if entry.event_name == "payment_link.expired"
    ]
    assert len(expiry_entries) == 1


def test_redelivered_payment_captured_stays_idempotent(client: TestClient) -> None:
    fail_payload = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_captured_redelivery",
                    "amount": 250000,
                    "currency": "INR",
                    "method": "upi",
                    "customer_id": "cust_captured_redelivery",
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_reason": "insufficient_funds",
                }
            }
        },
    }
    client.post("/api/webhooks/razorpay", json=fail_payload)

    capture_payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_captured_redelivery",
                    "amount": 250000,
                    "currency": "INR",
                }
            }
        },
    }
    first = client.post("/api/webhooks/razorpay", json=capture_payload)
    assert first.json()["action_taken"] == "RECOVERED"

    second = client.post("/api/webhooks/razorpay", json=capture_payload)
    assert second.status_code == 200
    assert second.json()["action_taken"] == "RECOVERED"

    repo = get_case_repository()
    case = repo.get_by_payment_id("pay_captured_redelivery")
    assert case is not None
    assert case.recovered_amount_paise == 250000
    recovered_entries = [
        entry for entry in case.audit_trail if entry.event_name == "payment.recovered"
    ]
    assert len(recovered_entries) == 1


def test_redelivered_subscription_halted_does_not_duplicate_case(
    client: TestClient,
) -> None:
    payload = {
        "event": "subscription.halted",
        "payload": {
            "subscription": {
                "entity": {
                    "id": "sub_redelivery_1",
                    "customer_id": "cust_sub_redelivery",
                    "plan": {"amount": 99900},
                }
            }
        },
    }

    first = client.post("/api/webhooks/razorpay", json=payload)
    assert first.status_code == 202
    case_id = first.json()["case_id"]

    second = client.post("/api/webhooks/razorpay", json=payload)
    assert second.status_code == 202
    assert second.json()["action_taken"] == "ALREADY_QUEUED"
    assert second.json()["case_id"] == case_id

    repo = get_case_repository()
    all_cases = repo.list_cases(limit=100)
    matching = [
        c for c in all_cases if c.failure_event.subscription_id == "sub_redelivery_1"
    ]
    assert len(matching) == 1


def test_redelivered_virtual_account_credited_stays_idempotent(
    client: TestClient,
) -> None:
    case_id = "case_redelivery_va"
    va_id = "va_redelivery_1"
    repo = get_case_repository()
    now = datetime.now(UTC)
    case = RecoveryCase(
        case_id=case_id,
        merchant_id="merch_redelivery",
        state=RecoveryState.P2P_WAITING,
        experiment_arm=ExperimentArm.TREATMENT,
        amount_paise=400000,
        currency="INR",
        virtual_account_id=va_id,
        failure_event=RawFailureEvent(
            event_id=f"evt_{case_id}",
            payment_id=f"pay_{case_id}",
            customer_id=f"cust_{case_id}",
            amount_paise=400000,
            currency="INR",
            payment_rail=PaymentRail.B2B_INVOICE,
            error_code="AUTH_FAIL",
            occurred_at=now,
        ),
    )
    repo.save(case)

    payload = {
        "event": "virtual_account.credited",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_va_credit_1",
                    "amount": 400000,
                    "method": "bank_transfer",
                }
            },
            "virtual_account": {"entity": {"id": va_id}},
        },
    }

    first = client.post("/api/webhooks/razorpay", json=payload)
    assert first.status_code == 200
    assert first.json()["action_taken"] == "RECOVERED"

    second = client.post("/api/webhooks/razorpay", json=payload)
    assert second.status_code == 200
    assert second.json()["action_taken"] == "RECOVERED"

    updated = repo.get_by_id(case_id)
    assert updated is not None
    assert updated.recovered_amount_paise == 400000
    reconciled_entries = [
        entry
        for entry in updated.audit_trail
        if entry.event_name == "smart_collect.reconciled"
    ]
    assert len(reconciled_entries) == 1
