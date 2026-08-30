"""Tests for end-to-end recovery orchestration."""

from datetime import UTC, datetime

import pytest

from app.audit.repository import CaseRepository
from app.core.enums import ExperimentArm, PaymentRail, RecoveryState
from app.detection.models import RawFailureEvent
from app.intervention.orchestrator import RecoveryOrchestrator


@pytest.mark.anyio
async def test_orchestrator_transient_window_passive_retry() -> None:
    repo = CaseRepository()
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
    repo = CaseRepository()
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
    repo = CaseRepository()
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
    repo = CaseRepository()
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
