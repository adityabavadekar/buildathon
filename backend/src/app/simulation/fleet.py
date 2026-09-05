"""Continuous Fleet Failure Generator daemon running in the background."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
from collections import deque
from datetime import UTC, datetime
from typing import Any

import httpx2

from app.core.constants import (
    FLEET_MAX_PENDING_RECOVERIES,
    FLEET_RECOVERY_CHECK_PROBABILITY,
    MAX_FLEET_EVENTS_PER_MINUTE,
)
from app.core.credential_resolver import resolve_webhook_secret
from app.core.enums import FailureCategory, PaymentRail
from app.core.logging import get_logger
from app.simulation.seeder import CAMPAIGN_TAGS, CUSTOMER_NAMES, FAILURE_TEMPLATES

logger = get_logger(__name__)

# Fleet-generated rails must round-trip through the webhook's `method` string
# field the same way a real gateway payload would, not through the internal enum.
_RAIL_TO_WEBHOOK_METHOD: dict[PaymentRail, str] = {
    PaymentRail.UPI: "upi",
    PaymentRail.UPI_AUTOPAY: "upi_autopay",
    PaymentRail.ENACH: "enach",
    PaymentRail.CARD: "card",
    PaymentRail.NETBANKING: "netbanking",
    PaymentRail.B2B_INVOICE: "b2b_invoice",
}

_FLEET_WEBHOOK_BASE_URL = "http://fleet-internal"

# Reuses the seeder's category-shaped recovery rates so fleet's "no further
# failure" path is not a fabricated separate constant. Holdout is deliberately
# absent: fleet routes every event through the real webhook, which assigns
# the experiment arm itself, and this simulator does not see which arm a
# payment landed in.
_RECOVERY_RATE_BY_CATEGORY: dict[FailureCategory, float] = {
    FailureCategory.TRANSIENT_BANK_WINDOW: 0.72,
    FailureCategory.CHECKOUT_DROP_OFF: 0.44,
    FailureCategory.LIQUIDITY_CONSTRAINT: 0.38,
}
_DEFAULT_RECOVERY_RATE = 0.25


class _PendingRecovery:
    """A payment fleet emitted as failed, tracked so a later tick can decide
    whether that customer's payment eventually goes through with no further
    failure -- the flow that only ever ends in more failures otherwise.
    """

    __slots__ = ("amount_paise", "category", "payment_id")

    def __init__(
        self, payment_id: str, amount_paise: int, category: FailureCategory
    ) -> None:
        self.payment_id = payment_id
        self.amount_paise = amount_paise
        self.category = category


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
        self.recoveries_emitted: int = 0
        self.started_at: datetime | None = None
        self.last_emitted_at: datetime | None = None
        self._task: asyncio.Task[None] | None = None
        self._pending_recoveries: deque[_PendingRecovery] = deque(
            maxlen=FLEET_MAX_PENDING_RECOVERIES
        )

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
        self.events_per_minute = max(
            1, min(MAX_FLEET_EVENTS_PER_MINUTE, events_per_minute)
        )
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
            "recoveries_emitted": self.recoveries_emitted,
            "pending_recoveries": len(self._pending_recoveries),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_emitted_at": self.last_emitted_at.isoformat()
            if self.last_emitted_at
            else None,
        }

    async def _run_loop(self) -> None:
        """Continuous event generation loop.

        Each tick either emits a new failure or, at
        FLEET_RECOVERY_CHECK_PROBABILITY odds when a payment is pending,
        resolves one of those payments as recovered -- otherwise every fleet
        case would only ever fail again, never showing the "customer paid,
        no further failure" half of the recovery lifecycle.
        """
        while self.is_running:
            if not self.is_paused:
                try:
                    if (
                        self._pending_recoveries
                        and secrets.randbelow(1000)
                        < FLEET_RECOVERY_CHECK_PROBABILITY * 1000
                    ):
                        await self._maybe_emit_recovery()
                    else:
                        await self._emit_single_event()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("simulation.fleet_emit_error", error=str(exc))

            interval_seconds = 60.0 / max(1, self.events_per_minute)
            await asyncio.sleep(interval_seconds)

    def _sign_payload(self, body_bytes: bytes) -> str | None:
        """Return the X-Razorpay-Signature header value, or None if unsigned."""
        secret = resolve_webhook_secret()
        if not secret:
            return None
        return hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()

    async def _post_webhook(
        self, fastapi_app: Any, webhook_body: dict[str, Any], log_id: str
    ) -> dict[str, Any] | None:
        """POST a webhook body in-process through the real route. Returns the
        parsed response on success, or None (already logged) on failure.
        """
        body_bytes = json.dumps(webhook_body).encode("utf-8")
        signature = self._sign_payload(body_bytes)
        headers = {"Content-Type": "application/json"}
        if signature is not None:
            headers["X-Razorpay-Signature"] = signature

        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=fastapi_app),
            base_url=_FLEET_WEBHOOK_BASE_URL,
        ) as client:
            try:
                response = await client.post(
                    "/api/webhooks/razorpay", content=body_bytes, headers=headers
                )
                if not response.is_success:
                    logger.warning(
                        "simulation.fleet_webhook_post_failed",
                        payment_id=log_id,
                        status_code=response.status_code,
                        body=response.text,
                    )
                    return None
                return dict(response.json())
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "simulation.fleet_webhook_post_failed",
                    payment_id=log_id,
                    error=str(exc),
                )
                return None

    async def _emit_single_event(self) -> None:
        """Generate a synthetic failure event and POST it through the real webhook route.

        Routing in-process through the webhook endpoint (instead of calling the
        orchestrator directly) means fleet traffic exercises the same HMAC
        verification and async job-queue path real Razorpay traffic uses.
        """
        # Imported lazily: app.main wires up the simulation routes that import
        # this module, so importing app.main at module scope would be circular.
        from app.main import app as fastapi_app  # noqa: PLC0415

        available_templates = [
            t for t in FAILURE_TEMPLATES if t["rail"].value in self.rails
        ] or FAILURE_TEMPLATES
        template = secrets.choice(available_templates)
        cust = secrets.choice(CUSTOMER_NAMES)
        amount = secrets.choice(template["amounts"])
        amount = max(self.min_amount_paise, min(self.max_amount_paise, amount))

        # Distribute 50% agentic cases and 50% deterministic cases in fleet mode,
        # purely for the experiment_tag label; the worker (not this payload)
        # decides actual LLM usage uniformly via configured_providers().
        is_agentic = (self.events_emitted % 2 == 0) if self.use_llm else False
        case_tag = self.experiment_id or (
            "fleet_agentic" if is_agentic else "fleet_deterministic"
        )

        payment_id = f"pay_fleet_{secrets.token_hex(6)}"
        rail: PaymentRail = template["rail"]
        method = _RAIL_TO_WEBHOOK_METHOD.get(rail, rail.value.lower())

        webhook_body = {
            "event": "payment.failed",
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "amount": amount,
                        "currency": "INR",
                        "method": method,
                        "error_code": template["error_code"],
                        "error_description": template["error_reason"],
                        "error_reason": template["error_reason"],
                        "customer_id": cust[0],
                        "contact": cust[1],
                        "email": cust[2],
                        "notes": {
                            "campaign_id": secrets.choice(CAMPAIGN_TAGS),
                            "experiment_tag": case_tag,
                        },
                    }
                }
            },
        }
        response_data = await self._post_webhook(fastapi_app, webhook_body, payment_id)
        if response_data is None:
            return

        now = datetime.now(UTC)
        self.events_emitted += 1
        self.last_emitted_at = now
        self._pending_recoveries.append(
            _PendingRecovery(payment_id, amount, template["category"])
        )
        logger.info(
            "simulation.fleet_event_emitted",
            case_id=response_data.get("case_id"),
            payment_id=payment_id,
            rail=rail.value,
            is_agentic=is_agentic,
            action_taken=response_data.get("action_taken"),
        )

    async def _maybe_emit_recovery(self) -> None:
        """Pop one pending payment and, at its category's recovery rate, send a
        payment.captured webhook for it -- the "customer paid, no further
        failure" half of the lifecycle that pure failure generation never
        exercises on its own.

        A payment that rolls unlucky is dropped from tracking rather than
        requeued: fleet has no model of a customer being retried indefinitely,
        and the case still exists in whatever state its own retry/outreach
        schedule left it in.
        """
        from app.main import app as fastapi_app  # noqa: PLC0415

        pending = self._pending_recoveries.popleft()
        rate = _RECOVERY_RATE_BY_CATEGORY.get(pending.category, _DEFAULT_RECOVERY_RATE)
        if secrets.randbelow(1000) >= rate * 1000:
            return

        webhook_body = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": pending.payment_id,
                        "amount": pending.amount_paise,
                        "currency": "INR",
                    }
                }
            },
        }
        response_data = await self._post_webhook(
            fastapi_app, webhook_body, pending.payment_id
        )
        if response_data is None:
            return

        self.recoveries_emitted += 1
        self.last_emitted_at = datetime.now(UTC)
        logger.info(
            "simulation.fleet_recovery_emitted",
            case_id=response_data.get("case_id"),
            payment_id=pending.payment_id,
            action_taken=response_data.get("action_taken"),
        )
