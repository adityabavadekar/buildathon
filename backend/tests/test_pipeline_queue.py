"""Tests for fleet enqueueing and queue observability."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.audit.repository import get_case_repository
from app.core.config import get_settings
from app.core.enums import JobStatus, PaymentRail
from app.detection.models import RawFailureEvent
from app.intervention.orchestrator import RecoveryOrchestrator
from app.simulation.fleet import FleetSimulator

COMPRESSION_TEST_HOURS = 48


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
    orchestrator = RecoveryOrchestrator(repository=repo)

    live = await orchestrator.process_failure_event(_event(source="webhook"))
    sim = await orchestrator.process_failure_event(_event(source="fleet"))

    assert live.due_at is not None
    assert sim.due_at is not None
    assert sim.due_at < live.due_at


@pytest.mark.anyio
async def test_fleet_ingestion_rows_are_terminal_not_claimable() -> None:
    """The fleet diagnoses inline, so its own job row must not be re-claimable."""
    repo = get_case_repository()
    repo.clear()
    try:
        fleet = FleetSimulator()
        await fleet._emit_single_event(repo)

        jobs = repo.fetch_queued_jobs(
            limit=50, statuses=[JobStatus.DONE.value, JobStatus.QUEUED.value]
        )
        ingestion = [j for j in jobs if j.job_type == "INGESTION_DIAGNOSIS"]
        assert ingestion, "fleet did not record an ingestion job"
        assert all(j.status == JobStatus.DONE.value for j in ingestion)

        # A terminal row must never be handed to the worker.
        claimed = repo.claim_next_due_job()
        if claimed is not None:
            assert claimed.job_type != "INGESTION_DIAGNOSIS"
    finally:
        repo.clear()
