"""Continuous Fleet Failure Generator daemon running in the background."""

from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime
from typing import Any

from app.audit.models import ScheduledJob
from app.audit.repository import get_case_repository
from app.core.config import get_settings
from app.core.enums import ExperimentArm, JobStatus, PaymentRail
from app.core.logging import get_logger
from app.detection.models import RawFailureEvent
from app.intervention.orchestrator import get_recovery_orchestrator
from app.simulation.seeder import CAMPAIGN_TAGS, CUSTOMER_NAMES, FAILURE_TEMPLATES

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
        # Keep the cap well above require_human_above_paise so high-value cases
        # actually exceed the human-approval threshold instead of clamping to it.
        self.max_amount_paise: int = 50000000
        self.use_llm: bool = True
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
        max_amount_paise: int = 50000000,
        use_llm: bool = True,
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
                    await self._emit_single_event(repo)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("simulation.fleet_emit_error", error=str(exc))

            interval_seconds = 60.0 / max(1, self.events_per_minute)
            await asyncio.sleep(interval_seconds)

    async def _emit_single_event(self, repo: Any) -> None:
        """Generate, formulate strategy, and enqueue a single synthetic failure event."""
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

        # Distribute 50% agentic cases and 50% deterministic cases in fleet mode
        is_agentic = (self.events_emitted % 2 == 0) if self.use_llm else False
        case_tag = self.experiment_id or (
            "fleet_agentic" if is_agentic else "fleet_deterministic"
        )
        model_override = get_settings().agentic_model if is_agentic else None

        payment_id = f"pay_fleet_{secrets.token_hex(6)}"
        event_id = f"evt_fleet_{secrets.token_hex(6)}"
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
            campaign_id=secrets.choice(CAMPAIGN_TAGS),
            occurred_at=now,
            experiment_tag=case_tag,
            model_override=model_override,
            metadata={"is_agentic": is_agentic, "source": "fleet"},
        )

        orchestrator = get_recovery_orchestrator()
        case = await orchestrator.process_failure_event(
            raw_event,
            experiment_arm_override=arm,
            use_llm=is_agentic,
        )

        # The diagnosis already ran inline above, so this row is the audit record
        # of that work rather than pending work: it is terminal on creation and
        # must not be claimable, or the worker would re-diagnose every event.
        job = ScheduledJob(
            case_id=case.case_id,
            job_type="INGESTION_DIAGNOSIS",
            due_at=now,
            status=JobStatus.DONE.value,
            idempotency_key=f"ingest_{payment_id}",
            payload={
                "event_id": event_id,
                "payment_id": payment_id,
                "use_llm": is_agentic,
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
            case_id=case.case_id,
            payment_id=payment_id,
            rail=template["rail"].value,
            arm=arm.value,
            is_agentic=is_agentic,
        )
