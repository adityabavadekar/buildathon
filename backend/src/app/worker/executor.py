"""Durable background worker processing queued ingestion, diagnosis, and intervention tasks."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.audit.models import RecoveryCase, ScheduledJob
from app.audit.repository import get_case_repository
from app.audit.state_machine import transition_case
from app.core.constants import (
    MAX_DUNNING_LIFECYCLE_DAYS,
    P2P_DEFAULT_FOLLOWUP_HOURS,
    P2P_MAX_REMINDER_ATTEMPTS,
)
from app.core.enums import AuditActor, EscalationReason, JobStatus, RecoveryState
from app.core.logging import get_logger
from app.core.operator import OperatorMode, get_operator_mode
from app.intervention.orchestrator import get_orchestrator
from app.llm.client import configured_providers

logger = get_logger(__name__)

MAX_JOB_ATTEMPTS = 5

# A dunning case sitting in a non-terminal state past this many days without a
# save (webhook, retry, outreach) is a lost cause we're still counting as "at
# risk" forever -- abandoning it stops the dashboard's open-case figure from
# growing unbounded with cases nothing will ever resolve.
_ACTIVE_STATES = [state.value for state in RecoveryState if state.is_active]


class DueJobExecutor:
    """Polls, atomically claims, and executes due recovery jobs with bounded retries and crash recovery."""

    def __init__(self) -> None:
        self.repo = get_case_repository()
        self.orchestrator = get_orchestrator()

    def _check_p2p_followup(self, case: RecoveryCase) -> None:
        """Evaluate a promise-to-pay deadline: no-op if paid, else one bounded
        reminder before escalating, so a missed promise cannot loop forever.
        """
        if case.state not in (RecoveryState.P2P_WAITING, RecoveryState.P2P_PROMISED):
            return

        if case.p2p_reminder_count < P2P_MAX_REMINDER_ATTEMPTS:
            case.p2p_reminder_count += 1
            new_due = datetime.now(UTC) + timedelta(hours=P2P_DEFAULT_FOLLOWUP_HOURS)
            case.promised_payment_date = new_due
            transition_case(
                case,
                to_state=RecoveryState.P2P_PROMISED,
                actor=AuditActor.SYSTEM,
                reason="Promised payment date passed without capture; sending one reminder before escalation.",
                event_name="p2p.reminder_sent",
                decision_inputs={
                    "promised_payment_date": case.promised_payment_date.isoformat(),
                    "reminder_count": case.p2p_reminder_count,
                    "max_reminder_attempts": P2P_MAX_REMINDER_ATTEMPTS,
                },
            )
            self.repo.schedule_job(
                ScheduledJob(
                    case_id=case.case_id,
                    job_type="P2P_FOLLOWUP_CHECK",
                    due_at=new_due,
                    idempotency_key=f"idem_p2pcheck_{case.case_id}_{case.p2p_reminder_count}",
                )
            )
            return

        transition_case(
            case,
            to_state=RecoveryState.ESCALATED,
            actor=AuditActor.POLICY_GATE,
            reason="Promise to pay missed after reminder; escalating for operator review.",
            event_name="p2p.promise_missed_escalated",
            escalation_reason=EscalationReason.HUMAN_JUDGMENT,
            decision_inputs={
                "promised_payment_date": case.promised_payment_date.isoformat()
                if case.promised_payment_date
                else None,
                "reminder_count": case.p2p_reminder_count,
                "max_reminder_attempts": P2P_MAX_REMINDER_ATTEMPTS,
            },
        )

    def recover_stuck_jobs(self) -> int:
        """Reclaim orphaned jobs stuck in PROCESSING from previous worker crashes."""
        reclaimed = self.repo.reclaim_stuck_processing_jobs(max_processing_seconds=30)
        if reclaimed > 0:
            logger.info("worker.crash_recovery_reclaimed_jobs", count=reclaimed)
        return reclaimed

    def abandon_stale_cases(self) -> int:
        """Terminate cases with no activity for MAX_DUNNING_LIFECYCLE_DAYS.

        Runs every sweep rather than once at startup: a case can go stale at
        any point in its lifetime, not just after a crash.
        """
        cutoff = datetime.now(UTC) - timedelta(days=MAX_DUNNING_LIFECYCLE_DAYS)
        abandoned_count = 0
        # Bounded page size: the number of cases stale enough to abandon in
        # one sweep is expected to be small relative to total case volume.
        stale_candidates = self.repo.list_cases(
            states=_ACTIVE_STATES,
            sort_by="updated_at",
            sort_dir="asc",
            limit=200,
        )
        for case in stale_candidates:
            if case.updated_at >= cutoff:
                # sort_dir=asc means every later case is even less stale.
                break
            transition_case(
                case,
                to_state=RecoveryState.ABANDONED,
                actor=AuditActor.SYSTEM,
                reason=(
                    f"No activity for {MAX_DUNNING_LIFECYCLE_DAYS} days "
                    f"(last update {case.updated_at.isoformat()}); "
                    "abandoning dunning lifecycle."
                ),
                event_name="case.abandoned_stale",
                decision_inputs={
                    "last_updated_at": case.updated_at.isoformat(),
                    "max_lifecycle_days": MAX_DUNNING_LIFECYCLE_DAYS,
                    "state_at_abandonment": case.state.value,
                },
            )
            self.repo.save(case)
            abandoned_count += 1
        if abandoned_count > 0:
            logger.info("worker.stale_cases_abandoned", count=abandoned_count)
        return abandoned_count

    async def execute_due_jobs_once(self, limit: int = 20) -> int:  # noqa: PLR0912, PLR0915
        """Fetch and execute due jobs whose due_at timestamp has passed."""
        executed_count = 0
        max_attempts = self.orchestrator.policy.max_attempts

        for _ in range(limit):
            # Atomic claim under row-level lock
            job = self.repo.claim_next_due_job()
            if not job:
                break

            logger.info(
                "worker.job_claimed",
                job_id=job.job_id,
                job_type=job.job_type,
                case_id=job.case_id,
                attempt=job.attempts,
            )

            try:
                case = self.repo.get_by_id(job.case_id)
                if not case:
                    self.repo.update_job_status(
                        job.job_id, status=JobStatus.FAILED.value
                    )
                    continue

                # 1. Skip terminal or already resolved cases
                if case.state in (
                    RecoveryState.RECOVERED,
                    RecoveryState.ABANDONED,
                    RecoveryState.WRITTEN_OFF,
                ):
                    self.repo.update_job_status(job.job_id, status=JobStatus.DONE.value)
                    executed_count += 1
                    continue

                # 2. Ingestion & Diagnosis Pipeline Job
                if (
                    job.job_type in ("INGESTION_DIAGNOSIS", "DIAGNOSIS")
                    or case.state == RecoveryState.ANALYSIS_QUEUED
                ):
                    await self.orchestrator.process_failure_event(
                        case.failure_event,
                        experiment_arm_override=case.experiment_arm,
                        use_llm=bool(configured_providers()),
                    )
                    self.repo.update_job_status(job.job_id, status=JobStatus.DONE.value)
                    executed_count += 1
                    continue

                # 3. Promise-to-Pay follow-up check
                if job.job_type == "P2P_FOLLOWUP_CHECK":
                    self._check_p2p_followup(case)
                    self.repo.save(case)
                    self.repo.update_job_status(job.job_id, status=JobStatus.DONE.value)
                    executed_count += 1
                    continue

                # 4. Check attempt caps & stopping rules
                if case.attempts_count >= max_attempts:
                    transition_case(
                        case,
                        to_state=RecoveryState.ESCALATED,
                        actor=AuditActor.POLICY_GATE,
                        reason=f"Reached maximum attempts cap ({max_attempts}). Escalating for operator review.",
                        event_name="policy.max_attempts_exceeded",
                        escalation_reason=EscalationReason.HUMAN_JUDGMENT,
                    )
                    self.repo.save(case)
                    self.repo.update_job_status(job.job_id, status=JobStatus.DONE.value)
                    executed_count += 1
                    continue

                # 5. Check operator mode before outbound execution
                operator_mode = get_operator_mode()
                if operator_mode == OperatorMode.MONITORING_ONLY:
                    logger.info(
                        "worker.job_held_circuit_breaker",
                        job_id=job.job_id,
                        case_id=case.case_id,
                    )
                    self.repo.update_job_status(
                        job.job_id, status=JobStatus.QUEUED.value
                    )
                    continue

                if (
                    operator_mode == OperatorMode.HUMAN_IN_THE_LOOP
                    and case.state != RecoveryState.IN_DUNNING
                ):
                    transition_case(
                        case,
                        to_state=RecoveryState.ESCALATED,
                        actor=AuditActor.POLICY_GATE,
                        reason="Attempt paused for human operator approval under HUMAN_IN_THE_LOOP mode",
                        event_name="worker.pending_human_approval",
                        escalation_reason=EscalationReason.HUMAN_JUDGMENT,
                    )
                    self.repo.save(case)
                    self.repo.update_job_status(job.job_id, status=JobStatus.DONE.value)
                    executed_count += 1
                    continue

                # 6. Scheduled Attempt Execution
                case.attempts_count += 1
                case.last_attempt_at = datetime.now(UTC)

                if "RETRY" in job.job_type.upper():
                    case.retry_count += 1
                    transition_case(
                        case,
                        to_state=RecoveryState.IN_DUNNING,
                        actor=AuditActor.SYSTEM,
                        reason=f"Executed worker retry sequence for case {case.case_id}",
                        event_name="worker.retry_executed",
                        cost_incurred_paise=250,
                    )
                else:
                    case.outreach_count += 1
                    transition_case(
                        case,
                        to_state=RecoveryState.IN_DUNNING,
                        actor=AuditActor.SYSTEM,
                        reason=f"Executed worker outreach delivery for case {case.case_id}",
                        event_name="worker.outreach_executed",
                        cost_incurred_paise=50,
                    )

                case.recompute_nrv()
                self.repo.save(case)
                self.repo.update_job_status(job.job_id, status=JobStatus.DONE.value)
                executed_count += 1

            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "worker.job_execution_failed",
                    job_id=job.job_id,
                    attempts=job.attempts,
                    error=str(exc),
                )
                if job.attempts >= MAX_JOB_ATTEMPTS:
                    # Bounded dead-letter queue for poison events
                    logger.error(
                        "worker.job_moved_to_dead_letter",
                        job_id=job.job_id,
                        case_id=job.case_id,
                    )
                    self.repo.update_job_status(job.job_id, status=JobStatus.DEAD.value)
                else:
                    # Exponential backoff retry
                    backoff_seconds = min(3600, (2**job.attempts) * 3)
                    new_due = datetime.now(UTC) + timedelta(seconds=backoff_seconds)
                    self.repo.update_job_status(
                        job.job_id, status=JobStatus.QUEUED.value
                    )
                    # Update due_at on retry
                    cur_job = ScheduledJob(
                        job_id=job.job_id,
                        case_id=job.case_id,
                        job_type=job.job_type,
                        due_at=new_due,
                        status=JobStatus.QUEUED,
                        idempotency_key=job.idempotency_key,
                        attempts=job.attempts,
                        payload=job.payload,
                    )
                    self.repo.schedule_job(cur_job)

        return executed_count

    async def run_forever(self, poll_interval_seconds: float = 1.0) -> None:
        """Run the job polling worker loop indefinitely."""
        self.recover_stuck_jobs()
        logger.info("worker.started_polling", interval=poll_interval_seconds)
        # A lifecycle sweep is a once-a-day-scale concern; run it once per
        # startup and then on a fixed cadence rather than every poll tick, so
        # a slow query never competes with due-job latency at 1s granularity.
        sweep_every_n_polls = max(1, round(3600 / poll_interval_seconds))
        polls_since_sweep = sweep_every_n_polls
        while True:
            try:
                count = await self.execute_due_jobs_once()
                if count > 0:
                    logger.info("worker.batch_completed", count=count)
                polls_since_sweep += 1
                if polls_since_sweep >= sweep_every_n_polls:
                    self.abandon_stale_cases()
                    polls_since_sweep = 0
            except Exception as exc:  # noqa: BLE001
                logger.error("worker.loop_error", error=str(exc))
            await asyncio.sleep(poll_interval_seconds)
