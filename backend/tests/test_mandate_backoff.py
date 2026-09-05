"""Tests for the mandate-retry escalating backoff schedule and its gating."""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx2
import pytest

from app.audit.models import RecoveryCase
from app.audit.repository import CaseRepository
from app.core.config import get_settings
from app.core.enums import (
    ExperimentArm,
    InterventionType,
    OutreachChannel,
    PaymentRail,
    PolicyCheckResult,
    RecoveryState,
)
from app.detection.models import RawFailureEvent
from app.intervention.mandate_backoff import compute_mandate_backoff_hours
from app.intervention.models import InterventionPlan, MerchantPolicy
from app.intervention.orchestrator import RecoveryOrchestrator
from app.intervention.policy_gate import PolicyGate
from app.intervention.tools.mandate_retry import MandateRetryTool


def _isolated_repo() -> CaseRepository:
    return CaseRepository(
        storage_path=Path(tempfile.mkdtemp(prefix="mandate_backoff_test_")) / "test.db"
    )


def _mock_mandate_retry_tool() -> MandateRetryTool:
    """A MandateRetryTool wired to a mock transport that always charges successfully."""

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status_code=200, json={"id": "chg_backoff_test"})

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    return MandateRetryTool(client=client)


def _mandate_event(
    payment_id: str, rail: PaymentRail, amount_paise: int = 100000
) -> RawFailureEvent:
    return RawFailureEvent(
        event_id=f"evt_{payment_id}",
        payment_id=payment_id,
        customer_id=f"cust_{payment_id}",
        amount_paise=amount_paise,
        payment_rail=rail,
        error_code="BAD_REQUEST_ERROR",
        error_reason="bank_cutoff_in_progress",
        npci_response_code="XT",
        occurred_at=datetime.now(UTC),
    )


def _mandate_case(
    rail: PaymentRail,
    retry_count: int,
    last_attempt_at: datetime | None,
) -> RecoveryCase:
    return RecoveryCase(
        case_id="case_mandate_test",
        amount_paise=100000,
        failure_event=_mandate_event("pay_mandate_test", rail),
        retry_count=retry_count,
        attempts_count=retry_count,
        last_attempt_at=last_attempt_at,
        experiment_arm=ExperimentArm.TREATMENT,
    )


def _mandate_plan(scheduled_at: datetime) -> InterventionPlan:
    return InterventionPlan(
        plan_id="plan_mandate_test",
        case_id="case_mandate_test",
        intervention_type=InterventionType.SMART_RETRY,
        scheduled_at=scheduled_at,
        idempotency_key="idem_mandate_test",
        rationale="Mandate retry",
    )


def test_compute_mandate_backoff_hours_escalates_by_attempt() -> None:
    policy = MerchantPolicy()
    assert (
        compute_mandate_backoff_hours(policy, PaymentRail.UPI_AUTOPAY, 1)
        == policy.mandate_retry_backoff_hours[0]
    )
    assert (
        compute_mandate_backoff_hours(policy, PaymentRail.UPI_AUTOPAY, 2)
        == policy.mandate_retry_backoff_hours[1]
    )
    assert compute_mandate_backoff_hours(
        policy, PaymentRail.UPI_AUTOPAY, 2
    ) > compute_mandate_backoff_hours(policy, PaymentRail.UPI_AUTOPAY, 1)


def test_compute_mandate_backoff_hours_caps_at_last_schedule_entry() -> None:
    policy = MerchantPolicy()
    last = policy.mandate_retry_backoff_hours[-1]
    assert compute_mandate_backoff_hours(policy, PaymentRail.UPI_AUTOPAY, 50) == last


def test_enach_uses_its_own_longer_schedule_than_upi_autopay() -> None:
    policy = MerchantPolicy()
    assert (
        compute_mandate_backoff_hours(policy, PaymentRail.ENACH, 1)
        == policy.enach_retry_backoff_hours[0]
    )
    assert compute_mandate_backoff_hours(
        policy, PaymentRail.ENACH, 1
    ) > compute_mandate_backoff_hours(policy, PaymentRail.UPI_AUTOPAY, 1)


def test_policy_gate_blocks_mandate_retry_before_first_backoff_elapses() -> None:
    gate = PolicyGate()
    policy = MerchantPolicy(mandate_retry_backoff_hours=[4, 24, 72])
    now = datetime.now(UTC)
    case = _mandate_case(PaymentRail.UPI_AUTOPAY, retry_count=0, last_attempt_at=now)
    plan = _mandate_plan(scheduled_at=now + timedelta(hours=2))

    evaluation = gate.evaluate(case, plan, policy)
    assert evaluation.result == PolicyCheckResult.BLOCKED_COOLDOWN
    assert not evaluation.is_allowed
    assert "Mandate retry backoff" in evaluation.reason


def test_policy_gate_allows_mandate_retry_after_first_backoff_elapses() -> None:
    gate = PolicyGate()
    policy = MerchantPolicy(mandate_retry_backoff_hours=[4, 24, 72])
    now = datetime.now(UTC)
    case = _mandate_case(PaymentRail.UPI_AUTOPAY, retry_count=0, last_attempt_at=now)
    plan = _mandate_plan(scheduled_at=now + timedelta(hours=5))

    evaluation = gate.evaluate(case, plan, policy)
    assert evaluation.is_allowed


