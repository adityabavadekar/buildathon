"""Tests for recovery intervention execution tools, contract mocks, and cost accounting."""

import json
from datetime import UTC, datetime
from typing import Any

import httpx2
import pytest

from app.audit.models import RecoveryCase
from app.core.config import get_settings
from app.core.enums import InterventionType, OutreachChannel
from app.detection.models import RawFailureEvent
from app.intervention.models import InterventionPlan
from app.intervention.tools.base import RazorpayGatewayError
from app.intervention.tools.mandate_retry import MandateRetryTool
from app.intervention.tools.notification import CustomerNotificationTool
from app.intervention.tools.payment_link import RazorpayPaymentLinkTool


def _create_test_case(amount_paise: int = 250000) -> RecoveryCase:
    event = RawFailureEvent(
        event_id="evt_tool_test",
        payment_id="pay_tool_test",
        customer_id="cust_tool_test",
        amount_paise=amount_paise,
        subscription_id="sub_test_mandate_99",
        error_code="BAD_REQUEST_ERROR",
        occurred_at=datetime.now(UTC),
    )
    return RecoveryCase(
        case_id="case_tool_test",
        amount_paise=amount_paise,
        failure_event=event,
    )


@pytest.mark.anyio
async def test_razorpay_payment_link_no_credentials_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without Razorpay credentials, the tool must fail cleanly, never fabricate a link."""

    async def _no_auth() -> None:
        return None

    monkeypatch.setattr(
        "app.intervention.tools.payment_link.resolve_razorpay_auth", _no_auth
    )

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

    with pytest.raises(RazorpayGatewayError, match="credentials not configured"):
        await tool.execute(case, plan)


@pytest.mark.anyio
async def test_razorpay_payment_link_live_http_contract_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify live gateway call contract: Basic Auth, minor paise amount, expire_by, reference_id."""
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_key123")
    monkeypatch.setattr(settings, "razorpay_key_secret", "secret_pass_456")

    recorded_requests: list[httpx2.Request] = []

    def mock_handler(request: httpx2.Request) -> httpx2.Response:
        recorded_requests.append(request)
        assert request.url == "https://api.razorpay.com/v1/payment_links"
        assert request.headers.get("Authorization") is not None
        body = json.loads(request.content.decode("utf-8"))
        assert body["amount"] == 95000
        assert body["currency"] == "INR"
        assert body["reference_id"] == "idem_live_pl_1"
        assert "expire_by" in body
        return httpx2.Response(
            status_code=200,
            json={
                "id": "plink_live_rzp_99",
                "short_url": "https://rzp.io/i/live_99",
                "status": "created",
            },
        )

    transport = httpx2.MockTransport(mock_handler)
    async with httpx2.AsyncClient(transport=transport) as mock_client:
        tool = RazorpayPaymentLinkTool(client=mock_client)
        case = _create_test_case(amount_paise=100000)
        plan = InterventionPlan(
            plan_id="plan_live",
            case_id=case.case_id,
            intervention_type=InterventionType.INCENTIVIZED_LINK,
            discount_bps=500,
            discount_paise=5000,
            scheduled_at=datetime.now(UTC),
            idempotency_key="idem_live_pl_1",
            rationale="Live gateway link test",
        )

        result = await tool.execute(case, plan)
        assert result.success is True
        assert result.action_taken == "PAYMENT_LINK_CREATED"
        assert result.external_id == "plink_live_rzp_99"
        assert result.data["short_url"] == "https://rzp.io/i/live_99"
        assert result.data["live_gateway_call"] is True
        assert len(recorded_requests) == 1


