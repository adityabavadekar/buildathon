"""Customer notification and dunning communication tool with real outbound provider dispatch."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar
from uuid import uuid4

import httpx2
from pydantic import SecretStr

from app.core.config import get_settings
from app.core.constants import (
    OUTREACH_EMAIL_COST_PAISE,
    OUTREACH_SMS_COST_PAISE,
    OUTREACH_VOICE_COST_PAISE,
    OUTREACH_WHATSAPP_COST_PAISE,
)
from app.core.enums import OutreachChannel
from app.core.logging import get_logger
from app.intervention.tools.base import BaseInterventionTool, ToolExecutionResult

if TYPE_CHECKING:
    from app.audit.models import RecoveryCase
    from app.intervention.models import InterventionPlan

logger = get_logger(__name__)


def _extract_secret_str(val: SecretStr | str | None) -> str | None:
    if val is None:
        return None
    if isinstance(val, SecretStr):
        return val.get_secret_value().strip()
    return str(val).strip()


class CustomerNotificationTool(BaseInterventionTool):
    """Dispatches templated RBI-compliant dunning messages with cost accounting and webhook delivery."""

    CHANNEL_COSTS: ClassVar[dict[OutreachChannel, int]] = {
        OutreachChannel.WHATSAPP: OUTREACH_WHATSAPP_COST_PAISE,
        OutreachChannel.SMS: OUTREACH_SMS_COST_PAISE,
        OutreachChannel.EMAIL: OUTREACH_EMAIL_COST_PAISE,
        OutreachChannel.VOICE_CALL: OUTREACH_VOICE_COST_PAISE,
    }

    def __init__(self, client: httpx2.AsyncClient | None = None) -> None:
        self._client = client

    async def execute(
        self, case: RecoveryCase, plan: InterventionPlan
    ) -> ToolExecutionResult:
        """Dispatch notification to customer via selected channel."""
        channel = plan.channel or OutreachChannel.WHATSAPP
        cost_paise = self.CHANNEL_COSTS.get(channel, OUTREACH_WHATSAPP_COST_PAISE)
        message_id = f"msg_{uuid4().hex[:14]}"

        # Compose clean, RBI-compliant dunning message template
        amount_fmt = f"{case.currency} {case.amount_paise / 100:,.2f}"
        short_link = f"https://rzp.io/i/{case.case_id[:8]}"
        message_text = (
            f"Dear Customer, your payment of {amount_fmt} could not be completed. "
            f"Reason: {plan.rationale}. "
            f"Please complete it securely: {short_link}. "
            "Reply STOP to opt out of payment alerts."
        )

        settings = get_settings()
        webhook_url = settings.notification_webhook_url
        wa_token = _extract_secret_str(settings.whatsapp_api_token)

        # 1. Live Provider Dispatch if webhook endpoint is configured
        if webhook_url:
            headers = {"Content-Type": "application/json"}
            if wa_token:
                headers["Authorization"] = f"Bearer {wa_token}"

            post_body = {
                "message_id": message_id,
                "customer_id": case.failure_event.customer_id,
                "channel": channel.value,
                "message_text": message_text,
                "case_id": case.case_id,
                "amount_paise": case.amount_paise,
                "currency": case.currency,
                "idempotency_key": plan.idempotency_key,
            }

            try:
                if self._client:
                    resp = await self._client.post(
                        webhook_url, json=post_body, headers=headers
                    )
                else:
                    async with httpx2.AsyncClient(timeout=10.0) as client:
                        resp = await client.post(
                            webhook_url, json=post_body, headers=headers
                        )

                if resp.is_success:
                    provider_data: dict[str, Any] = resp.json() if resp.text else {}
                    dispatch_id = str(provider_data.get("id", message_id))
                    logger.info(
                        "notification.provider.dispatched",
                        case_id=case.case_id,
                        channel=channel.value,
                        dispatch_id=dispatch_id,
                    )
                    payload = {
                        "message_id": dispatch_id,
                        "customer_id": case.failure_event.customer_id,
                        "channel": channel.value,
                        "message_text": message_text,
                        "cost_paise": cost_paise,
                        "idempotency_key": plan.idempotency_key,
                        "live_dispatch_call": True,
                        "provider_response": provider_data,
                    }
                    return ToolExecutionResult(
                        success=True,
                        action_taken="NOTIFICATION_DISPATCHED",
                        external_id=dispatch_id,
                        cost_incurred_paise=cost_paise,
                        data=payload,
                    )

                logger.warning(
                    "notification.provider.error",
                    status_code=resp.status_code,
                    response=resp.text,
                )
                return ToolExecutionResult(
                    success=False,
                    action_taken="NOTIFICATION_GATEWAY_ERROR",
                    external_id=None,
                    cost_incurred_paise=0,
                    data={"error": resp.text, "status_code": resp.status_code},
                )
            except (httpx2.HTTPError, OSError, ValueError) as exc:
                logger.warning("notification.provider.exception", error=str(exc))
                return ToolExecutionResult(
                    success=False,
                    action_taken="NOTIFICATION_NETWORK_EXCEPTION",
                    external_id=None,
                    cost_incurred_paise=0,
                    data={"error": str(exc)},
                )

        # 2. In local development/sandbox when external dispatch URL is absent
        if settings.env == "production":
            return ToolExecutionResult(
                success=False,
                action_taken="NOTIFICATION_MISSING_PROVIDER",
                external_id=None,
                cost_incurred_paise=0,
                data={
                    "error": "Notification provider webhook not configured in production"
                },
            )

        payload = {
            "message_id": message_id,
            "customer_id": case.failure_event.customer_id,
            "channel": channel.value,
            "message_text": message_text,
            "cost_paise": cost_paise,
            "idempotency_key": plan.idempotency_key,
            "live_dispatch_call": False,
            "sandbox_simulated": True,
        }

        logger.info(
            "intervention.tool.notification_dispatched",
            case_id=case.case_id,
            channel=channel.value,
            message_id=message_id,
            cost_paise=cost_paise,
        )

        return ToolExecutionResult(
            success=True,
            action_taken="NOTIFICATION_DISPATCHED",
            external_id=message_id,
            cost_incurred_paise=cost_paise,
            data=payload,
        )