def test_policy_gate_requires_longer_wait_on_second_mandate_retry() -> None:
    """Attempt 2's backoff (24h) is longer than attempt 1's (4h), so a gap that
    clears the first step must still block the second.
    """
    gate = PolicyGate()
    policy = MerchantPolicy(mandate_retry_backoff_hours=[4, 24, 72])
    now = datetime.now(UTC)
    case = _mandate_case(PaymentRail.UPI_AUTOPAY, retry_count=1, last_attempt_at=now)
    plan = _mandate_plan(scheduled_at=now + timedelta(hours=5))

    evaluation = gate.evaluate(case, plan, policy)
    assert evaluation.result == PolicyCheckResult.BLOCKED_COOLDOWN

    later_plan = _mandate_plan(scheduled_at=now + timedelta(hours=25))
    later_evaluation = gate.evaluate(case, later_plan, policy)
    assert later_evaluation.is_allowed


def test_generic_cooldown_path_is_unaffected_for_non_mandate_interventions() -> None:
    """A customer-facing nudge still uses the flat min_cooldown_hours, proving
    the mandate backoff branch is scoped to retry interventions only.
    """
    gate = PolicyGate()
    policy = MerchantPolicy(min_cooldown_hours=24, mandate_retry_backoff_hours=[1])
    now = datetime.now(UTC)
    case = _mandate_case(PaymentRail.UPI_AUTOPAY, retry_count=0, last_attempt_at=now)
    plan = InterventionPlan(
        plan_id="plan_nudge_test",
        case_id=case.case_id,
        intervention_type=InterventionType.CUSTOMER_NUDGE,
        channel=OutreachChannel.WHATSAPP,
        scheduled_at=now + timedelta(hours=2),
        idempotency_key="idem_nudge_test",
        rationale="Nudge",
    )

    evaluation = gate.evaluate(case, plan, policy)
    assert evaluation.result == PolicyCheckResult.BLOCKED_COOLDOWN
    assert "Cooldown constraint violated" in evaluation.reason


@pytest.mark.anyio
async def test_orchestrator_schedules_repeat_mandate_retry_using_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second SMART_RETRY attempt is scheduled using the escalating backoff,
    not the classifier's flat first-attempt delay.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_backoff")
    monkeypatch.setattr(settings, "razorpay_key_secret", "backoff_secret")

    repo = _isolated_repo()
    policy = MerchantPolicy(mandate_retry_backoff_hours=[4, 24, 72], max_attempts=5)
    orchestrator = RecoveryOrchestrator(
        repository=repo, policy=policy, mandate_retry_tool=_mock_mandate_retry_tool()
    )

    event = _mandate_event("pay_backoff_1", PaymentRail.UPI_AUTOPAY)
    event = event.model_copy(update={"error_reason": "insufficient_funds"})

    case = await orchestrator.process_failure_event(
        event, experiment_arm_override=ExperimentArm.TREATMENT
    )
    assert case.retry_count == 1
    assert case.due_at is not None

    case.state = RecoveryState.ANALYSIS_QUEUED
    repo.save(case)

    case = await orchestrator.process_failure_event(
        event, experiment_arm_override=ExperimentArm.TREATMENT
    )
    assert case.retry_count == 2
    assert case.due_at is not None

    second_delay_hours = (case.due_at - datetime.now(UTC)).total_seconds() / 3600
    assert second_delay_hours == pytest.approx(
        policy.mandate_retry_backoff_hours[1], abs=0.1
    )


@pytest.mark.anyio
async def test_mandate_retry_case_exceeding_max_attempts_is_capped_not_retried() -> (
    None
):
    """Bounded stopping rules still apply on top of the backoff schedule: once
    max_attempts is reached the case halts rather than retrying indefinitely.
    """
    repo = _isolated_repo()
    policy = MerchantPolicy(mandate_retry_backoff_hours=[4, 24, 72], max_attempts=2)
    orchestrator = RecoveryOrchestrator(repository=repo, policy=policy)

    event = _mandate_event("pay_backoff_capped", PaymentRail.UPI_AUTOPAY)
    event = event.model_copy(update={"error_reason": "insufficient_funds"})
    case = RecoveryCase(
        case_id="case_backoff_capped",
        merchant_id=policy.merchant_id,
        failure_event=event,
        amount_paise=event.amount_paise,
        currency=event.currency,
        experiment_arm=ExperimentArm.TREATMENT,
        state=RecoveryState.ANALYSIS_QUEUED,
        attempts_count=2,
        retry_count=2,
    )
    repo.save(case)

    result = await orchestrator.process_failure_event(
        event, experiment_arm_override=ExperimentArm.TREATMENT
    )

    assert result.state == RecoveryState.FAILED
    assert result.retry_count == 2  # unchanged: no further retry was attempted
    events = [e.event_name for e in result.audit_trail]
    assert "intervention.blocked" in events
