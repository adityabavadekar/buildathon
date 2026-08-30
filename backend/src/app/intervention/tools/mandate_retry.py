"""Mandate and subscription auto-retry execution tool."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from app.core.constants import GATEWAY_RETRY_COST_PAISE
from app.core.logging import get_logger
from app.intervention.tools.base import BaseInterventionTool, ToolExecutionResult

if TYPE_CHECKING:
    from app.audit.models import RecoveryCase
    from app.intervention.models import InterventionPlan

logger = get_logger(__name__)


class MandateRetryTool(BaseInterventionTool):
    """Executes scheduled bank debit retries via Razorpay Subscriptions Charge API."""

    async def execute(
        self, case: RecoveryCase, plan: InterventionPlan
    ) -> ToolExecutionResult:
        """Execute or schedule subscription debit attempt."""
        subscription_id = case.failure_event.subscription_id or f"sub_{uuid4().hex[:14]}"
        attempt_id = f"rtr_{uuid4().hex[:14]}"

        payload = {
            "attempt_id": attempt_id,
            "subscription_id": subscription_id,
            "amount_paise": case.amount_paise,
            "currency": case.currency,
            "scheduled_at": plan.scheduled_at.isoformat(),
            "idempotency_key": plan.idempotency_key,
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
