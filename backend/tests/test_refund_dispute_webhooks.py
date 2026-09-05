"""Refund and dispute webhook handling: post-recovery adjustments to
recovered_amount_paise and net_recovered_value_paise, plus dispute escalation.
Razorpay uses at-least-once delivery, so redelivery must not double-count.
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


def _seed_case(
    case_id: str,
    payment_id: str,
    amount_paise: int,
    *,
    state: RecoveryState = RecoveryState.RECOVERED,
    recovered_amount_paise: int | None = None,
) -> RecoveryCase:
    repo = get_case_repository()
    now = datetime.now(UTC)
    case = RecoveryCase(
        case_id=case_id,
        merchant_id="merch_refund_dispute",
        state=state,
        experiment_arm=ExperimentArm.TREATMENT,
        amount_paise=amount_paise,
        currency="INR",
        recovered_amount_paise=(
            recovered_amount_paise
            if recovered_amount_paise is not None
            else (amount_paise if state == RecoveryState.RECOVERED else 0)
        ),
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
    case.recompute_nrv()
    repo.save(case)
    return case


def _refund_payload(
    event: str, payment_id: str, refund_id: str, amount: int
) -> dict[str, object]:
    return {
        "event": event,
        "payload": {
            "payment": {"entity": {"id": payment_id}},
            "refund": {
                "entity": {
                    "id": refund_id,
                    "payment_id": payment_id,
                    "amount": amount,
                }
            },
        },
    }


def _dispute_payload(
    event: str, payment_id: str, dispute_id: str, amount: int, reason: str | None = None
) -> dict[str, object]:
    entity: dict[str, object] = {
        "id": dispute_id,
        "payment_id": payment_id,
        "amount": amount,
    }
    if reason:
        entity["reason_code"] = reason
    return {
        "event": event,
        "payload": {
            "payment": {"entity": {"id": payment_id}},
            "dispute": {"entity": entity},
        },
    }


def test_refund_processed_reduces_recovered_amount_and_recomputes_nrv(
    client: TestClient,
) -> None:
    case_id = "case_refund_processed"
    payment_id = "pay_refund_processed"
    _seed_case(case_id, payment_id, amount_paise=200000)

    payload = _refund_payload("refund.processed", payment_id, "rfnd_1", 50000)
    resp = client.post("/api/webhooks/razorpay", json=payload)
    assert resp.status_code == 200
    assert resp.json()["action_taken"] == "RECOVERED_AMOUNT_ADJUSTED"

    repo = get_case_repository()
    case = repo.get_by_id(case_id)
    assert case is not None
    assert case.recovered_amount_paise == 150000
    assert case.net_recovered_value_paise == 150000
    assert case.state == RecoveryState.RECOVERED

    entries = [e for e in case.audit_trail if e.event_name == "refund.processed"]
    assert len(entries) == 1
    assert entries[0].decision_inputs["refund_id"] == "rfnd_1"
    assert entries[0].decision_inputs["recovered_amount_after_paise"] == 150000


def test_redelivered_refund_processed_does_not_double_subtract(
    client: TestClient,
) -> None:
    case_id = "case_refund_redelivered"
    payment_id = "pay_refund_redelivered"
    _seed_case(case_id, payment_id, amount_paise=200000)

    payload = _refund_payload("refund.processed", payment_id, "rfnd_redeliver", 50000)

    first = client.post("/api/webhooks/razorpay", json=payload)
    assert first.json()["action_taken"] == "RECOVERED_AMOUNT_ADJUSTED"

    second = client.post("/api/webhooks/razorpay", json=payload)
    assert second.status_code == 200
    assert second.json()["action_taken"] == "ALREADY_RECORDED"

    repo = get_case_repository()
    case = repo.get_by_id(case_id)
    assert case is not None
    assert case.recovered_amount_paise == 150000


def test_full_refund_zeroes_recovered_amount_but_stays_recovered_state(
    client: TestClient,
) -> None:
    case_id = "case_refund_full"
    payment_id = "pay_refund_full"
    _seed_case(case_id, payment_id, amount_paise=100000)

    payload = _refund_payload("refund.processed", payment_id, "rfnd_full", 100000)
    resp = client.post("/api/webhooks/razorpay", json=payload)
    assert resp.json()["action_taken"] == "RECOVERED_AMOUNT_ADJUSTED"

    repo = get_case_repository()
    case = repo.get_by_id(case_id)
    assert case is not None
    assert case.recovered_amount_paise == 0
    # RECOVERED has no legal exit transition; state must remain RECOVERED,
    # with the true adjusted amount carried by recovered_amount_paise / audit.
    assert case.state == RecoveryState.RECOVERED
    entry = next(e for e in case.audit_trail if e.event_name == "refund.processed")
    assert entry.decision_inputs["fully_reversed"] is True


def test_refund_amount_exceeding_recorded_clamps_at_zero(client: TestClient) -> None:
    case_id = "case_refund_over"
    payment_id = "pay_refund_over"
    _seed_case(case_id, payment_id, amount_paise=50000)

    payload = _refund_payload("refund.processed", payment_id, "rfnd_over", 999999)
    resp = client.post("/api/webhooks/razorpay", json=payload)
    assert resp.status_code == 200

    repo = get_case_repository()
    case = repo.get_by_id(case_id)
    assert case is not None
    assert case.recovered_amount_paise == 0
    entry = next(e for e in case.audit_trail if e.event_name == "refund.processed")
    assert entry.decision_inputs["amount_anomaly"] is True


def test_refund_failed_logs_without_changing_amount(client: TestClient) -> None:
    case_id = "case_refund_failed"
    payment_id = "pay_refund_failed"
    _seed_case(case_id, payment_id, amount_paise=80000)

    payload = _refund_payload("refund.failed", payment_id, "rfnd_fail_1", 80000)
    resp = client.post("/api/webhooks/razorpay", json=payload)
    assert resp.json()["action_taken"] == "REFUND_FAILURE_LOGGED"

    repo = get_case_repository()
    case = repo.get_by_id(case_id)
    assert case is not None
    assert case.recovered_amount_paise == 80000
    assert any(e.event_name == "refund.failed" for e in case.audit_trail)


def test_refund_created_and_speed_changed_are_informational(client: TestClient) -> None:
    case_id = "case_refund_info"
    payment_id = "pay_refund_info"
    _seed_case(case_id, payment_id, amount_paise=60000)

    created = client.post(
        "/api/webhooks/razorpay",
        json=_refund_payload("refund.created", payment_id, "rfnd_info_1", 60000),
    )
    assert created.json()["action_taken"] == "LOGGED"

    speed = client.post(
        "/api/webhooks/razorpay",
        json=_refund_payload("refund.speed_changed", payment_id, "rfnd_info_1", 60000),
    )
    assert speed.json()["action_taken"] == "LOGGED"

    repo = get_case_repository()
    case = repo.get_by_id(case_id)
    assert case is not None
    assert case.recovered_amount_paise == 60000


def test_refund_for_unknown_payment_does_not_crash_and_logs_globally(
    client: TestClient,
) -> None:
    payload = _refund_payload(
        "refund.processed", "pay_does_not_exist", "rfnd_orphan", 10000
    )
    resp = client.post("/api/webhooks/razorpay", json=payload)
    assert resp.status_code == 200
    assert resp.json()["action_taken"] == "NO_MATCHING_CASE"


def test_dispute_created_escalates_open_case(client: TestClient) -> None:
    case_id = "case_dispute_created"
    payment_id = "pay_dispute_created"
    _seed_case(
        case_id,
        payment_id,
        amount_paise=120000,
        state=RecoveryState.IN_DUNNING,
        recovered_amount_paise=0,
    )

    payload = _dispute_payload(
        "payment.dispute.created", payment_id, "disp_1", 120000, reason="fraudulent"
    )
    resp = client.post("/api/webhooks/razorpay", json=payload)
    assert resp.json()["action_taken"] == "ESCALATED"

    repo = get_case_repository()
    case = repo.get_by_id(case_id)
    assert case is not None
    assert case.state == RecoveryState.ESCALATED
    entry = next(
        e for e in case.audit_trail if e.event_name == "payment.dispute.created"
    )
    assert entry.decision_inputs["dispute_id"] == "disp_1"
    assert entry.decision_inputs["reason"] == "fraudulent"


def test_dispute_created_on_recovered_case_logs_without_illegal_transition(
    client: TestClient,
) -> None:
    case_id = "case_dispute_recovered"
    payment_id = "pay_dispute_recovered"
    _seed_case(case_id, payment_id, amount_paise=90000)

    payload = _dispute_payload("payment.dispute.created", payment_id, "disp_2", 90000)
    resp = client.post("/api/webhooks/razorpay", json=payload)
    assert resp.status_code == 200
    assert resp.json()["action_taken"] == "ESCALATED"

    repo = get_case_repository()
    case = repo.get_by_id(case_id)
    assert case is not None
    # RECOVERED is terminal with no legal exit; state must not change.
    assert case.state == RecoveryState.RECOVERED
    assert any(e.event_name == "payment.dispute.created" for e in case.audit_trail)


def test_dispute_lost_reduces_recovered_amount(client: TestClient) -> None:
    case_id = "case_dispute_lost"
    payment_id = "pay_dispute_lost"
    _seed_case(case_id, payment_id, amount_paise=150000)

    payload = _dispute_payload(
        "payment.dispute.lost", payment_id, "disp_lost_1", 150000
    )
    resp = client.post("/api/webhooks/razorpay", json=payload)
    assert resp.json()["action_taken"] == "RECOVERED_AMOUNT_ADJUSTED"

    repo = get_case_repository()
    case = repo.get_by_id(case_id)
    assert case is not None
    assert case.recovered_amount_paise == 0
    assert case.net_recovered_value_paise == 0


def test_dispute_won_logs_without_amount_change(client: TestClient) -> None:
    case_id = "case_dispute_won"
    payment_id = "pay_dispute_won"
    _seed_case(case_id, payment_id, amount_paise=70000)

    payload = _dispute_payload("payment.dispute.won", payment_id, "disp_won_1", 70000)
    resp = client.post("/api/webhooks/razorpay", json=payload)
    assert resp.json()["action_taken"] == "DISPUTE_WON_LOGGED"

    repo = get_case_repository()
    case = repo.get_by_id(case_id)
    assert case is not None
    assert case.recovered_amount_paise == 70000


def test_dispute_under_review_and_action_required_escalate(client: TestClient) -> None:
    case_id = "case_dispute_action_required"
    payment_id = "pay_dispute_action_required"
    _seed_case(
        case_id,
        payment_id,
        amount_paise=40000,
        state=RecoveryState.OUTREACH_PENDING,
        recovered_amount_paise=0,
    )

    under_review = client.post(
        "/api/webhooks/razorpay",
        json=_dispute_payload(
            "payment.dispute.under_review", payment_id, "disp_review_1", 40000
        ),
    )
    assert under_review.json()["action_taken"] == "ESCALATED"

    action_required = client.post(
        "/api/webhooks/razorpay",
        json=_dispute_payload(
            "payment.dispute.action_required", payment_id, "disp_action_1", 40000
        ),
    )
    assert action_required.status_code == 200
    assert action_required.json()["action_taken"] == "ESCALATED"

    repo = get_case_repository()
    case = repo.get_by_id(case_id)
    assert case is not None
    assert case.state == RecoveryState.ESCALATED


def test_dispute_closed_is_informational(client: TestClient) -> None:
    case_id = "case_dispute_closed"
    payment_id = "pay_dispute_closed"
    _seed_case(
        case_id,
        payment_id,
        amount_paise=30000,
        state=RecoveryState.ESCALATED,
        recovered_amount_paise=0,
    )

    payload = _dispute_payload(
        "payment.dispute.closed", payment_id, "disp_closed_1", 30000
    )
    resp = client.post("/api/webhooks/razorpay", json=payload)
    assert resp.json()["action_taken"] == "LOGGED"

    repo = get_case_repository()
    case = repo.get_by_id(case_id)
    assert case is not None
    assert case.state == RecoveryState.ESCALATED


def test_redelivered_dispute_lost_does_not_double_subtract(client: TestClient) -> None:
    case_id = "case_dispute_lost_redeliver"
    payment_id = "pay_dispute_lost_redeliver"
    _seed_case(case_id, payment_id, amount_paise=100000)

    payload = _dispute_payload(
        "payment.dispute.lost", payment_id, "disp_lost_redeliver", 100000
    )

    first = client.post("/api/webhooks/razorpay", json=payload)
    assert first.json()["action_taken"] == "RECOVERED_AMOUNT_ADJUSTED"

    second = client.post("/api/webhooks/razorpay", json=payload)
    assert second.json()["action_taken"] == "ALREADY_RECORDED"

    repo = get_case_repository()
    case = repo.get_by_id(case_id)
    assert case is not None
    assert case.recovered_amount_paise == 0


def test_dispute_for_unknown_payment_does_not_crash_and_logs_globally(
    client: TestClient,
) -> None:
    payload = _dispute_payload(
        "payment.dispute.created", "pay_dispute_does_not_exist", "disp_orphan", 5000
    )
    resp = client.post("/api/webhooks/razorpay", json=payload)
    assert resp.status_code == 200
    assert resp.json()["action_taken"] == "NO_MATCHING_CASE"
