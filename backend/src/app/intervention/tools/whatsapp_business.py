"""Outbound customer recovery messages via Meta's WhatsApp Business Cloud API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

import httpx2

from app.core.config import get_settings
from app.core.constants import (
    OUTREACH_WHATSAPP_COST_PAISE,
    WHATSAPP_GRAPH_API_BASE,
    WHATSAPP_TEMPLATE_LANGUAGE_CODE,
)
from app.core.logging import get_logger
from app.intervention.tools.base import BaseInterventionTool, ToolExecutionResult

if TYPE_CHECKING:
    from app.audit.models import RecoveryCase
    from app.intervention.models import InterventionPlan

logger = get_logger(__name__)

HTTP_UNAUTHORIZED = 401


def _template_components(case: RecoveryCase, message: str) -> list[dict[str, Any]]:
    """Build the template's body parameters.

    A single free-text body variable carries the drafted dunning copy, so the
    approved template need only declare one {{1}} placeholder rather than a
    separate template per failure category.
    """
    return [
        {
            "type": "body",
            "parameters": [{"type": "text", "text": message}],
        }
    ]


class WhatsAppBusinessTool(BaseInterventionTool):
    """Sends a real templated message through Meta's Graph API.

    Falls back to the generic notification webhook when Cloud API credentials
    are absent, rather than failing the outreach outright: unlike a phone call,
    a customer message has an existing simulated/relay path worth preserving
    for merchants who have not onboarded a WhatsApp Business number yet.
    """

    def __init__(self, client: httpx2.AsyncClient | None = None) -> None:
        self._client = client

    def is_configured(self) -> bool:
        settings = get_settings()
        return bool(
            settings.whatsapp_phone_number_id
            and settings.whatsapp_api_token
            and settings.whatsapp_template_name
        )

    async def execute(
        self, case: RecoveryCase, plan: InterventionPlan
    ) -> ToolExecutionResult:
        """Send the case's drafted dunning message as a WhatsApp template.

        Raises if Cloud API credentials are only partially configured, so a
        caller can distinguish "not set up" (caught by is_configured before
        this runs) from "misconfigured" (a real error worth escalating).
        """
        settings = get_settings()
        phone_number_id = settings.whatsapp_phone_number_id
        token = settings.whatsapp_api_token
        template_name = settings.whatsapp_template_name

        if not (phone_number_id and token and template_name):
            msg = (
                "WhatsApp Business Cloud API credentials (phone number ID, "
                "access token, template name) are not fully configured"
            )
            logger.warning(
                "whatsapp_business.missing_credentials", case_id=case.case_id
            )
            raise ValueError(msg)

        to_number = case.contact_phone or case.failure_event.contact_phone
        if not to_number:
            msg = f"Case {case.case_id} has no contact_phone for a WhatsApp message"
            logger.warning(
                "whatsapp_business.missing_phone_number", case_id=case.case_id
            )
            raise ValueError(msg)

        message = (
            case.dunning_message_en
            or plan.dunning_message_en
            or f"Your payment of {case.currency} {case.amount_paise / 100:,.2f} "
            "could not be completed. Please retry from your original order."
        )

        endpoint = f"{WHATSAPP_GRAPH_API_BASE}/{phone_number_id}/messages"
        body = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": WHATSAPP_TEMPLATE_LANGUAGE_CODE},
                "components": _template_components(case, message),
            },
        }
        headers = {
            "Authorization": f"Bearer {token.get_secret_value()}",
            "Content-Type": "application/json",
        }

        logger.info(
            "whatsapp_business.attempt",
            case_id=case.case_id,
            idempotency_key=plan.idempotency_key,
            to_number_suffix=to_number[-4:],
        )

        try:
            if self._client:
                resp = await self._client.post(endpoint, json=body, headers=headers)
            else:
                async with httpx2.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(endpoint, json=body, headers=headers)

            if resp.is_success:
                response_data: dict[str, Any] = resp.json()
                messages = response_data.get("messages") or []
                message_id = str(
                    messages[0].get("id") if messages else f"wamid.{uuid4().hex[:24]}"
                )
                logger.info(
                    "whatsapp_business.message_sent",
                    case_id=case.case_id,
                    message_id=message_id,
                )
                payload = {
                    "message_id": message_id,
                    "to_number_suffix": to_number[-4:],
                    "template_name": template_name,
                    "idempotency_key": plan.idempotency_key,
                    "live_gateway_call": True,
                    "provider_response": response_data,
                }
                return ToolExecutionResult(
                    success=True,
                    action_taken="WHATSAPP_MESSAGE_SENT",
                    external_id=message_id,
                    cost_incurred_paise=OUTREACH_WHATSAPP_COST_PAISE,
                    data=payload,
                )

            logger.warning(
                "whatsapp_business.execution_failed",
                case_id=case.case_id,
                status_code=resp.status_code,
                response=resp.text,
            )
            action = (
                "WHATSAPP_AUTH_ERROR"
                if resp.status_code == HTTP_UNAUTHORIZED
                else "WHATSAPP_GATEWAY_ERROR"
            )
            return ToolExecutionResult(
                success=False,
                action_taken=action,
                external_id=None,
                cost_incurred_paise=0,
                data={"error": resp.text, "status_code": resp.status_code},
                error_message=resp.text,
            )
        except (httpx2.HTTPError, OSError, ValueError) as exc:
            logger.warning(
                "whatsapp_business.execution_failed",
                case_id=case.case_id,
                error=str(exc),
            )
            return ToolExecutionResult(
                success=False,
                action_taken="WHATSAPP_NETWORK_EXCEPTION",
                external_id=None,
                cost_incurred_paise=0,
                data={"error": str(exc)},
                error_message=str(exc),
            )


__all__ = ["WhatsAppBusinessTool"]