@pytest.mark.anyio
async def test_razorpay_payment_link_gateway_error_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that when gateway returns an error, the tool fails loudly without fabricating success."""
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_key123")
    monkeypatch.setattr(settings, "razorpay_key_secret", "secret_pass_456")

    def mock_handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status_code=400,
            json={
                "error": {
                    "code": "BAD_REQUEST_ERROR",
                    "description": "Invalid customer phone",
                }
            },
        )

    transport = httpx2.MockTransport(mock_handler)
    async with httpx2.AsyncClient(transport=transport) as mock_client:
        tool = RazorpayPaymentLinkTool(client=mock_client)
        case = _create_test_case(amount_paise=100000)
        plan = InterventionPlan(
            plan_id="plan_err",
            case_id=case.case_id,
            intervention_type=InterventionType.INCENTIVIZED_LINK,
            scheduled_at=datetime.now(UTC),
            idempotency_key="idem_err_1",
            rationale="Gateway error test",
        )

        with pytest.raises(RazorpayGatewayError, match="BAD_REQUEST_ERROR"):
            await tool.execute(case, plan)


@pytest.mark.anyio
async def test_mandate_retry_live_http_contract_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify Subscriptions Charge API contract: Basic Auth, subscription endpoint, paise body."""
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_sub_key")
    monkeypatch.setattr(settings, "razorpay_key_secret", "sub_secret_456")

    recorded_requests: list[httpx2.Request] = []

    def mock_handler(request: httpx2.Request) -> httpx2.Response:
        recorded_requests.append(request)
        assert "/v1/subscriptions/sub_test_mandate_99/charge" in str(request.url)
        assert request.headers.get("Authorization") is not None
        body = json.loads(request.content.decode("utf-8"))
        assert body["amount"] == 500000
        assert body["currency"] == "INR"
        return httpx2.Response(
            status_code=200,
            json={"id": "chg_sub_live_123", "status": "charged"},
        )

    transport = httpx2.MockTransport(mock_handler)
    async with httpx2.AsyncClient(transport=transport) as mock_client:
        tool = MandateRetryTool(client=mock_client)
        case = _create_test_case(amount_paise=500000)
        plan = InterventionPlan(
            plan_id="plan_mr_live",
            case_id=case.case_id,
            intervention_type=InterventionType.SMART_RETRY,
            scheduled_at=datetime.now(UTC),
            idempotency_key="idem_mr_live",
            rationale="Live subscription charge test",
        )

        result = await tool.execute(case, plan)
        assert result.success is True
        assert result.action_taken == "MANDATE_RETRY_SCHEDULED"
        assert result.external_id == "chg_sub_live_123"
        assert result.cost_incurred_paise == 250
        assert result.data["live_gateway_call"] is True
        assert len(recorded_requests) == 1


@pytest.mark.anyio
async def test_mandate_retry_no_credentials_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without Razorpay credentials, the tool must fail cleanly, never fabricate a charge."""

    async def _no_auth() -> None:
        return None

    monkeypatch.setattr(
        "app.intervention.tools.mandate_retry.resolve_razorpay_auth", _no_auth
    )

    tool = MandateRetryTool()
    case = _create_test_case(amount_paise=500000)
    plan = InterventionPlan(
        plan_id="plan_mr_nocreds",
        case_id=case.case_id,
        intervention_type=InterventionType.SMART_RETRY,
        scheduled_at=datetime.now(UTC),
        idempotency_key="idem_mr_nocreds",
        rationale="Missing credentials test",
    )

    with pytest.raises(RazorpayGatewayError, match="credentials not configured"):
        await tool.execute(case, plan)


@pytest.mark.anyio
async def test_mandate_retry_gateway_error_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify mandate retry fails honestly when Subscriptions API rejects."""
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_sub_key")
    monkeypatch.setattr(settings, "razorpay_key_secret", "sub_secret_456")

    def mock_handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status_code=400,
            json={
                "error": {
                    "code": "BAD_REQUEST_ERROR",
                    "description": "Mandate already expired",
                }
            },
        )

    transport = httpx2.MockTransport(mock_handler)
    async with httpx2.AsyncClient(transport=transport) as mock_client:
        tool = MandateRetryTool(client=mock_client)
        case = _create_test_case(amount_paise=500000)
        plan = InterventionPlan(
            plan_id="plan_mr_err",
            case_id=case.case_id,
            intervention_type=InterventionType.SMART_RETRY,
            scheduled_at=datetime.now(UTC),
            idempotency_key="idem_mr_err",
            rationale="Mandate error test",
        )

        with pytest.raises(RazorpayGatewayError, match="BAD_REQUEST_ERROR"):
            await tool.execute(case, plan)


