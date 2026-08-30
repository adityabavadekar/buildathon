"""Tests for CaseRepository persistence, deduplication, scheduled jobs, and filtering."""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.audit.models import AuditEntry, ModelTelemetryEntry, RecoveryCase, ScheduledJob
from app.audit.repository import CaseRepository
from app.core.enums import AuditActor, ExperimentArm, RecoveryState
from app.detection.models import RawFailureEvent


def _make_case(
    case_id: str, payment_id: str, state: RecoveryState = RecoveryState.IN_DUNNING
) -> RecoveryCase:
    event = RawFailureEvent(
        event_id=f"evt_{payment_id}",
        payment_id=payment_id,
        customer_id=f"cust_{case_id}",
        amount_paise=100000,
        error_code="BAD_REQUEST_ERROR",
        occurred_at=datetime.now(UTC),
    )
    return RecoveryCase(
        case_id=case_id,
        state=state,
        amount_paise=100000,
        failure_event=event,
    )


def test_repository_save_and_retrieve_by_various_keys() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        repo = CaseRepository(storage_path=Path(tmp.name))
        case = _make_case("case_1", "pay_1")

        repo.save(case, idempotency_key="idem_1")

        retrieved = repo.get_by_id("case_1")
        assert retrieved is not None
        assert retrieved.case_id == case.case_id
        assert retrieved.failure_event.payment_id == "pay_1"

        assert repo.get_by_payment_id("pay_1") is not None
        assert repo.get_by_idempotency_key("idem_1") is not None
        assert repo.get_by_id("non_existent") is None


def test_repository_list_and_filter() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        repo = CaseRepository(storage_path=Path(tmp.name))
        case1 = _make_case("case_1", "pay_1", state=RecoveryState.IN_DUNNING)
        case2 = _make_case("case_2", "pay_2", state=RecoveryState.RECOVERED)
        case3 = _make_case("case_3", "pay_3", state=RecoveryState.ESCALATED)
        case3.experiment_arm = ExperimentArm.HOLDOUT_CONTROL

        repo.save(case1)
        repo.save(case2)
        repo.save(case3)

        all_cases = repo.list_cases(limit=10)
        assert len(all_cases) == 3

        recovered_cases = repo.list_cases(state=RecoveryState.RECOVERED)
        assert len(recovered_cases) == 1
        assert recovered_cases[0].case_id == "case_2"

        holdout_cases = repo.list_cases(experiment_arm=ExperimentArm.HOLDOUT_CONTROL)
        assert len(holdout_cases) == 1
        assert holdout_cases[0].case_id == "case_3"

        assert repo.count() == 3
        assert repo.count(state=RecoveryState.ESCALATED) == 1


def test_repository_audit_trail_immutability() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        repo = CaseRepository(storage_path=Path(tmp.name))
        case = _make_case("case_aud", "pay_aud")

        entry = AuditEntry(
            case_id="case_aud",
            event_name="test.event",
            actor=AuditActor.SYSTEM,
            from_state=RecoveryState.ANALYSIS_QUEUED,
            to_state=RecoveryState.IN_DUNNING,
            notes="Test audit entry",
        )
        case.audit_trail.append(entry)
        repo.save(case)

        saved = repo.get_by_id("case_aud")
        assert saved is not None
        assert len(saved.audit_trail) == 1
        assert saved.audit_trail[0].event_name == "test.event"


def test_repository_scheduled_jobs() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        repo = CaseRepository(storage_path=Path(tmp.name))
        case = _make_case("case_job", "pay_job")
        repo.save(case)

        now = datetime.now(UTC)
        past_job = ScheduledJob(
            case_id="case_job",
            job_type="RETRY",
            due_at=now - timedelta(minutes=5),
            idempotency_key="idem_past",
        )
        future_job = ScheduledJob(
            case_id="case_job",
            job_type="OUTREACH",
            due_at=now + timedelta(hours=2),
            idempotency_key="idem_future",
        )

        repo.schedule_job(past_job)
        repo.schedule_job(future_job)

        due_jobs = repo.fetch_due_jobs(limit=10)
        assert len(due_jobs) == 1
        assert due_jobs[0].job_id == past_job.job_id
        assert due_jobs[0].job_type == "RETRY"

        # Update status
        repo.update_job_status(past_job.job_id, status="DONE", attempts=1)
        remaining_due = repo.fetch_due_jobs(limit=10)
        assert len(remaining_due) == 0


def test_repository_model_telemetry() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        repo = CaseRepository(storage_path=Path(tmp.name))
        entry = ModelTelemetryEntry(
            model="anthropic/claude-3.7-sonnet",
            provider="openrouter",
            input_tokens=150,
            output_tokens=75,
            cost_usd=0.0012,
            latency_ms=350.5,
            case_id="case_tel",
        )
        repo.record_model_telemetry(entry)
