"""Tests for the persisted escalation_reason classification.

Replaces the earlier session's audit-trail-derived needs_human_judgment
helper (app/audit/escalation.py, deleted): escalation_reason is now set
explicitly at every call site that escalates a case, enforced by
transition_case itself, and queried directly rather than re-derived from
log content on every read.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from app.audit.models import RecoveryCase
from app.audit.state_machine import InvalidStateTransitionError, transition_case
from app.core.enums import (
    AuditActor,
    EscalationReason,
    ExperimentArm,
    PaymentRail,
    RecoveryState,
)
from app.detection.models import RawFailureEvent
from app.intervention.orchestrator import RecoveryOrchestrator

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def _make_case(case_id: str, *, amount_paise: int = 100000) -> RecoveryCase:
    return RecoveryCase(
        case_id=case_id,
        merchant_id="merch_esc_test",
        state=RecoveryState.ANALYSIS_QUEUED,
        experiment_arm=ExperimentArm.TREATMENT,
        amount_paise=amount_paise,
        currency="INR",
        failure_event=RawFailureEvent(
            event_id=f"evt_{case_id}",
            payment_id=f"pay_{case_id}",
            customer_id=f"cust_{case_id}",
            amount_paise=amount_paise,
            currency="INR",
            payment_rail=PaymentRail.UPI,
            error_code="GATEWAY_ERROR",
            occurred_at=datetime.now(UTC),
        ),
    )


def test_transition_case_rejects_escalation_without_reason() -> None:
    """The invariant this whole change rests on: a caller cannot escalate a
    case without saying why. This must be a hard error, not a null column
    discovered later.
    """
    case = _make_case("case_no_reason")
    with pytest.raises(InvalidStateTransitionError, match="escalation_reason"):
        transition_case(
            case,
            to_state=RecoveryState.ESCALATED,
            actor=AuditActor.SYSTEM,
            reason="test escalation with no classification",
        )


def test_transition_case_persists_escalation_reason() -> None:
    case = _make_case("case_with_reason")
    transition_case(
        case,
        to_state=RecoveryState.ESCALATED,
        actor=AuditActor.SYSTEM,
        reason="test escalation",
        escalation_reason=EscalationReason.HUMAN_JUDGMENT,
    )
    assert case.state == RecoveryState.ESCALATED
    assert case.escalation_reason == EscalationReason.HUMAN_JUDGMENT


def test_non_escalated_case_has_no_escalation_reason() -> None:
    """A case that never escalates must never carry a stale/leftover
    escalation_reason from an unrelated code path.
    """
    case = _make_case("case_never_escalated")
    transition_case(
        case,
        to_state=RecoveryState.IN_DUNNING,
        actor=AuditActor.SYSTEM,
        reason="normal dunning progression",
    )
    assert case.state == RecoveryState.IN_DUNNING
    assert case.escalation_reason is None

    transition_case(
        case,
        to_state=RecoveryState.RECOVERED,
        actor=AuditActor.SYSTEM,
        reason="payment captured",
    )
    assert case.escalation_reason is None


def test_escalation_reason_does_not_leak_across_transitions() -> None:
    """A case escalated once, then moved back to an active state, must not
    keep reporting the old escalation_reason -- it is only meaningful while
    state == ESCALATED.
    """
    case = _make_case("case_reescalated")
    transition_case(
        case,
        to_state=RecoveryState.ESCALATED,
        actor=AuditActor.SYSTEM,
        reason="first escalation",
        escalation_reason=EscalationReason.SYSTEM_ERROR,
    )
    first_reason = case.escalation_reason
    assert first_reason == EscalationReason.SYSTEM_ERROR

    transition_case(
        case,
        to_state=RecoveryState.IN_DUNNING,
        actor=AuditActor.HUMAN_OPERATOR,
        reason="operator resumed after fixing the integration",
    )
    # escalation_reason is not cleared on exit today (the column simply
    # becomes meaningless outside ESCALATED); re-escalating must overwrite it
    # correctly regardless of what is left over from the prior escalation.
    transition_case(
        case,
        to_state=RecoveryState.ESCALATED,
        actor=AuditActor.POLICY_GATE,
        reason="second escalation, different reason",
        escalation_reason=EscalationReason.HUMAN_JUDGMENT,
    )
    second_reason = case.escalation_reason
    assert second_reason == EscalationReason.HUMAN_JUDGMENT


@pytest.mark.anyio
async def test_human_judgment_escalation_via_manual_escalation_plan() -> None:
    """Site: orchestrator._execute_plan, MANUAL_ESCALATION exec-time branch."""
    orchestrator = RecoveryOrchestrator()
    event = RawFailureEvent(
        event_id="evt_hj_manual",
        payment_id="pay_hj_manual",
        customer_id="cust_hj_manual",
        amount_paise=150000,
        currency="INR",
        payment_rail=PaymentRail.CARD,
        error_code="SUSPECTED_FRAUD_HOLD",
        error_reason="Risk engine flagged anomaly on card authorization",
        occurred_at=datetime.now(UTC),
    )
    case = await orchestrator.process_failure_event(
        event, experiment_arm_override=ExperimentArm.TREATMENT
    )
    assert case.state == RecoveryState.ESCALATED
    assert case.escalation_reason == EscalationReason.HUMAN_JUDGMENT


def test_disputes_escalate_as_human_judgment(client: TestClient) -> None:
    """Site: webhooks.py _escalate_case helper, called only for dispute events."""
    fail_payload = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_esc_dispute_1",
                    "amount": 500000,
                    "currency": "INR",
                    "customer_id": "cust_esc_dispute_1",
                    "error_code": "GATEWAY_ERROR",
                    "error_reason": "server_error",
                }
            }
        },
    }
    res = client.post("/api/webhooks/razorpay", json=fail_payload)
    case_id = res.json()["case_id"]

    dispute_payload = {
        "event": "payment.dispute.created",
        "payload": {
            "payment": {"entity": {"id": "pay_esc_dispute_1"}},
            "dispute": {
                "entity": {
                    "id": "disp_esc_1",
                    "amount": 500000,
                    "payment_id": "pay_esc_dispute_1",
                    "reason_code": "fraudulent",
                }
            },
        },
    }
    client.post("/api/webhooks/razorpay", json=dispute_payload)

    case = client.get(f"/api/cases/{case_id}").json()
    assert case["state"] == "ESCALATED"
    assert case["escalation_reason"] == "HUMAN_JUDGMENT"


@pytest.mark.anyio
async def test_escalated_tab_filter_matches_human_judgment_count(
    client: TestClient,
) -> None:
    """Pagination correctness: total must equal the actual filtered count, not
    just what fits on the page, and must stay correct at any limit.
    """
    orchestrator = RecoveryOrchestrator()
    human_judgment_event = RawFailureEvent(
        event_id="evt_page_hj",
        payment_id="pay_page_hj",
        customer_id="cust_page_hj",
        amount_paise=150000,
        currency="INR",
        payment_rail=PaymentRail.CARD,
        error_code="SUSPECTED_FRAUD_HOLD",
        error_reason="Risk engine flagged anomaly",
        occurred_at=datetime.now(UTC),
    )
    await orchestrator.process_failure_event(
        human_judgment_event, experiment_arm_override=ExperimentArm.TREATMENT
    )

    # limit=1: total must still reflect the full filtered count, not the page size.
    res = client.get(
        "/api/cases?state=ESCALATED&escalation_reason=HUMAN_JUDGMENT&limit=1"
    )
    data = res.json()
    assert data["total"] >= 1
    assert len(data["items"]) == 1
    for item in data["items"]:
        assert item["escalation_reason"] == "HUMAN_JUDGMENT"

    # A wide limit must return exactly `total` matching rows, all HUMAN_JUDGMENT.
    res_all = client.get(
        "/api/cases?state=ESCALATED&escalation_reason=HUMAN_JUDGMENT&limit=500"
    )
    data_all = res_all.json()
    assert data_all["total"] == len(data_all["items"])
    assert all(
        item["escalation_reason"] == "HUMAN_JUDGMENT" for item in data_all["items"]
    )


def test_escalations_and_failed_executions_queues_do_not_overlap(
    client: TestClient,
) -> None:
    """/escalations returns only HUMAN_JUDGMENT cases; /failed-executions
    returns only SYSTEM_ERROR cases; no case appears in both.
    """
    res_escalations = client.get("/api/analytics/escalations")
    res_failed = client.get("/api/analytics/failed-executions")
    assert res_escalations.status_code == 200
    assert res_failed.status_code == 200

    escalation_case_ids = {item["case_id"] for item in res_escalations.json()}
    failed_case_ids = {item["case_id"] for item in res_failed.json()}
    assert escalation_case_ids.isdisjoint(failed_case_ids)
