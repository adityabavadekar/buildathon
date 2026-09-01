"""Tests for end-to-end recovery orchestration."""

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.audit.repository import CaseRepository
from app.core.enums import ExperimentArm, PaymentRail, RecoveryState
from app.detection.models import RawFailureEvent
from app.intervention.orchestrator import RecoveryOrchestrator


def _isolated_repo() -> CaseRepository:
    """Return a CaseRepository backed by a fresh temp DB per test.

    Using the shared default ``data/recovery_engine.db`` makes these tests
    non-reproducible on re-runs: a fixed payment_id persists its terminal state
    (e.g. RECOVERED) and is returned on the next run, breaking the state
    assertion. A temp store starts empty every time.
    """
    return CaseRepository(
        storage_path=Path(tempfile.mkdtemp(prefix="orch_test_")) / "test.db"
    )


@pytest.mark.anyio
async def test_orchestrator_transient_window_passive_retry() -> None:
    repo = _isolated_repo()
    orchestrator = RecoveryOrchestrator(repository=repo)

    event = RawFailureEvent(
        event_id="evt_orch_1",
        payment_id="pay_orch_1",
        customer_id="cust_orch_1",
        amount_paise=200000,
        payment_rail=PaymentRail.UPI_AUTOPAY,
        error_code="BAD_REQUEST_ERROR",
        error_reason="bank_cutoff_in_progress",
        npci_response_code="XT",
        occurred_at=datetime.now(UTC),
    )

    case = await orchestrator.process_failure_event(
        event, experiment_arm_override=ExperimentArm.TREATMENT
    )
    assert case.state == RecoveryState.RETRY_SCHEDULED
    assert case.retry_count == 1
    assert case.touches_count == 1
    assert len(case.audit_trail) >= 2


@pytest.mark.anyio
async def test_orchestrator_checkout_dropoff_incentivized_link() -> None:
    repo = _isolated_repo()
    orchestrator = RecoveryOrchestrator(repository=repo)

    event = RawFailureEvent(
        event_id="evt_orch_2",
        payment_id="pay_orch_2",
        customer_id="cust_orch_2",
        amount_paise=100000,
        payment_rail=PaymentRail.UPI,
        error_code="BAD_REQUEST_ERROR",
        error_step="payment_authentication",
        error_reason="otp_timeout",
        occurred_at=datetime.now(UTC),
    )

    case = await orchestrator.process_failure_event(
        event, experiment_arm_override=ExperimentArm.TREATMENT
    )
    assert case.state == RecoveryState.OUTREACH_PENDING
    assert case.discount_paise_granted == 5000  # 5% discount (500 bps)
    assert case.touches_count == 1


@pytest.mark.anyio
async def test_orchestrator_idempotency_returns_existing_case() -> None:
    repo = _isolated_repo()
    orchestrator = RecoveryOrchestrator(repository=repo)

    event = RawFailureEvent(
        event_id="evt_orch_3",
        payment_id="pay_orch_3",
        customer_id="cust_orch_3",
        amount_paise=100000,
        payment_rail=PaymentRail.CARD,
        error_code="BAD_REQUEST_ERROR",
        error_reason="insufficient_funds",
        occurred_at=datetime.now(UTC),
    )

    case1 = await orchestrator.process_failure_event(
        event, experiment_arm_override=ExperimentArm.TREATMENT
    )
    case2 = await orchestrator.process_failure_event(
        event, experiment_arm_override=ExperimentArm.TREATMENT
    )

    assert case1.case_id == case2.case_id


@pytest.mark.anyio
async def test_orchestrator_payment_captured_resolution() -> None:
    repo = _isolated_repo()
    orchestrator = RecoveryOrchestrator(repository=repo)

    event = RawFailureEvent(
        event_id="evt_orch_4",
        payment_id="pay_orch_4",
        customer_id="cust_orch_4",
        amount_paise=500000,
        payment_rail=PaymentRail.UPI_AUTOPAY,
        error_code="BAD_REQUEST_ERROR",
        error_reason="bank_cutoff_in_progress",
        npci_response_code="XT",
        occurred_at=datetime.now(UTC),
    )

    case = await orchestrator.process_failure_event(
        event, experiment_arm_override=ExperimentArm.TREATMENT
    )
    assert case.state == RecoveryState.RETRY_SCHEDULED

    # Payment captured on recovery retry
    resolved = orchestrator.process_payment_captured("pay_orch_4", 500000)
    assert resolved is not None
    assert resolved.state == RecoveryState.RECOVERED
    assert (
        resolved.net_recovered_value_paise == 499750
    )  # 500000 - 250 (gateway retry cost)


@pytest.mark.anyio
async def test_orchestrator_unclassified_routes_to_escalated() -> None:
    repo = _isolated_repo()
    orchestrator = RecoveryOrchestrator(repository=repo)

    event = RawFailureEvent(
        event_id="evt_orch_esc_1",
        payment_id="pay_orch_esc_1",
        customer_id="cust_orch_esc_1",
        amount_paise=150000,
        payment_rail=PaymentRail.CARD,
        error_code="SUSPECTED_FRAUD_HOLD",
        error_reason="Risk engine flagged anomaly on card authorization",
        occurred_at=datetime.now(UTC),
    )

    case = await orchestrator.process_failure_event(
        event, experiment_arm_override=ExperimentArm.TREATMENT
    )
    assert case.state == RecoveryState.ESCALATED
    assert case.touches_count == 0  # Escalation does not increment customer touches
    events = [e.event_name for e in case.audit_trail]
    assert "intervention.escalated" in events


@pytest.mark.anyio
async def test_orchestrator_high_value_routes_to_escalated() -> None:
    repo = _isolated_repo()
    orchestrator = RecoveryOrchestrator(repository=repo)

    # 15,000,000 paise = INR 1,50,000 (above default 10,000,000 paise threshold)
    event = RawFailureEvent(
        event_id="evt_orch_esc_2",
        payment_id="pay_orch_esc_2",
        customer_id="cust_orch_esc_2",
        amount_paise=15000000,
        payment_rail=PaymentRail.B2B_INVOICE,
        error_code="OVERDUE_RECEIVABLE",
        error_reason="Invoice overdue",
        occurred_at=datetime.now(UTC),
    )

    case = await orchestrator.process_failure_event(
        event, experiment_arm_override=ExperimentArm.TREATMENT
    )
    assert case.state == RecoveryState.ESCALATED
    assert case.touches_count == 0
    events = [e.event_name for e in case.audit_trail]
    assert "intervention.escalated" in events
