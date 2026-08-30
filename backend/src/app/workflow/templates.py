"""Built-in recovery workflow templates and stage transition blueprints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.enums import PaymentRail
from app.workflow.models import (
    WorkflowStoppingRules,
    WorkflowTemplate,
)

if TYPE_CHECKING:
    from app.detection.models import RawFailureEvent


def select_template_for_event(event: RawFailureEvent) -> WorkflowTemplate:
    """Select appropriate built-in workflow template based on failure event properties."""
    # 1. Payment degradation if error indicates switch/bank wide failure
    if (
        event.error_code in ("XT", "XU", "INTERNAL_SERVER_ERROR")
        and event.error_source == "bank"
    ):
        return WorkflowTemplate.PAYMENT_DEGRADATION

    # 2. Overdue invoice if B2B invoice rail or invoice identifier
    if (
        event.payment_rail == PaymentRail.B2B_INVOICE
        or "invoice" in event.payment_id.lower()
    ):
        return WorkflowTemplate.OVERDUE_INVOICE

    # 3. Subscription failure if recurring/subscription mandate
    if (
        event.payment_rail in (PaymentRail.UPI_AUTOPAY, PaymentRail.ENACH)
        or "sub_" in event.payment_id.lower()
    ):
        return WorkflowTemplate.SUBSCRIPTION_FAILURE

    # 4. Abandoned payment if checkout drop-off or OTP timeout
    if (
        event.error_source == "customer"
        or "timeout" in (event.error_reason or "").lower()
    ):
        return WorkflowTemplate.ABANDONED_PAYMENT

    # 5. Default to failed payment template
    return WorkflowTemplate.FAILED_PAYMENT


def configure_stopping_rules(
    template: WorkflowTemplate, amount_paise: int
) -> WorkflowStoppingRules:
    """Derive bounded stopping rules tailored to the workflow template and monetary scale."""
    if template == WorkflowTemplate.OVERDUE_INVOICE:
        return WorkflowStoppingRules(
            max_retries=2,
            max_touches=6,
            max_duration_hours=720,  # 30 days
            max_discount_bps=500,  # 5% max on invoice
            stop_on_recovered=True,
            stop_on_human_pause=True,
        )

    if template == WorkflowTemplate.SUBSCRIPTION_FAILURE:
        return WorkflowStoppingRules(
            max_retries=4,
            max_touches=5,
            max_duration_hours=336,  # 14 days dunning cycle
            max_discount_bps=1000,
            stop_on_recovered=True,
            stop_on_human_pause=True,
        )

    if template == WorkflowTemplate.ABANDONED_PAYMENT:
        return WorkflowStoppingRules(
            max_retries=1,
            max_touches=3,
            max_duration_hours=48,  # 2 days abandonment window
            max_discount_bps=1500,  # 15% incentive nudge
            stop_on_recovered=True,
            stop_on_human_pause=True,
        )

    if template == WorkflowTemplate.PAYMENT_DEGRADATION:
        return WorkflowStoppingRules(
            max_retries=3,
            max_touches=4,
            max_duration_hours=72,
            max_discount_bps=0,
            stop_on_recovered=True,
            stop_on_human_pause=True,
        )

    # Standard FAILED_PAYMENT rules
    return WorkflowStoppingRules(
        max_retries=3,
        max_touches=4,
        max_duration_hours=168,  # 7 days
        max_discount_bps=1000,
        stop_on_recovered=True,
        stop_on_human_pause=True,
    )
