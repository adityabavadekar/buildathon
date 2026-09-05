"""Mandate and subscription auto-retry execution tool integrating with Razorpay Subscriptions API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

import httpx2

from app.core.constants import GATEWAY_RETRY_COST_PAISE, RAZORPAY_API_BASE
from app.core.logging import get_logger
from app.integrations.auth import resolve_razorpay_auth
from app.intervention.tools.base import (
    BaseInterventionTool,
    RazorpayGatewayError,
    ToolExecutionResult,
    describe_razorpay_error,
)

if TYPE_CHECKING:
    from app.audit.models import RecoveryCase
    from app.intervention.models import InterventionPlan

logger = get_logger(__name__)


class MandateRetryTool(BaseInterventionTool):
    """Executes scheduled bank debit retries via Razorpay Subscriptions Charge API."""

    def __init__(self, client: httpx2.AsyncClient | None = None) -> None:
        self._client = client

    async def execute(
        self, case: RecoveryCase, plan: InterventionPlan
    ) -> ToolExecutionResult:
        """Execute subscription debit attempt against Razorpay Subscriptions Charge API."""
        subscription_id = (
            case.failure_event.subscription_id or f"sub_{uuid4().hex[:14]}"
        )

        rzp = await resolve_razorpay_auth()
        if not rzp:
            msg = "Razorpay credentials not configured; cannot retry mandate"
            raise RazorpayGatewayError(msg)

        auth_kwargs = rzp.httpx_kwargs()
        post_body = {
            "amount": case.amount_paise,
            "currency": case.currency,
            "notes": {
                "case_id": case.case_id,
                "idempotency_key": plan.idempotency_key[:40],
                "scheduled_at": plan.scheduled_at.isoformat(),
            },
        }

        endpoint = f"{RAZORPAY_API_BASE}/v1/subscriptions/{subscription_id}/charge"
        try:
            if self._client:
                resp = await self._client.post(endpoint, json=post_body, **auth_kwargs)
            else:
                async with httpx2.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(endpoint, json=post_body, **auth_kwargs)
        except (httpx2.HTTPError, OSError, ValueError) as exc:
            logger.warning("razorpay.api.subscription_charge_exception", error=str(exc))
            msg = f"Razorpay subscription charge API call failed: {exc}"
            raise RazorpayGatewayError(msg) from exc

        if not resp.is_success:
            logger.warning(
                "razorpay.api.subscription_charge_error",
                status_code=resp.status_code,
                response=resp.text,
            )
            msg = describe_razorpay_error(
                "Razorpay subscription charge", resp.status_code, resp.text
            )
            raise RazorpayGatewayError(msg)

        rzp_data: dict[str, Any] = resp.json()
        charge_id = str(rzp_data.get("id", f"rtr_{uuid4().hex[:14]}"))
        logger.info(
            "razorpay.api.subscription_charged",
            case_id=case.case_id,
            subscription_id=subscription_id,
            charge_id=charge_id,
        )
        payload = {
            "attempt_id": charge_id,
            "subscription_id": subscription_id,
            "amount_paise": case.amount_paise,
            "currency": case.currency,
            "scheduled_at": plan.scheduled_at.isoformat(),
            "idempotency_key": plan.idempotency_key,
            "live_gateway_call": True,
            "gateway_response": rzp_data,
        }
        return ToolExecutionResult(
            success=True,
            action_taken="MANDATE_RETRY_SCHEDULED",
            external_id=charge_id,
            cost_incurred_paise=GATEWAY_RETRY_COST_PAISE,
            data=payload,
        )
