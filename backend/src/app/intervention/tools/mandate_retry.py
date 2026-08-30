"""Mandate and subscription auto-retry execution tool integrating with Razorpay Subscriptions API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

import httpx2
from pydantic import SecretStr

from app.core.config import get_settings
from app.core.constants import GATEWAY_RETRY_COST_PAISE
from app.core.logging import get_logger
from app.intervention.tools.base import BaseInterventionTool, ToolExecutionResult

if TYPE_CHECKING:
    from app.audit.models import RecoveryCase
    from app.intervention.models import InterventionPlan

logger = get_logger(__name__)

HTTP_NOT_FOUND = 404


def _extract_secret_str(val: SecretStr | str | None) -> str | None:
    if val is None:
        return None
    if isinstance(val, SecretStr):
        return val.get_secret_value().strip()
    return str(val).strip()


class MandateRetryTool(BaseInterventionTool):
    """Executes scheduled bank debit retries via Razorpay Subscriptions Charge API."""

    def __init__(self, client: httpx2.AsyncClient | None = None) -> None:
        self._client = client

    async def execute(
        self, case: RecoveryCase, plan: InterventionPlan
    ) -> ToolExecutionResult:
        """Execute or schedule subscription debit attempt against Razorpay API."""
        subscription_id = (
            case.failure_event.subscription_id or f"sub_{uuid4().hex[:14]}"
        )
        attempt_id = f"rtr_{uuid4().hex[:14]}"

        settings = get_settings()
        key_id = settings.razorpay_key_id
        key_secret = _extract_secret_str(settings.razorpay_key_secret)

        # 1. Live Gateway Execution path when credentials are provided
        if key_id and key_secret:
            auth = (key_id, key_secret)
            post_body = {
                "amount": case.amount_paise,
                "currency": case.currency,
                "notes": {
                    "case_id": case.case_id,
                    "idempotency_key": plan.idempotency_key[:40],
                    "scheduled_at": plan.scheduled_at.isoformat(),
                },
            }

            try:
                endpoint = f"https://api.razorpay.com/v1/subscriptions/{subscription_id}/charge"
                if self._client:
                    resp = await self._client.post(endpoint, json=post_body, auth=auth)
                else:
                    async with httpx2.AsyncClient(timeout=10.0) as client:
                        resp = await client.post(endpoint, json=post_body, auth=auth)

                if resp.is_success:
                    rzp_data: dict[str, Any] = resp.json()
                    charge_id = str(rzp_data.get("id", attempt_id))
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

                # In local dev environment with synthetic sub_ IDs, allow sandbox fallback
                if settings.env != "production" and (
                    resp.status_code == HTTP_NOT_FOUND
                    or "no Route matched" in resp.text
                ):
                    logger.info(
                        "razorpay.api.subscription_dev_simulation",
                        case_id=case.case_id,
                        subscription_id=subscription_id,
                    )
                    payload = {
                        "attempt_id": attempt_id,
                        "subscription_id": subscription_id,
                        "amount_paise": case.amount_paise,
                        "currency": case.currency,
                        "scheduled_at": plan.scheduled_at.isoformat(),
                        "idempotency_key": plan.idempotency_key,
                        "live_gateway_call": False,
                        "sandbox_simulated": True,
                    }
                    return ToolExecutionResult(
                        success=True,
                        action_taken="MANDATE_RETRY_SCHEDULED",
                        external_id=attempt_id,
                        cost_incurred_paise=GATEWAY_RETRY_COST_PAISE,
                        data=payload,
                    )

                logger.warning(
                    "razorpay.api.subscription_charge_error",
                    status_code=resp.status_code,
                    response=resp.text,
                )
                return ToolExecutionResult(
                    success=False,
                    action_taken="MANDATE_RETRY_GATEWAY_ERROR",
                    external_id=None,
                    cost_incurred_paise=0,
                    data={"error": resp.text, "status_code": resp.status_code},
                )
            except (httpx2.HTTPError, OSError, ValueError) as exc:
                logger.warning(
                    "razorpay.api.subscription_charge_exception", error=str(exc)
                )
                return ToolExecutionResult(
                    success=False,
                    action_taken="MANDATE_RETRY_NETWORK_EXCEPTION",
                    external_id=None,
                    cost_incurred_paise=0,
                    data={"error": str(exc)},
                )

        # 2. In sandbox/dev environment when keys are absent
        if settings.env == "production":
            return ToolExecutionResult(
                success=False,
                action_taken="MANDATE_RETRY_MISSING_CREDENTIALS",
                external_id=None,
                cost_incurred_paise=0,
                data={"error": "Razorpay credentials not configured in production"},
            )

        payload = {
            "attempt_id": attempt_id,
            "subscription_id": subscription_id,
            "amount_paise": case.amount_paise,
            "currency": case.currency,
            "scheduled_at": plan.scheduled_at.isoformat(),
            "idempotency_key": plan.idempotency_key,
            "live_gateway_call": False,
            "sandbox_simulated": True,
        }

        logger.info(
            "intervention.tool.mandate_retry_scheduled",
            case_id=case.case_id,
            subscription_id=subscription_id,
            attempt_id=attempt_id,
            cost_incurred_paise=GATEWAY_RETRY_COST_PAISE,
        )

        return ToolExecutionResult(
            success=True,
            action_taken="MANDATE_RETRY_SCHEDULED",
            external_id=attempt_id,
            cost_incurred_paise=GATEWAY_RETRY_COST_PAISE,
            data=payload,
        )
