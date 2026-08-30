"""Tests for asynchronous worker loop, event consumption, and due job execution."""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.audit.models import RecoveryCase, ScheduledJob
from app.audit.repository import CaseRepository
from app.core.enums import RecoveryState
from app.detection.models import RawFailureEvent
from app.worker.executor import DueJobExecutor
from app.worker.sync_consumer import RecoverySyncConsumer


def _make_test_case(case_id: str, payment_id: str) -> RecoveryCase:
    event = RawFailureEvent(
        event_id=f"evt_{payment_id}",
        payment_id=payment_id,
        customer_id=f"cust_{case_id}",
        amount_paise=50000,
        error_code="BAD_REQUEST_ERROR",
        occurred_at=datetime.now(UTC),
    )
    return RecoveryCase(
        case_id=case_id,
        state=RecoveryState.IN_DUNNING,
        amount_paise=50000,
        failure_event=event,
    )


@pytest.mark.anyio
async def test_worker_job_execution() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        repo = CaseRepository(storage_path=Path(tmp.name))
        case = _make_test_case("case_w1", "pay_w1")
        repo.save(case)

        now = datetime.now(UTC)
        job = ScheduledJob(
            case_id="case_w1",
            job_type="RETRY",
            due_at=now - timedelta(seconds=10),
            idempotency_key="idem_w1",
        )
        repo.schedule_job(job)

        executor = DueJobExecutor()
        executor.repo = repo

        executed = await executor.execute_due_jobs_once(limit=10)
        assert executed == 1

        due_after = repo.fetch_due_jobs(limit=10)
        assert len(due_after) == 0


@pytest.mark.anyio
async def test_sync_consumer_event_processing() -> None:
    consumer = RecoverySyncConsumer()
    event_dict = {
        "event_id": "evt_consumer_1",
        "payment_id": "pay_consumer_1",
        "customer_id": "cust_consumer_1",
        "amount_paise": 75000,
        "payment_rail": "UPI",
        "error_code": "AP15",
        "error_reason": "Insufficient balance in customer bank account",
        "occurred_at": datetime.now(UTC).isoformat(),
    }
    case_id = await consumer.process_event(event_dict)
    assert case_id is not None
