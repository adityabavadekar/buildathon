"""Razorpay Smart Payment Link generation tool.

Generates single-use, short-lived fallback payment links for failed mandates
and checkout drop-offs. Integrates with Razorpay API when credentials are provided.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx2

from app.core.constants import (
    CHECKOUT_DROP_OFF_LINK_VALIDITY_MINUTES,
    RAZORPAY_API_BASE,
)
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


class RazorpayPaymentLinkTool(BaseInterventionTool):
    """Generates dynamic, single-use Razorpay payment links."""

    def __init__(self, client: httpx2.AsyncClient | None = None) -> None:
        self._client = client

    async def execute(
        self, case: RecoveryCase, plan: InterventionPlan
    ) -> ToolExecutionResult:
        """Create a short-lived recovery link with optional incentive discount."""
        now = datetime.now(UTC)
        validity_minutes = (
            CHECKOUT_DROP_OFF_LINK_VALIDITY_MINUTES if plan.discount_bps > 0 else 1440
        )
        expire_by = now + timedelta(minutes=validity_minutes)

        final_amount_paise = max(100, case.amount_paise - plan.discount_paise)

        rzp = await resolve_razorpay_auth()
        if not rzp:
            msg = "Razorpay credentials not configured; cannot create payment link"
            raise RazorpayGatewayError(msg)

        auth_kwargs = rzp.httpx_kwargs()
        post_body = {
            "amount": final_amount_paise,
            "currency": case.currency,
            "accept_partial": False,
            "description": f"Recovery for {case.case_id}",
            "reference_id": plan.idempotency_key[:40],
            "expire_by": int(expire_by.timestamp()),
        }

        try:
            if self._client:
                resp = await self._client.post(
                    f"{RAZORPAY_API_BASE}/v1/payment_links",
                    json=post_body,
                    **auth_kwargs,
                )
            else:
                async with httpx2.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        f"{RAZORPAY_API_BASE}/v1/payment_links",
                        json=post_body,
                        **auth_kwargs,
                    )
        except (httpx2.HTTPError, OSError, ValueError) as exc:
            logger.warning("razorpay.api.exception", error=str(exc))
            msg = f"Razorpay payment link API call failed: {exc}"
            raise RazorpayGatewayError(msg) from exc

        if not resp.is_success:
            logger.warning(
                "razorpay.api.error",
                status_code=resp.status_code,
                response=resp.text,
            )
            msg = describe_razorpay_error(
                "Razorpay payment link creation", resp.status_code, resp.text
            )
            raise RazorpayGatewayError(msg)

        rzp_data: dict[str, Any] = resp.json()
        link_id = str(rzp_data.get("id", ""))
        short_url = str(rzp_data.get("short_url", ""))
        logger.info(
            "razorpay.api.payment_link_created",
            case_id=case.case_id,
            link_id=link_id,
            short_url=short_url,
        )
        payload = {
            "id": link_id,
            "short_url": short_url,
            "amount_paise": final_amount_paise,
            "currency": case.currency,
            "reference_id": plan.idempotency_key,
            "expire_by": expire_by.isoformat(),
            "discount_paise": plan.discount_paise,
            "customer_id": case.failure_event.customer_id,
            "live_gateway_call": True,
        }
        case.payment_link_id = link_id
        case.payment_link_url = short_url
        case.payment_link_expires_at = expire_by
        return ToolExecutionResult(
            success=True,
            action_taken="PAYMENT_LINK_CREATED",
            external_id=link_id,
            cost_incurred_paise=0,
            data=payload,
        )
