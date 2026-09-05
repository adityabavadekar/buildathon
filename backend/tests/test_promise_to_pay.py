"""Tests for the promise-to-pay tracker: P2P_WAITING transition, scheduled
follow-up job, missed-promise escalation, and recovered-before-followup no-op.
"""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.audit.repository import CaseRepository
from app.audit.state_machine import transition_case
from app.core.constants import P2P_MAX_REMINDER_ATTEMPTS
from app.core.enums import AuditActor, ExperimentArm, PaymentRail, RecoveryState
from app.detection.models import RawFailureEvent
from app.intervention.orchestrator import RecoveryOrchestrator
from app.worker.executor import DueJobExecutor


def _isolated_repo() -> CaseRepository:
    return CaseRepository(
        storage_path=Path(tempfile.mkdtemp(prefix="p2p_test_")) / "test.db"
    )


def _p2p_event(
    payment_id: str, customer_id: str, amount_paise: int = 300000
) -> RawFailureEvent:
    return RawFailureEvent(
        event_id=f"evt_{payment_id}",
        payment_id=payment_id,
        customer_id=customer_id,
        amount_paise=amount_paise,
        payment_rail=PaymentRail.UPI,
        error_code="P2P_PROMISED",
        error_reason="customer promised to pay after salary credit",
        occurred_at=datetime.now(UTC),
    )


@pytest.mark.anyio
async def test_p2p_followup_transitions_to_waiting_with_scheduled_job() -> None:
    repo = _isolated_repo()
    orchestrator = RecoveryOrchestrator(repository=repo)

    case = await orchestrator.process_failure_event(
        _p2p_event("pay_p2p_1", "cust_p2p_1"),
        experiment_arm_override=ExperimentArm.TREATMENT,
    )

    assert case.state == RecoveryState.P2P_WAITING
    assert case.promised_payment_date is not None
    assert case.outreach_count == 1

    due_jobs = repo.fetch_due_jobs(limit=10)
    assert not any(j.job_type == "P2P_FOLLOWUP_CHECK" for j in due_jobs)

    queued = repo.fetch_queued_jobs(limit=10)
    followup_jobs = [j for j in queued if j.job_type == "P2P_FOLLOWUP_CHECK"]
    assert len(followup_jobs) == 1
    assert followup_jobs[0].case_id == case.case_id


@pytest.mark.anyio
async def test_missed_promise_sends_one_reminder_then_escalates() -> None:
    repo = _isolated_repo()
    orchestrator = RecoveryOrchestrator(repository=repo)
    executor = DueJobExecutor()
    executor.repo = repo
    executor.orchestrator = orchestrator

    case = await orchestrator.process_failure_event(
        _p2p_event("pay_p2p_2", "cust_p2p_2"),
        experiment_arm_override=ExperimentArm.TREATMENT,
    )
    assert case.state == RecoveryState.P2P_WAITING

    # Force the scheduled check job due now instead of waiting the real window.
    queued = repo.fetch_queued_jobs(limit=10)
    followup_job = next(j for j in queued if j.job_type == "P2P_FOLLOWUP_CHECK")
    followup_job.due_at = datetime.now(UTC) - timedelta(seconds=5)
    repo.schedule_job(followup_job)

    executed = await executor.execute_due_jobs_once(limit=10)
    assert executed >= 1

    after_reminder = repo.get_by_id(case.case_id)
    assert after_reminder is not None
    assert after_reminder.state == RecoveryState.P2P_PROMISED
    assert after_reminder.p2p_reminder_count == P2P_MAX_REMINDER_ATTEMPTS

    # Fire the reminder's own follow-up job; the bound is exhausted, so escalate.
    queued_again = repo.fetch_queued_jobs(limit=10)
    second_job = next(j for j in queued_again if j.job_type == "P2P_FOLLOWUP_CHECK")
    second_job.due_at = datetime.now(UTC) - timedelta(seconds=5)
    repo.schedule_job(second_job)

    executed_again = await executor.execute_due_jobs_once(limit=10)
    assert executed_again >= 1

    after_escalation = repo.get_by_id(case.case_id)
    assert after_escalation is not None
    assert after_escalation.state == RecoveryState.ESCALATED
    events = [e.event_name for e in after_escalation.audit_trail]
    assert "p2p.promise_missed_escalated" in events


@pytest.mark.anyio
async def test_recovered_before_followup_is_noop() -> None:
    repo = _isolated_repo()
    orchestrator = RecoveryOrchestrator(repository=repo)
    executor = DueJobExecutor()
    executor.repo = repo
    executor.orchestrator = orchestrator

    case = await orchestrator.process_failure_event(
        _p2p_event("pay_p2p_3", "cust_p2p_3"),
        experiment_arm_override=ExperimentArm.TREATMENT,
    )
    assert case.state == RecoveryState.P2P_WAITING

    case.recovered_amount_paise = case.amount_paise
    transition_case(
        case,
        to_state=RecoveryState.RECOVERED,
        actor=AuditActor.GATEWAY_WEBHOOK,
        reason="Customer paid before the follow-up window elapsed.",
    )
    repo.save(case)

    queued = repo.fetch_queued_jobs(limit=10)
    followup_job = next(j for j in queued if j.job_type == "P2P_FOLLOWUP_CHECK")
    followup_job.due_at = datetime.now(UTC) - timedelta(seconds=5)
    repo.schedule_job(followup_job)

    executed = await executor.execute_due_jobs_once(limit=10)
    assert executed >= 1

    unchanged = repo.get_by_id(case.case_id)
    assert unchanged is not None
    assert unchanged.state == RecoveryState.RECOVERED
