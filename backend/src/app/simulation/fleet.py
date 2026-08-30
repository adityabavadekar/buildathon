"""Continuous Fleet Failure Generator daemon running in the background."""

from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.audit.models import AuditEntry, RecoveryCase, ScheduledJob
from app.audit.repository import get_case_repository
from app.core.enums import AuditActor, ExperimentArm, PaymentRail, RecoveryState
from app.core.logging import get_logger
from app.detection.models import RawFailureEvent
from app.simulation.seeder import CUSTOMER_NAMES, FAILURE_TEMPLATES

logger = get_logger(__name__)


class FleetSimulator:
    """Continuous background generator emitting realistic transaction failure events into the queue."""

    _instance: FleetSimulator | None = None

    def __init__(self) -> None:
        self.is_running: bool = False
        self.is_paused: bool = False
        self.events_per_minute: int = 20
        self.rails: list[str] = [
            r.value for r in PaymentRail if r != PaymentRail.UNKNOWN
        ]
        self.min_amount_paise: int = 10000
        self.max_amount_paise: int = 10000000
        self.use_llm: bool = False
        self.experiment_id: str | None = None
        self.events_emitted: int = 0
        self.started_at: datetime | None = None
        self.last_emitted_at: datetime | None = None
        self._task: asyncio.Task[None] | None = None

    @classmethod
    def get_instance(cls) -> FleetSimulator:
        """Return singleton fleet simulator instance."""
        if cls._instance is None:
            cls._instance = FleetSimulator()
        return cls._instance

    def start(
        self,
        *,
        events_per_minute: int = 20,
        rails: list[str] | None = None,
        min_amount_paise: int = 10000,
        max_amount_paise: int = 10000000,
        use_llm: bool = False,
        experiment_id: str | None = None,
    ) -> dict[str, Any]:
        """Start the continuous background failure generation loop."""
        self.events_per_minute = max(1, min(300, events_per_minute))
        if rails:
            self.rails = rails
        self.min_amount_paise = max(100, min_amount_paise)
        self.max_amount_paise = max(self.min_amount_paise, max_amount_paise)
        self.use_llm = use_llm
        self.experiment_id = experiment_id
        self.is_running = True
        self.is_paused = False
        self.started_at = datetime.now(UTC)

        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run_loop())

        logger.info(
            "simulation.fleet_started",
            rate=self.events_per_minute,
            rails=self.rails,
        )
        return self.get_status()

    def stop(self) -> dict[str, Any]:
        """Stop the background simulation generator."""
        self.is_running = False
        self.is_paused = False
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        logger.info("simulation.fleet_stopped", total_emitted=self.events_emitted)
        return self.get_status()

    def pause(self) -> dict[str, Any]:
        """Temporarily pause generation without resetting counters."""
        self.is_paused = True
        logger.info("simulation.fleet_paused")
        return self.get_status()

    def resume(self) -> dict[str, Any]:
        """Resume paused generation."""
        self.is_paused = False
        logger.info("simulation.fleet_resumed")
        return self.get_status()

    def get_status(self) -> dict[str, Any]:
        """Return the current live status of the fleet simulator."""
        return {
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "events_per_minute": self.events_per_minute,
            "rails": self.rails,
            "min_amount_paise": self.min_amount_paise,
            "max_amount_paise": self.max_amount_paise,
            "use_llm": self.use_llm,
            "experiment_id": self.experiment_id,
            "events_emitted": self.events_emitted,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_emitted_at": self.last_emitted_at.isoformat()
            if self.last_emitted_at
            else None,
        }

    async def _run_loop(self) -> None:
        """Continuous event generation loop."""
        repo = get_case_repository()
        while self.is_running:
            if not self.is_paused:
                try:
                    self._emit_single_event(repo)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("simulation.fleet_emit_error", error=str(exc))

            interval_seconds = 60.0 / max(1, self.events_per_minute)
            await asyncio.sleep(interval_seconds)

    def _emit_single_event(self, repo: Any) -> None:
        """Generate and enqueue a single synthetic failure event."""
        # Pick template matching configured rails
        available_templates = [
            t for t in FAILURE_TEMPLATES if t["rail"].value in self.rails
        ] or FAILURE_TEMPLATES
        template = secrets.choice(available_templates)
        cust = secrets.choice(CUSTOMER_NAMES)
        amount = secrets.choice(template["amounts"])
        amount = max(self.min_amount_paise, min(self.max_amount_paise, amount))

        # Assign 10% holdout control arm deterministically
        is_holdout = secrets.randbelow(10) == 0
        arm = ExperimentArm.HOLDOUT_CONTROL if is_holdout else ExperimentArm.TREATMENT

        payment_id = f"pay_fleet_{secrets.token_hex(6)}"
        event_id = f"evt_fleet_{secrets.token_hex(6)}"
        case_id = f"case_fl_{uuid4().hex[:8]}"
        now = datetime.now(UTC)

        raw_event = RawFailureEvent(
            event_id=event_id,
            payment_id=payment_id,
            customer_id=cust[0],
            amount_paise=amount,
            currency="INR",
            payment_rail=template["rail"].value,
            error_code=template["error_code"],
            error_description=template["error_reason"],
            error_reason=template["error_reason"],
            contact_email=cust[2],
            contact_phone=cust[1],
            occurred_at=now,
        )

        case = RecoveryCase(
            case_id=case_id,
            merchant_id="merchant_live_buildathon",
            state=RecoveryState.ANALYSIS_QUEUED,
            experiment_arm=arm,
            amount_paise=amount,
            currency="INR",
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
                notes=f"Fleet simulator generated failure event {payment_id} for rail {template['rail'].value}",
                cost_incurred_paise=0,
                decision_inputs={
                    "payment_id": payment_id,
                    "amount_paise": amount,
                    "rail": template["rail"].value,
                    "experiment_arm": arm.value,
                },
                timestamp=now,
            )
        )
        case.recompute_nrv()
        repo.save(case)

        # Enqueue durable job for worker execution
        job = ScheduledJob(
            case_id=case_id,
            job_type="INGESTION_DIAGNOSIS",
            due_at=now,
            status="QUEUED",
            idempotency_key=f"ingest_{payment_id}",
            payload={
                "event_id": event_id,
                "payment_id": payment_id,
                "use_llm": self.use_llm,
                "experiment_arm": arm.value,
            },
            created_at=now,
            updated_at=now,
        )
        repo.schedule_job(job)

        self.events_emitted += 1
        self.last_emitted_at = now
        logger.info(
            "simulation.fleet_event_emitted",
            case_id=case_id,
            payment_id=payment_id,
            rail=template["rail"].value,
            arm=arm.value,
        )
