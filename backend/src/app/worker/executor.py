"""Durable background worker processing queued ingestion, diagnosis, and intervention tasks."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.audit.models import ScheduledJob
from app.audit.repository import get_case_repository
from app.audit.state_machine import transition_case
from app.core.enums import AuditActor, JobStatus, RecoveryState
from app.core.logging import get_logger
from app.core.operator import OperatorMode, get_operator_mode
from app.intervention.orchestrator import get_orchestrator

logger = get_logger(__name__)

MAX_JOB_ATTEMPTS = 5


class DueJobExecutor:
    """Polls, atomically claims, and executes due recovery jobs with bounded retries and crash recovery."""

    def __init__(self) -> None:
        self.repo = get_case_repository()
        self.orchestrator = get_orchestrator()

    def recover_stuck_jobs(self) -> int:
        """Reclaim orphaned jobs stuck in PROCESSING from previous worker crashes."""
        reclaimed = self.repo.reclaim_stuck_processing_jobs(max_processing_seconds=30)
        if reclaimed > 0:
            logger.info("worker.crash_recovery_reclaimed_jobs", count=reclaimed)
        return reclaimed

    async def execute_due_jobs_once(self, limit: int = 20) -> int:  # noqa: PLR0912, PLR0915
        """Fetch and execute due jobs whose due_at timestamp has passed."""
        executed_count = 0
        max_touches = self.orchestrator.policy.max_touches

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
                    use_llm = bool(job.payload.get("use_llm", False))
                    await self.orchestrator.process_failure_event(
                        case.failure_event,
                        experiment_arm_override=case.experiment_arm,
                        use_llm=use_llm,
                    )
                    self.repo.update_job_status(job.job_id, status=JobStatus.DONE.value)
                    executed_count += 1
                    continue

                # 3. Check touch caps & stopping rules
                if case.touches_count >= max_touches:
                    transition_case(
                        case,
                        to_state=RecoveryState.ESCALATED,
                        actor=AuditActor.POLICY_GATE,
                        reason=f"Reached maximum touches cap ({max_touches}). Escalating for operator review.",
                        event_name="policy.max_touches_exceeded",
                    )
                    self.repo.save(case)
                    self.repo.update_job_status(job.job_id, status=JobStatus.DONE.value)
                    executed_count += 1
                    continue

                # 4. Check operator mode before outbound execution
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
                        reason="Touch paused for human operator approval under HUMAN_IN_THE_LOOP mode",
                        event_name="worker.pending_human_approval",
                    )
                    self.repo.save(case)
                    self.repo.update_job_status(job.job_id, status=JobStatus.DONE.value)
                    executed_count += 1
                    continue

                # 5. Scheduled Touch Execution
                case.touches_count += 1
                case.last_touch_at = datetime.now(UTC)

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
                        status=JobStatus.QUEUED.value,
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
        while True:
            try:
                count = await self.execute_due_jobs_once()
                if count > 0:
                    logger.info("worker.batch_completed", count=count)
            except Exception as exc:  # noqa: BLE001
                logger.error("worker.loop_error", error=str(exc))
            await asyncio.sleep(poll_interval_seconds)