@pytest.mark.anyio
async def test_customer_notification_live_provider_contract_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify live messaging provider dispatch contract with RBI notice and Bearer token."""
    settings = get_settings()
    monkeypatch.setattr(
        settings,
        "notification_webhook_url",
        "https://api.whatsapp.provider.com/v1/messages",
    )
    monkeypatch.setattr(settings, "whatsapp_api_token", "test_wa_token_789")

    recorded_requests: list[httpx2.Request] = []

    def mock_handler(request: httpx2.Request) -> httpx2.Response:
        recorded_requests.append(request)
        assert str(request.url) == "https://api.whatsapp.provider.com/v1/messages"
        assert request.headers.get("Authorization") == "Bearer test_wa_token_789"
        body = json.loads(request.content.decode("utf-8"))
        assert body["customer_id"] == "cust_tool_test"
        assert "Reply STOP to opt out" in body["message_text"]
        return httpx2.Response(status_code=200, json={"id": "wam_live_disp_456"})

    transport = httpx2.MockTransport(mock_handler)
    async with httpx2.AsyncClient(transport=transport) as mock_client:
        tool = CustomerNotificationTool(client=mock_client)
        case = _create_test_case(amount_paise=150000)
        plan = InterventionPlan(
            plan_id="plan_wa_live",
            case_id=case.case_id,
            intervention_type=InterventionType.CUSTOMER_NUDGE,
            channel=OutreachChannel.WHATSAPP,
            scheduled_at=datetime.now(UTC),
            idempotency_key="idem_wa_live",
            rationale="Live WhatsApp notice",
        )

        result = await tool.execute(case, plan)
        assert result.success is True
        assert result.action_taken == "NOTIFICATION_DISPATCHED"
        assert result.external_id == "wam_live_disp_456"
        assert result.cost_incurred_paise == 50
        assert result.data["live_dispatch_call"] is True
        assert len(recorded_requests) == 1


@pytest.mark.anyio
async def test_notification_quotes_only_a_real_issued_payment_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dunning text must carry the link the payment-link tool issued."""
    settings = get_settings()
    monkeypatch.setattr(
        settings,
        "notification_webhook_url",
        "https://api.whatsapp.provider.com/v1/messages",
    )

    issued_url = "https://rzp.io/i/realLink42"
    bodies: list[dict[str, Any]] = []

    def mock_handler(request: httpx2.Request) -> httpx2.Response:
        bodies.append(json.loads(request.content.decode("utf-8")))
        return httpx2.Response(status_code=200, json={"id": "wam_link_1"})

    transport = httpx2.MockTransport(mock_handler)
    async with httpx2.AsyncClient(transport=transport) as mock_client:
        tool = CustomerNotificationTool(client=mock_client)
        case = _create_test_case(amount_paise=150000)
        case.payment_link_id = "plink_live_abc123"
        case.payment_link_url = issued_url
        plan = InterventionPlan(
            plan_id="plan_wa_link",
            case_id=case.case_id,
            intervention_type=InterventionType.CUSTOMER_NUDGE,
            channel=OutreachChannel.WHATSAPP,
            scheduled_at=datetime.now(UTC),
            idempotency_key="idem_wa_link",
            rationale="Nudge with issued link",
        )

        result = await tool.execute(case, plan)

    assert result.success is True
    assert issued_url in bodies[0]["message_text"]


@pytest.mark.anyio
async def test_notification_omits_link_when_none_was_issued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no issued link, the message must not invent a URL from the case id."""
    settings = get_settings()
    monkeypatch.setattr(
        settings,
        "notification_webhook_url",
        "https://api.whatsapp.provider.com/v1/messages",
    )

    bodies: list[dict[str, Any]] = []

    def mock_handler(request: httpx2.Request) -> httpx2.Response:
        bodies.append(json.loads(request.content.decode("utf-8")))
        return httpx2.Response(status_code=200, json={"id": "wam_nolink_1"})

    transport = httpx2.MockTransport(mock_handler)
    async with httpx2.AsyncClient(transport=transport) as mock_client:
        tool = CustomerNotificationTool(client=mock_client)
        case = _create_test_case(amount_paise=150000)
        assert case.payment_link_url is None
        plan = InterventionPlan(
            plan_id="plan_wa_nolink",
            case_id=case.case_id,
            intervention_type=InterventionType.CUSTOMER_NUDGE,
            channel=OutreachChannel.WHATSAPP,
            scheduled_at=datetime.now(UTC),
            idempotency_key="idem_wa_nolink",
            rationale="Nudge without a link",
        )

        result = await tool.execute(case, plan)

    assert result.success is True
    message_text = bodies[0]["message_text"]
    assert "rzp.io" not in message_text
    assert case.case_id[:8] not in message_text
    assert "Reply STOP to opt out" in message_text


@pytest.mark.anyio
async def test_customer_notification_provider_error_returns_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify notification dispatch fails honestly when provider returns error."""
    settings = get_settings()
    monkeypatch.setattr(
        settings,
        "notification_webhook_url",
        "https://api.whatsapp.provider.com/v1/messages",
    )

    def mock_handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status_code=500,
            json={"error": "Provider message queue down"},
        )

    transport = httpx2.MockTransport(mock_handler)
    async with httpx2.AsyncClient(transport=transport) as mock_client:
        tool = CustomerNotificationTool(client=mock_client)
        case = _create_test_case(amount_paise=150000)
        plan = InterventionPlan(
            plan_id="plan_wa_fail",
            case_id=case.case_id,
            intervention_type=InterventionType.CUSTOMER_NUDGE,
            channel=OutreachChannel.WHATSAPP,
            scheduled_at=datetime.now(UTC),
            idempotency_key="idem_wa_fail",
            rationale="Live provider failure test",
        )

        result = await tool.execute(case, plan)
        assert result.success is False
        assert result.action_taken == "NOTIFICATION_GATEWAY_ERROR"


@pytest.mark.anyio
async def test_customer_notification_tool_whatsapp_and_sms_sandbox() -> None:
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
        rationale="SMS recovery nudge",
    )
    sms_result = await tool.execute(case, sms_plan)
    assert sms_result.success is True
    assert sms_result.cost_incurred_paise == 20  # INR 0.20
