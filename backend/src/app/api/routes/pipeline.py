"""Pipeline and queue observability endpoints according to DATA_PIPELINE_SPEC."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator  # noqa: TC003
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from app.audit.models import AuditEntry, RecoveryCase, ScheduledJob
from app.audit.repository import get_case_repository
from app.core.constants import DEFAULT_CURRENCY, MAX_FLEET_EVENTS_PER_MINUTE
from app.core.enums import (
    AuditActor,
    ExperimentArm,
    JobStatus,
    PaymentRail,
    RecoveryState,
)
from app.core.logging import get_logger
from app.detection.models import RawFailureEvent
from app.simulation.fleet import FleetSimulator

logger = get_logger(__name__)
router = APIRouter(prefix="/pipeline", tags=["pipeline"])


class SingleEventIngestRequest(BaseModel):
    """Payload for single event manual ingress."""

    payment_id: str = Field(default_factory=lambda: f"pay_demo_{uuid4().hex[:8]}")
    customer_id: str = "cust_demo_manual"
    amount_paise: int = Field(default=49900, gt=0)
    currency: str = Field(default=DEFAULT_CURRENCY, pattern=r"^[A-Z]{3}$")
    payment_rail: PaymentRail = PaymentRail.UPI
    error_code: str = "U30"
    error_description: str = "PSP bank timeout during collect request"
    error_reason: str = "PSP bank timeout"
    contact_phone: str | None = "+919876500001"
    contact_email: str | None = "demo@example.com"
    experiment_arm: ExperimentArm = ExperimentArm.TREATMENT


class FleetStartRequest(BaseModel):
    """Configuration payload for continuous fleet simulation."""

    events_per_minute: int = Field(default=20, ge=1, le=MAX_FLEET_EVENTS_PER_MINUTE)
    rails: list[PaymentRail] | None = None
    min_amount_paise: int = Field(default=10000, ge=100)
    max_amount_paise: int = Field(default=50000000, ge=100)
    use_llm: bool = True
    experiment_id: str | None = None

    @model_validator(mode="after")
    def _check_amount_range(self) -> FleetStartRequest:
        if self.min_amount_paise > self.max_amount_paise:
            msg = "min_amount_paise must not exceed max_amount_paise"
            raise ValueError(msg)
        return self


@router.get("/overview", summary="Get Pipeline Health & Queue Overview")
async def get_pipeline_overview() -> dict[str, Any]:
    """Return live observable queue counts, throughput rates, and backlog depth."""
    repo = get_case_repository()
    return repo.get_pipeline_overview()


@router.get("/timeseries", summary="Get Ingestion & Processing Timeseries")
async def get_pipeline_timeseries(
    bucket_minutes: Annotated[int, Query(ge=1, le=1440)] = 60,
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
) -> list[dict[str, Any]]:
    """Return aggregated time series for ingested vs processed events."""
    repo = get_case_repository()
    return repo.get_pipeline_timeseries(bucket_minutes=bucket_minutes, hours=hours)


@router.get("/heatmap", summary="Get 7x24 Flood/Peak Traffic Heatmap")
async def get_pipeline_heatmap() -> list[dict[str, Any]]:
    """Return 7x24 matrix of event counts across day-of-week and hour-of-day."""
    repo = get_case_repository()
    return repo.get_pipeline_heatmap()


@router.get("/queued", summary="Get Queued Jobs Listing")
async def get_queued_jobs(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    statuses: Annotated[
        str | None, Query(description="Comma-separated status filter")
    ] = None,
) -> list[dict[str, Any]]:
    """Return list of observable queue jobs with retry counts, age, and status."""
    repo = get_case_repository()
    status_list = [s.strip().upper() for s in statuses.split(",")] if statuses else None
    jobs = repo.fetch_queued_jobs(limit=limit, statuses=status_list)
    return [job.model_dump(mode="json") for job in jobs]


@router.post(
    "/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest Single Failure Event",
)
async def ingest_single_event(
    req: SingleEventIngestRequest,
    response: Response,
) -> dict[str, Any]:
    """Ingest a single transaction failure directly into the durable FIFO queue."""
    repo = get_case_repository()

    # Deduplication check
    existing = repo.get_by_payment_id(req.payment_id)
    if existing:
        response.status_code = status.HTTP_202_ACCEPTED
        return {
            "status": "queued",
            "case_id": existing.case_id,
            "action": "ALREADY_QUEUED",
        }

    now = datetime.now(UTC)
    case_id = f"case_ing_{uuid4().hex[:8]}"
    raw_event = RawFailureEvent(
        event_id=f"evt_{req.payment_id}",
        payment_id=req.payment_id,
        customer_id=req.customer_id,
        amount_paise=req.amount_paise,
        currency=req.currency,
        payment_rail=req.payment_rail,
        error_code=req.error_code,
        error_description=req.error_description,
        error_reason=req.error_reason,
        contact_phone=req.contact_phone,
        contact_email=req.contact_email,
        occurred_at=now,
    )

    case = RecoveryCase(
        case_id=case_id,
        merchant_id="merchant_live_buildathon",
        state=RecoveryState.ANALYSIS_QUEUED,
        experiment_arm=req.experiment_arm,
        amount_paise=req.amount_paise,
        currency=req.currency,
        failure_event=raw_event,
        created_at=now,
        updated_at=now,
    )
    case.audit_trail.append(
        AuditEntry(
            case_id=case_id,
            from_state=None,
            to_state=RecoveryState.ANALYSIS_QUEUED,
            actor=AuditActor.GATEWAY_WEBHOOK,
            event_name="case.ingested",
            notes=f"Single manual event ingested {req.payment_id} for rail {req.payment_rail.value}",
            cost_incurred_paise=0,
            decision_inputs={
                "payment_id": req.payment_id,
                "amount_paise": req.amount_paise,
                "rail": req.payment_rail.value,
                "experiment_arm": req.experiment_arm.value,
            },
            timestamp=now,
        )
    )
    case.recompute_nrv()
    repo.save(case)

    job = ScheduledJob(
        case_id=case_id,
        job_type="INGESTION_DIAGNOSIS",
        due_at=now,
        status=JobStatus.QUEUED,
        idempotency_key=f"ingest_{req.payment_id}",
        payload={"event_id": raw_event.event_id, "payment_id": req.payment_id},
        created_at=now,
        updated_at=now,
    )
    repo.schedule_job(job)

    response.status_code = status.HTTP_202_ACCEPTED
    return {
        "status": "queued",
        "case_id": case_id,
        "job_id": job.job_id,
        "payment_id": req.payment_id,
    }


@router.get("/stream", summary="Live Server-Sent Events Queue Feed")
async def stream_pipeline_events() -> StreamingResponse:
    """Stream realtime queue state and throughput updates over Server-Sent Events."""
    repo = get_case_repository()

    async def event_generator() -> AsyncIterator[str]:
        while True:
            try:
                overview = repo.get_pipeline_overview()
                recent_jobs = repo.fetch_queued_jobs(limit=10)
                data = {
                    "overview": overview,
                    "recent_jobs": [j.model_dump(mode="json") for j in recent_jobs],
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                yield f"data: {json.dumps(data)}\n\n"
            except Exception as exc:  # noqa: BLE001
                yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
            await asyncio.sleep(1.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# Fleet Simulator Remote Control Endpoints
@router.post("/fleet/start", summary="Start Continuous Fleet Simulator")
async def start_fleet_simulation(req: FleetStartRequest) -> dict[str, Any]:
    """Start continuous background transaction failure generation."""
    simulator = FleetSimulator.get_instance()
    return simulator.start(
        events_per_minute=req.events_per_minute,
        rails=[r.value for r in req.rails] if req.rails else None,
        min_amount_paise=req.min_amount_paise,
        max_amount_paise=req.max_amount_paise,
        use_llm=req.use_llm,
        experiment_id=req.experiment_id,
    )


@router.post("/fleet/stop", summary="Stop Fleet Simulator")
async def stop_fleet_simulation() -> dict[str, Any]:
    """Stop continuous fleet simulation."""
    simulator = FleetSimulator.get_instance()
    return simulator.stop()


@router.post("/fleet/pause", summary="Pause Fleet Simulator")
async def pause_fleet_simulation() -> dict[str, Any]:
    """Pause continuous fleet simulation."""
    simulator = FleetSimulator.get_instance()
    return simulator.pause()


@router.post("/fleet/resume", summary="Resume Fleet Simulator")
async def resume_fleet_simulation() -> dict[str, Any]:
    """Resume paused fleet simulation."""
    simulator = FleetSimulator.get_instance()
    return simulator.resume()


@router.get("/fleet/status", summary="Get Fleet Simulator Status")
async def get_fleet_simulator_status() -> dict[str, Any]:
    """Return live status of the continuous fleet simulator."""
    simulator = FleetSimulator.get_instance()
    return simulator.get_status()
