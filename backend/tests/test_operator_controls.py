"""End-to-end verification contract tests for Operator Controls Spec."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.audit.models import RecoveryCase
from app.audit.repository import get_case_repository
from app.core.enums import (
    ExperimentArm,
    PaymentRail,
    RecoveryState,
)
from app.core.operator import (
    OperatorMode,
    get_operator_mode,
    set_operator_mode,
)
from app.detection.models import RawFailureEvent
from app.intervention.orchestrator import get_recovery_orchestrator


@pytest.mark.anyio
async def test_operator_mode_persistence_and_audit() -> None:
    """Test switching autonomy mode persists state and writes audit log."""
    set_operator_mode(OperatorMode.FULL_AUTONOMY, reason="Reset to full")
    assert get_operator_mode() == OperatorMode.FULL_AUTONOMY

    state = set_operator_mode(
        OperatorMode.HUMAN_IN_THE_LOOP,
        reason="Testing HITL transition",
        updated_by="test_operator",
    )
    assert state.mode == OperatorMode.HUMAN_IN_THE_LOOP
    assert get_operator_mode() == OperatorMode.HUMAN_IN_THE_LOOP

    # Verify audit record
    repo = get_case_repository()
    cur = repo._store._conn.cursor()
    cur.execute(
        "SELECT * FROM audit WHERE event_name = 'operator.mode_changed' ORDER BY timestamp DESC LIMIT 1;"
    )
    row = cur.fetchone()
    assert row is not None
    assert row["actor"] == "HUMAN_OPERATOR"


@pytest.mark.anyio
async def test_monitoring_only_circuit_breaker_holds_interventions() -> None:
    """Test MONITORING_ONLY mode holds outbound interventions without sending touches."""
    set_operator_mode(OperatorMode.MONITORING_ONLY, reason="Engage circuit breaker")
    orchestrator = get_recovery_orchestrator()

    event = RawFailureEvent(
        event_id=f"evt_cb_{uuid4().hex[:8]}",
        payment_id=f"pay_cb_{uuid4().hex[:8]}",
        customer_id="cust_circuit_breaker",
        amount_paise=250000,
        currency="INR",
        payment_rail=PaymentRail.UPI,
        error_code="INTERNAL_SERVER_ERROR",
        error_reason="Bank timeout",
        occurred_at=datetime.now(UTC),
    )

    case = await orchestrator.process_failure(
        event, experiment_arm_override=ExperimentArm.TREATMENT
    )
    # Interventions must be held
    assert case.touches_count == 0
    held_events = [
        e
        for e in case.audit_trail
        if e.event_name == "intervention.held_circuit_breaker"
    ]
    assert len(held_events) > 0
    assert "circuit breaker" in (held_events[0].notes or "").lower()

    # Reset
    set_operator_mode(OperatorMode.FULL_AUTONOMY, reason="Reset to full")


@pytest.mark.anyio
async def test_hitl_mode_pauses_for_human_approval() -> None:
    """Test HUMAN_IN_THE_LOOP mode pauses before executing active interventions."""
    set_operator_mode(OperatorMode.HUMAN_IN_THE_LOOP, reason="Testing HITL gate")
    orchestrator = get_recovery_orchestrator()

    event = RawFailureEvent(
        event_id=f"evt_hitl_{uuid4().hex[:8]}",
        payment_id=f"pay_hitl_{uuid4().hex[:8]}",
        customer_id="cust_hitl_test",
        amount_paise=150000,
        currency="INR",
        payment_rail=PaymentRail.UPI_AUTOPAY,
        error_code="AP15",
        error_reason="Insufficient balance",
        occurred_at=datetime.now(UTC),
    )

    case = await orchestrator.process_failure(
        event, experiment_arm_override=ExperimentArm.TREATMENT
    )
    assert case.state == RecoveryState.ESCALATED
    pending_events = [
        e
        for e in case.audit_trail
        if e.event_name == "intervention.pending_human_approval"
    ]
    assert len(pending_events) > 0

    # Reset
    set_operator_mode(OperatorMode.FULL_AUTONOMY, reason="Reset to full")


@pytest.mark.anyio
async def test_server_side_case_filtering_and_sorting() -> None:
    """Test parameterized query filters and sorting in relational store."""
    repo = get_case_repository()
    now = datetime.now(UTC)
    unique_merchant_id = f"merch_filter_{uuid4().hex[:6]}"

    # Seed distinct cases
    case1 = RecoveryCase(
        case_id=f"case_test_filter_1_{uuid4().hex[:6]}",
        merchant_id=unique_merchant_id,
        state=RecoveryState.RECOVERED,
        experiment_arm=ExperimentArm.TREATMENT,
        amount_paise=250000,
        currency="INR",
        recovered_amount_paise=250000,
        failure_event=RawFailureEvent(
            event_id=f"evt_f1_{uuid4().hex[:6]}",
            payment_id=f"pay_f1_{uuid4().hex[:6]}",
            customer_id="cust_alpha",
            amount_paise=250000,
            currency="INR",
            payment_rail=PaymentRail.UPI,
            error_code="AP15",
            error_reason="Insufficient funds in account",
            occurred_at=now,
        ),
    )
    repo.save(case1)

    case2 = RecoveryCase(
        case_id=f"case_test_filter_2_{uuid4().hex[:6]}",
        merchant_id=unique_merchant_id,
        state=RecoveryState.IN_DUNNING,
        experiment_arm=ExperimentArm.HOLDOUT_CONTROL,
        amount_paise=1000000,
        currency="INR",
        recovered_amount_paise=0,
        failure_event=RawFailureEvent(
            event_id=f"evt_f2_{uuid4().hex[:6]}",
            payment_id=f"pay_f2_{uuid4().hex[:6]}",
            customer_id="cust_beta",
            amount_paise=1000000,
            currency="INR",
            payment_rail=PaymentRail.CARD,
            error_code="GATEWAY_ERROR",
            error_reason="Issuer 3DS authorization failed",
            occurred_at=now,
        ),
    )
    repo.save(case2)

    # Test filtering by rail
    upi_cases = repo.list_cases(merchant_id=unique_merchant_id, payment_rails=["UPI"])
    assert len(upi_cases) == 1
    assert upi_cases[0].case_id == case1.case_id

    # Test filtering by recovered
    rec_cases = repo.list_cases(merchant_id=unique_merchant_id, recovered=True)
    assert len(rec_cases) == 1
    assert rec_cases[0].case_id == case1.case_id

    # Test free-text q
    search_cases = repo.list_cases(merchant_id=unique_merchant_id, q="authorization")
    assert len(search_cases) == 1
    assert search_cases[0].case_id == case2.case_id

    # Test count accuracy
    assert repo.count(merchant_id=unique_merchant_id) == 2
    assert repo.count(merchant_id=unique_merchant_id, payment_rails=["CARD"]) == 1
