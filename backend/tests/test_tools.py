"""Tests for recovery intervention execution tools and cost accounting."""

from datetime import UTC, datetime

import pytest

from app.audit.models import RecoveryCase
from app.core.enums import InterventionType, OutreachChannel
from app.detection.models import RawFailureEvent
from app.intervention.models import InterventionPlan
from app.intervention.tools.mandate_retry import MandateRetryTool
from app.intervention.tools.notification import CustomerNotificationTool
from app.intervention.tools.payment_link import RazorpayPaymentLinkTool


def _create_test_case(amount_paise: int = 250000) -> RecoveryCase:
    event = RawFailureEvent(
        event_id="evt_tool_test",
        payment_id="pay_tool_test",
        customer_id="cust_tool_test",
        amount_paise=amount_paise,
        error_code="BAD_REQUEST_ERROR",
        occurred_at=datetime.now(UTC),
    )
    return RecoveryCase(
        case_id="case_tool_test",
        amount_paise=amount_paise,
        failure_event=event,
    )


@pytest.mark.anyio
async def test_razorpay_payment_link_tool_execution() -> None:
    tool = RazorpayPaymentLinkTool()
    case = _create_test_case(amount_paise=100000)  # INR 1,000
    plan = InterventionPlan(
        plan_id="plan_pl",
        case_id=case.case_id,
        intervention_type=InterventionType.INCENTIVIZED_LINK,
        discount_bps=500,  # 5%
        discount_paise=5000,  # INR 50
        scheduled_at=datetime.now(UTC),
        idempotency_key="idem_pl_1",
        rationale="Send 5% discount link",
    )

    result = await tool.execute(case, plan)
    assert result.success is True
    assert result.action_taken == "PAYMENT_LINK_CREATED"
    assert result.cost_incurred_paise == 0
    assert result.data["amount_paise"] == 95000  # 100000 - 5000
    assert "https://rzp.io/i/" in result.data["short_url"]


@pytest.mark.anyio
async def test_mandate_retry_tool_execution() -> None:
    tool = MandateRetryTool()
    case = _create_test_case(amount_paise=500000)  # INR 5,000
    plan = InterventionPlan(
        plan_id="plan_mr",
        case_id=case.case_id,
        intervention_type=InterventionType.SMART_RETRY,
        scheduled_at=datetime.now(UTC),
        idempotency_key="idem_mr_1",
        rationale="Retry mandate after salary cycle",
    )

    result = await tool.execute(case, plan)
    assert result.success is True
    assert result.action_taken == "MANDATE_RETRY_SCHEDULED"
    assert result.cost_incurred_paise == 250  # INR 2.50


@pytest.mark.anyio
async def test_customer_notification_tool_whatsapp_and_sms() -> None:
    tool = CustomerNotificationTool()
    case = _create_test_case(amount_paise=150000)

    # WhatsApp
    wa_plan = InterventionPlan(
        plan_id="plan_wa",
        case_id=case.case_id,
        intervention_type=InterventionType.CUSTOMER_NUDGE,
        channel=OutreachChannel.WHATSAPP,
        scheduled_at=datetime.now(UTC),
        idempotency_key="idem_wa",
        rationale="WhatsApp recovery nudge",
    )
    wa_result = await tool.execute(case, wa_plan)
    assert wa_result.success is True
    assert wa_result.cost_incurred_paise == 50  # INR 0.50

    # SMS
    sms_plan = InterventionPlan(
        plan_id="plan_sms",
        case_id=case.case_id,
        intervention_type=InterventionType.CUSTOMER_NUDGE,
        channel=OutreachChannel.SMS,
        scheduled_at=datetime.now(UTC),
        idempotency_key="idem_sms",
        rationale="SMS fallback nudge",
    )
    sms_result = await tool.execute(case, sms_plan)
    assert sms_result.success is True
    assert sms_result.cost_incurred_paise == 20  # INR 0.20
