"""Razorpay Smart Payment Link generation tool.

Generates single-use, short-lived fallback payment links for failed mandates
and checkout drop-offs. Integrates with Razorpay API when credentials are provided.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import httpx2

from app.core.config import get_settings
from app.core.constants import CHECKOUT_DROP_OFF_LINK_VALIDITY_MINUTES
from app.core.logging import get_logger
from app.intervention.tools.base import BaseInterventionTool, ToolExecutionResult

if TYPE_CHECKING:
    from app.audit.models import RecoveryCase
    from app.intervention.models import InterventionPlan

logger = get_logger(__name__)


class RazorpayPaymentLinkTool(BaseInterventionTool):
    """Generates dynamic, single-use Razorpay payment links."""

    async def execute(
        self, case: RecoveryCase, plan: InterventionPlan
    ) -> ToolExecutionResult:
        """Create a short-lived recovery link with optional incentive discount."""
        now = datetime.now(UTC)
        # 15-minute validity for drop-offs; 24-hour validity for mandate fallback
        validity_minutes = (
            CHECKOUT_DROP_OFF_LINK_VALIDITY_MINUTES
            if plan.discount_bps > 0
            else 1440
        )
        expire_by = now + timedelta(minutes=validity_minutes)

        # Apply incentive discount if present in plan
        final_amount_paise = max(100, case.amount_paise - plan.discount_paise)
        fallback_link_id = f"plink_{uuid4().hex[:14]}"
        fallback_short_url = f"https://rzp.io/i/{fallback_link_id[6:]}"

        link_id = fallback_link_id
        short_url = fallback_short_url
        razorpay_live_response: dict[str, Any] | None = None

        settings = get_settings()
        key_id = settings.razorpay_key_id
        key_secret = (
            settings.razorpay_key_secret.get_secret_value().strip()
            if settings.razorpay_key_secret
            else None
        )

        if key_id and key_secret:
            try:
                auth = (key_id, key_secret)
                post_body = {
                    "amount": final_amount_paise,
                    "currency": case.currency,
                    "accept_partial": False,
                    "description": f"Recovery for {case.case_id}",
                    "reference_id": plan.idempotency_key[:40],
                    "expire_by": int(expire_by.timestamp()),
                }
                async with httpx2.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        "https://api.razorpay.com/v1/payment_links",
                        json=post_body,
                        auth=auth,
                    )
                    if resp.is_success:
                        rzp_data = resp.json()
                        link_id = rzp_data.get("id", fallback_link_id)
                        short_url = rzp_data.get("short_url", fallback_short_url)
                        razorpay_live_response = rzp_data
                        logger.info(
                            "razorpay.api.payment_link_created",
                            case_id=case.case_id,
                            link_id=link_id,
                            short_url=short_url,
                        )
                    else:
                        logger.warning(
                            "razorpay.api.error",
                            status_code=resp.status_code,
                            response=resp.text,
                        )
            except (httpx2.HTTPError, OSError, ValueError) as exc:
                logger.warning("razorpay.api.exception", error=str(exc))

        payload = {
            "id": link_id,
            "short_url": short_url,
            "amount_paise": final_amount_paise,
            "currency": case.currency,
            "reference_id": plan.idempotency_key,
            "expire_by": expire_by.isoformat(),
            "discount_paise": plan.discount_paise,
            "customer_id": case.failure_event.customer_id,
            "live_gateway_call": razorpay_live_response is not None,
        }

        logger.info(
            "intervention.tool.payment_link_created",
            case_id=case.case_id,
            link_id=link_id,
            amount_paise=final_amount_paise,
            discount_paise=plan.discount_paise,
        )

        return ToolExecutionResult(
            success=True,
            action_taken="PAYMENT_LINK_CREATED",
            external_id=link_id,
            cost_incurred_paise=0,  # Link generation is free; fee is charged on capture
            data=payload,
        )
