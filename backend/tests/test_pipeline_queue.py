"""Tests for fleet enqueueing and queue observability."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx2
import pytest

from app.audit.repository import get_case_repository
from app.core.config import get_settings
from app.core.enums import JobStatus, PaymentRail
from app.detection.models import RawFailureEvent
from app.intervention.orchestrator import RecoveryOrchestrator
from app.intervention.tools.mandate_retry import MandateRetryTool
from app.simulation.fleet import FleetSimulator

COMPRESSION_TEST_HOURS = 48


def _mock_mandate_retry_tool() -> MandateRetryTool:
    """A MandateRetryTool wired to a mock transport that always charges
    successfully, so this queue-timing test never depends on a live Razorpay
    subscription existing for a synthetic payment_id.
    """

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status_code=200, json={"id": "chg_queue_test"})

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    return MandateRetryTool(client=client)


def _event(*, source: str, code: str = "AP15") -> RawFailureEvent:
    return RawFailureEvent(
        event_id=f"evt_q_{source}_{code}",
        payment_id=f"pay_q_{source}_{code}",
        # Distinct per source: cooldown is scoped to the customer, so a shared id
        # would block the second event and mask what this test measures.
        customer_id=f"cust_queue_{source}",
        amount_paise=250000,
        currency="INR",
        payment_rail=PaymentRail.UPI_AUTOPAY,
        error_code=code,
        error_reason="Insufficient balance in account for debit mandate",
        error_description="Insufficient balance in account for debit mandate",
        occurred_at=datetime.now(UTC),
        metadata={"source": source},
    )


@pytest.mark.anyio
async def test_simulated_events_are_scheduled_sooner_than_real_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compression must apply to simulated traffic only.

    Production delays are correct but leave nothing due for hours, which makes a
    demo look like a stalled worker.
    """
    monkeypatch.setattr(
        get_settings(), "fleet_time_compression", COMPRESSION_TEST_HOURS, raising=False
    )
    repo = get_case_repository()
    orchestrator = RecoveryOrchestrator(
        repository=repo, mandate_retry_tool=_mock_mandate_retry_tool()
    )

    live = await orchestrator.process_failure_event(_event(source="webhook"))
    sim = await orchestrator.process_failure_event(_event(source="fleet"))

    assert live.due_at is not None
    assert sim.due_at is not None
    assert sim.due_at < live.due_at


@pytest.mark.anyio
async def test_fleet_events_are_queued_via_the_real_webhook_route() -> None:
    """Fleet now posts through the webhook endpoint, so its ingestion row is
    QUEUED like any other webhook-originated case, not diagnosed inline.
    """
    repo = get_case_repository()
    repo.clear()
    try:
        fleet = FleetSimulator()
        await fleet._emit_single_event()

        jobs = repo.fetch_queued_jobs(
            limit=50, statuses=[JobStatus.DONE.value, JobStatus.QUEUED.value]
        )
        ingestion = [j for j in jobs if j.job_type == "INGESTION_DIAGNOSIS"]
        assert ingestion, "fleet did not record an ingestion job"
        assert all(j.status == JobStatus.QUEUED.value for j in ingestion)

        # A queued row from fleet traffic must be claimable by the worker just
        # like a real webhook-originated job.
        claimed = repo.claim_next_due_job()
        assert claimed is not None
        assert claimed.job_type == "INGESTION_DIAGNOSIS"
    finally:
        repo.clear()
