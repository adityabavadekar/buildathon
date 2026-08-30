"""Razorpay Smart Payment Link generation tool.

Generates single-use, short-lived fallback payment links for failed mandates
and checkout drop-offs. Integrates with Razorpay API when credentials are provided.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import httpx2
from pydantic import SecretStr

from app.core.config import get_settings
from app.core.constants import CHECKOUT_DROP_OFF_LINK_VALIDITY_MINUTES
from app.core.logging import get_logger
from app.intervention.tools.base import BaseInterventionTool, ToolExecutionResult

if TYPE_CHECKING:
    from app.audit.models import RecoveryCase
    from app.intervention.models import InterventionPlan

logger = get_logger(__name__)

HTTP_TOO_MANY_REQUESTS = 429


def _extract_secret_str(val: SecretStr | str | None) -> str | None:
    if val is None:
        return None
    if isinstance(val, SecretStr):
        return val.get_secret_value().strip()
    return str(val).strip()


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

        settings = get_settings()
        key_id = settings.razorpay_key_id
        key_secret = _extract_secret_str(settings.razorpay_key_secret)

        # 1. Live Gateway Execution path when credentials are provided
        if key_id and key_secret:
            auth = (key_id, key_secret)
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
                        "https://api.razorpay.com/v1/payment_links",
                        json=post_body,
                        auth=auth,
                    )
                else:
                    async with httpx2.AsyncClient(timeout=10.0) as client:
                        resp = await client.post(
                            "https://api.razorpay.com/v1/payment_links",
                            json=post_body,
                            auth=auth,
                        )

                if resp.is_success:
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
                    return ToolExecutionResult(
                        success=True,
                        action_taken="PAYMENT_LINK_CREATED",
                        external_id=link_id,
                        cost_incurred_paise=0,
                        data=payload,
                    )

                # Handle 429 Test Mode Rate Limit in local development environments
                if (
                    resp.status_code == HTTP_TOO_MANY_REQUESTS
                    and settings.env != "production"
                ):
                    logger.warning(
                        "razorpay.api.test_mode_rate_limit_fallback",
                        case_id=case.case_id,
                        response=resp.text,
                    )
                    sim_link_id = f"plink_sim_{uuid4().hex[:12]}"
                    sim_short_url = f"https://rzp.io/i/{sim_link_id[6:]}"
                    payload = {
                        "id": sim_link_id,
                        "short_url": sim_short_url,
                        "amount_paise": final_amount_paise,
                        "currency": case.currency,
                        "reference_id": plan.idempotency_key,
                        "expire_by": expire_by.isoformat(),
                        "discount_paise": plan.discount_paise,
                        "customer_id": case.failure_event.customer_id,
                        "live_gateway_call": False,
                        "sandbox_simulated": True,
                        "rate_limited": True,
                    }
                    return ToolExecutionResult(
                        success=True,
                        action_taken="PAYMENT_LINK_CREATED",
                        external_id=sim_link_id,
                        cost_incurred_paise=0,
                        data=payload,
                    )

                logger.warning(
                    "razorpay.api.error",
                    status_code=resp.status_code,
                    response=resp.text,
                )
                return ToolExecutionResult(
                    success=False,
                    action_taken="PAYMENT_LINK_GATEWAY_ERROR",
                    external_id=None,
                    cost_incurred_paise=0,
                    data={"error": resp.text, "status_code": resp.status_code},
                )
            except (httpx2.HTTPError, OSError, ValueError) as exc:
                logger.warning("razorpay.api.exception", error=str(exc))
                return ToolExecutionResult(
                    success=False,
                    action_taken="PAYMENT_LINK_NETWORK_EXCEPTION",
                    external_id=None,
                    cost_incurred_paise=0,
                    data={"error": str(exc)},
                )

        # 2. In sandbox/dev environment when keys are absent, generate deterministic simulation link
        if settings.env == "production":
            return ToolExecutionResult(
                success=False,
                action_taken="PAYMENT_LINK_MISSING_CREDENTIALS",
                external_id=None,
                cost_incurred_paise=0,
                data={"error": "Razorpay credentials not configured in production"},
            )

        sim_link_id = f"plink_sim_{uuid4().hex[:12]}"
        sim_short_url = f"https://rzp.io/i/{sim_link_id[6:]}"
        payload = {
            "id": sim_link_id,
            "short_url": sim_short_url,
            "amount_paise": final_amount_paise,
            "currency": case.currency,
            "reference_id": plan.idempotency_key,
            "expire_by": expire_by.isoformat(),
            "discount_paise": plan.discount_paise,
            "customer_id": case.failure_event.customer_id,
            "live_gateway_call": False,
            "sandbox_simulated": True,
        }

        return ToolExecutionResult(
            success=True,
            action_taken="PAYMENT_LINK_CREATED",
            external_id=sim_link_id,
            cost_incurred_paise=0,
            data=payload,
        )
