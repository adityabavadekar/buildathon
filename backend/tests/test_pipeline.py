"""Tests verifying the full data pipeline spec: fast 202 ingress, durable queue, fleet generator, and crash recovery."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx2
import pytest

from app.audit.models import RecoveryCase, ScheduledJob
from app.audit.repository import CaseRepository
from app.core.enums import ExperimentArm, JobStatus, PaymentRail, RecoveryState
from app.detection.models import RawFailureEvent
from app.main import create_app
from app.simulation.fleet import FleetSimulator
from app.worker.executor import DueJobExecutor


def _make_test_case(case_id: str, payment_id: str) -> RecoveryCase:
    event = RawFailureEvent(
        event_id=f"evt_{payment_id}",
        payment_id=payment_id,
        customer_id="cust_test_p",
        amount_paise=50000,
        currency="INR",
        payment_rail=PaymentRail.UPI,
        error_code="U30",
        error_description="Bank PSP timeout",
        error_reason="Bank PSP timeout",
        occurred_at=datetime.now(UTC),
    )
    return RecoveryCase(
        case_id=case_id,
        merchant_id="merchant_test",
        amount_paise=50000,
        currency="INR",
        failure_event=event,
        state=RecoveryState.ANALYSIS_QUEUED,
        experiment_arm=ExperimentArm.TREATMENT,
    )


@pytest.mark.anyio
async def test_fast_202_webhook_and_deduplication() -> None:
    """Verify webhook enqueues immediately with 202 and ignores duplicates."""
    app = create_app()
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://test"
    ) as client:
        payload = {
            "event": "payment.failed",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_pipe_test_101",
                        "amount": 29900,
                        "currency": "INR",
                        "method": "upi",
                        "error_code": "XT",
                        "error_description": "Bank switch window cutoff",
                    }
                }
            },
        }

        # First request should return 202 Accepted
        res1 = await client.post("/api/webhooks/razorpay", json=payload)
        assert res1.status_code == 202
        data1 = res1.json()
        assert data1["status"] == "queued"
        case_id = data1["case_id"]
        assert case_id is not None

        # Duplicate request with same payment_id should return 202 with ALREADY_QUEUED
        res2 = await client.post("/api/webhooks/razorpay", json=payload)
        assert res2.status_code == 202
        data2 = res2.json()
        assert data2["case_id"] == case_id
        assert data2["action_taken"] == "ALREADY_QUEUED"


@pytest.mark.anyio
async def test_single_event_ingest_endpoint() -> None:
    """Verify manual single event ingestion returns 202 and enqueues job."""
    app = create_app()
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://test"
    ) as client:
        payload = {
            "payment_id": "pay_manual_999",
            "customer_id": "cust_demo",
            "amount_paise": 75000,
            "payment_rail": "CARD",
            "error_code": "GATEWAY_TIMEOUT",
            "error_description": "Issuing bank network timed out",
            "error_reason": "Bank timeout",
        }
        res = await client.post("/api/pipeline/ingest", json=payload)
        assert res.status_code == 202
        data = res.json()
        assert data["status"] == "queued"
        assert "job_id" in data


@pytest.mark.anyio
async def test_fleet_simulator_lifecycle() -> None:
    """Verify continuous fleet simulator start, pause, resume, and stop controls."""
    simulator = FleetSimulator.get_instance()
    simulator.stop()

    start_res = simulator.start(events_per_minute=60, rails=["UPI", "CARD"])
    assert start_res["is_running"] is True
    assert start_res["is_paused"] is False
    assert start_res["events_per_minute"] == 60

    pause_res = simulator.pause()
    assert pause_res["is_paused"] is True

    resume_res = simulator.resume()
    assert resume_res["is_paused"] is False

    stop_res = simulator.stop()
    assert stop_res["is_running"] is False


@pytest.mark.anyio
async def test_crash_recovery_reclaim_processing_jobs() -> None:
    """Verify worker startup reclaims orphaned PROCESSING jobs from previous crashes."""
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        repo = CaseRepository(storage_path=Path(tmp.name))
        case = _make_test_case("case_crash_1", "pay_crash_1")
        repo.save(case)

        now = datetime.now(UTC)
        job = ScheduledJob(
            case_id="case_crash_1",
            job_type="INGESTION_DIAGNOSIS",
            due_at=now - timedelta(seconds=120),
            status=JobStatus.PROCESSING.value,
            idempotency_key="idem_crash_1",
            updated_at=now - timedelta(seconds=120),
        )
        repo.schedule_job(job)

        executor = DueJobExecutor()
        executor.repo = repo

        reclaimed = executor.recover_stuck_jobs()
        assert reclaimed == 1

        claimed = repo.claim_next_due_job()
        assert claimed is not None
        assert claimed.case_id == "case_crash_1"
        assert claimed.status == JobStatus.PROCESSING.value


@pytest.mark.anyio
async def test_pipeline_observability_endpoints() -> None:
    """Verify overview, timeseries, heatmap, and queue API queries."""
    app = create_app()
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Overview
        overview_res = await client.get("/api/pipeline/overview")
        assert overview_res.status_code == 200
        overview = overview_res.json()
        assert "counts" in overview
        assert "events_received_total" in overview
        assert "backlog_depth" in overview

        # Timeseries
        ts_res = await client.get("/api/pipeline/timeseries?bucket_minutes=60&hours=24")
        assert ts_res.status_code == 200
        ts = ts_res.json()
        assert isinstance(ts, list)

        # Heatmap
        hm_res = await client.get("/api/pipeline/heatmap")
        assert hm_res.status_code == 200
        hm = hm_res.json()
        assert len(hm) == 7 * 24

        # Queued listing
        queued_res = await client.get("/api/pipeline/queued?limit=10")
        assert queued_res.status_code == 200
        assert isinstance(queued_res.json(), list)
