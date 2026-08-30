"""Tests for state machine transitions and audit logging."""

from datetime import UTC, datetime

import pytest

from app.audit.models import RecoveryCase
from app.audit.state_machine import InvalidStateTransitionError, transition_case
from app.core.enums import AuditActor, RecoveryState
from app.detection.models import RawFailureEvent


def test_legal_lifecycle_transitions() -> None:
    event = RawFailureEvent(
        event_id="evt_sm",
        payment_id="pay_sm",
        customer_id="cust_sm",
        amount_paise=500000,
        error_code="BAD_REQUEST_ERROR",
        occurred_at=datetime.now(UTC),
    )
    case = RecoveryCase(
        case_id="case_sm",
        amount_paise=500000,
        failure_event=event,
        state=RecoveryState.ANALYSIS_QUEUED,
    )

    case = transition_case(
        case,
        to_state=RecoveryState.IN_DUNNING,
        actor=AuditActor.SYSTEM,
        reason="Diagnosis and initial recovery plan formulated.",
    )
    assert case.state == RecoveryState.IN_DUNNING
    assert len(case.audit_trail) == 1
    assert case.audit_trail[0].actor == AuditActor.SYSTEM

    case = transition_case(
        case,
        to_state=RecoveryState.RETRY_SCHEDULED,
        actor=AuditActor.POLICY_GATE,
        reason="Scheduled delayed auto-retry after bank window.",
    )
    assert case.state == RecoveryState.RETRY_SCHEDULED
    assert len(case.audit_trail) == 2

    case.recovered_amount_paise = 500000
    case.retry_count = 1
    case = transition_case(
        case,
        to_state=RecoveryState.RECOVERED,
        actor=AuditActor.GATEWAY_WEBHOOK,
        reason="Payment successfully captured on auto-retry.",
        cost_incurred_paise=250,
    )
    assert case.state == RecoveryState.RECOVERED
    assert case.state.is_terminal is True
    assert len(case.audit_trail) == 3
    assert case.net_recovered_value_paise == 499750


def test_terminal_state_immutability_raises() -> None:
    event = RawFailureEvent(
        event_id="evt_term",
        payment_id="pay_term",
        customer_id="cust_term",
        amount_paise=200000,
        error_code="BAD_REQUEST_ERROR",
        occurred_at=datetime.now(UTC),
    )
    case = RecoveryCase(
        case_id="case_term",
        amount_paise=200000,
        failure_event=event,
        state=RecoveryState.RECOVERED,
    )

    with pytest.raises(InvalidStateTransitionError, match="terminal state"):
        transition_case(
            case,
            to_state=RecoveryState.IN_DUNNING,
            actor=AuditActor.AGENT_LLM,
            reason="Illegal attempt to reopen a terminal recovered case",
        )
