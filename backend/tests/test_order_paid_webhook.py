"""order.paid webhook: fires when checkout completes and carries both payment
and order entities. It must resolve an open case the same way payment.captured
does, be a clean no-op when no case matches, and not double-process a payment
already resolved by a payment.captured webhook for the same payment_id
(razorpay.com/docs/webhooks/orders -- captured and order.paid are different
views of the same success).
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


def _seed_case(case_id: str, payment_id: str, amount_paise: int) -> None:
    repo = get_case_repository()
    now = datetime.now(UTC)
    case = RecoveryCase(
        case_id=case_id,
        merchant_id="merch_order_paid",
        state=RecoveryState.OUTREACH_PENDING,
        experiment_arm=ExperimentArm.TREATMENT,
        amount_paise=amount_paise,
        currency="INR",
        failure_event=RawFailureEvent(
            event_id=f"evt_{case_id}",
            payment_id=payment_id,
            customer_id=f"cust_{case_id}",
            amount_paise=amount_paise,
            currency="INR",
            payment_rail=PaymentRail.CARD,
            error_code="AUTH_FAIL",
            occurred_at=now,
        ),
    )
    repo.save(case)


def _order_paid_payload(
    payment_id: str, amount: int, attempts: int, order_id: str = "order_1"
) -> dict[str, object]:
    return {
        "event": "order.paid",
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "amount": amount,
                    "currency": "INR",
                }
            },
            "order": {
                "entity": {
                    "id": order_id,
                    "entity": "order",
                    "amount": amount,
                    "amount_paid": amount,
                    "amount_due": 0,
                    "currency": "INR",
                    "receipt": "rcpt_1",
                    "offer_id": None,
                    "status": "paid",
                    "attempts": attempts,
                    "notes": {},
                    "created_at": 1700000000,
                }
            },
        },
    }


def test_order_paid_resolves_open_case_to_recovered(client: TestClient) -> None:
    case_id = "case_order_paid_resolve"
    payment_id = "pay_order_paid_resolve"
    _seed_case(case_id, payment_id, amount_paise=180000)

    payload = _order_paid_payload(payment_id, amount=180000, attempts=1)
    resp = client.post("/api/webhooks/razorpay", json=payload)

    assert resp.status_code == 200
    assert resp.json()["action_taken"] == "RECOVERED"
    assert resp.json()["case_id"] == case_id

    repo = get_case_repository()
    case = repo.get_by_id(case_id)
    assert case is not None
    assert case.state == RecoveryState.RECOVERED
    assert case.recovered_amount_paise == 180000


def test_order_paid_with_no_matching_case_is_clean_noop(client: TestClient) -> None:
    payload = _order_paid_payload("pay_order_paid_unmatched", amount=50000, attempts=1)
    resp = client.post("/api/webhooks/razorpay", json=payload)

    assert resp.status_code == 200
    assert resp.json()["action_taken"] == "NOOP"
    assert resp.json()["case_id"] is None

    repo = get_case_repository()
    assert repo.get_by_payment_id("pay_order_paid_unmatched") is None


def test_order_paid_after_payment_captured_does_not_double_process(
    client: TestClient,
) -> None:
    case_id = "case_order_paid_after_captured"
    payment_id = "pay_order_paid_after_captured"
    _seed_case(case_id, payment_id, amount_paise=220000)

    captured_payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "amount": 220000,
                    "currency": "INR",
                }
            }
        },
    }
    first = client.post("/api/webhooks/razorpay", json=captured_payload)
    assert first.json()["action_taken"] == "RECOVERED"

    order_paid_payload = _order_paid_payload(payment_id, amount=220000, attempts=2)
    second = client.post("/api/webhooks/razorpay", json=order_paid_payload)
    assert second.status_code == 200
    assert second.json()["action_taken"] == "RECOVERED"

    repo = get_case_repository()
    case = repo.get_by_id(case_id)
    assert case is not None
    assert case.recovered_amount_paise == 220000
    recovered_entries = [
        entry for entry in case.audit_trail if entry.event_name == "payment.recovered"
    ]
    assert len(recovered_entries) == 1


def test_order_paid_captures_attempts_in_audit_decision_inputs(
    client: TestClient,
) -> None:
    case_id = "case_order_paid_attempts"
    payment_id = "pay_order_paid_attempts"
    _seed_case(case_id, payment_id, amount_paise=90000)

    payload = _order_paid_payload(payment_id, amount=90000, attempts=3)
    resp = client.post("/api/webhooks/razorpay", json=payload)
    assert resp.status_code == 200

    repo = get_case_repository()
    case = repo.get_by_id(case_id)
    assert case is not None
    recovered_entry = next(
        entry for entry in case.audit_trail if entry.event_name == "payment.recovered"
    )
    assert recovered_entry.decision_inputs.get("order_attempts") == 3
