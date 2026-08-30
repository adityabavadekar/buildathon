"""Customer notification and dunning communication tool."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar
from uuid import uuid4

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


class CustomerNotificationTool(BaseInterventionTool):
    """Dispatches templated or personalized dunning messages with cost accounting."""

    CHANNEL_COSTS: ClassVar[dict[OutreachChannel, int]] = {
        OutreachChannel.WHATSAPP: OUTREACH_WHATSAPP_COST_PAISE,
        OutreachChannel.SMS: OUTREACH_SMS_COST_PAISE,
        OutreachChannel.EMAIL: OUTREACH_EMAIL_COST_PAISE,
        OutreachChannel.VOICE_CALL: OUTREACH_VOICE_COST_PAISE,
    }

    async def execute(
        self, case: RecoveryCase, plan: InterventionPlan
    ) -> ToolExecutionResult:
        """Dispatch notification to customer via selected channel."""
        channel = plan.channel or OutreachChannel.WHATSAPP
        cost_paise = self.CHANNEL_COSTS.get(channel, OUTREACH_WHATSAPP_COST_PAISE)
        message_id = f"msg_{uuid4().hex[:14]}"

        # Compose clean dunning message
        amount_fmt = f"{case.currency} {case.amount_paise / 100:,.2f}"
        message_text = (
            f"Dear Customer, your payment of {amount_fmt} could not be completed. "
            f"Please complete it securely: {plan.rationale}"
        )

        payload = {
            "message_id": message_id,
            "customer_id": case.failure_event.customer_id,
            "channel": channel.value,
            "message_text": message_text,
            "cost_paise": cost_paise,
            "idempotency_key": plan.idempotency_key,
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
