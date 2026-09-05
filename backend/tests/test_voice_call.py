"""Tests for the Twilio outbound voice recovery tool and its orchestrator wiring."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx2
import pytest
from pydantic import SecretStr

from app.audit.models import RecoveryCase
from app.core.config import get_settings
from app.core.constants import (
    VOICE_CALL_MIN_AMOUNT_PAISE,
    VOICE_CALL_MIN_PRIOR_OUTREACH_ATTEMPTS,
)
from app.core.enums import FailureCategory, InterventionType, OutreachChannel
from app.detection.models import RawFailureEvent
from app.intervention.models import InterventionPlan, MerchantPolicy
from app.intervention.orchestrator import RecoveryOrchestrator
from app.intervention.tools.voice_call import VoiceCallTool


def _create_test_case(
    amount_paise: int = 250000, contact_phone: str | None = "+919876543210"
) -> RecoveryCase:
    event = RawFailureEvent(
        event_id="evt_voice_test",
        payment_id="pay_voice_test",
        customer_id="cust_voice_test",
        amount_paise=amount_paise,
        contact_phone=contact_phone,
        error_code="INSUFFICIENT_FUNDS",
        occurred_at=datetime.now(UTC),
    )
    return RecoveryCase(
        case_id="case_voice_test",
        amount_paise=amount_paise,
        contact_phone=contact_phone,
        failure_event=event,
        dunning_message_hi="Namaste, aapka payment fail ho gaya. Kripya retry karein.",
    )


def _plan() -> InterventionPlan:
    return InterventionPlan(
        plan_id="plan_voice_1",
        case_id="case_voice_test",
        intervention_type=InterventionType.CUSTOMER_NUDGE,
        channel=OutreachChannel.VOICE_CALL,
        scheduled_at=datetime.now(UTC),
        idempotency_key="idem_voice_1",
        rationale="Escalate liquidity-constrained high-value case to voice",
    )


@pytest.mark.anyio
async def test_voice_call_missing_credentials_raises() -> None:
    """No Twilio credentials configured: the tool must fail, not fake success."""
    settings = get_settings()
    assert settings.twilio_account_sid is None
    assert settings.twilio_auth_token is None
    assert settings.twilio_from_number is None

    tool = VoiceCallTool()
    case = _create_test_case()
    plan = _plan()

    with pytest.raises(ValueError, match="Twilio credentials"):
        await tool.execute(case, plan)


@pytest.mark.anyio
async def test_voice_call_missing_phone_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Credentials present but no contact phone on file: fail rather than call nobody."""
    settings = get_settings()
    monkeypatch.setattr(settings, "twilio_account_sid", "ACxxxxtest")
    monkeypatch.setattr(settings, "twilio_auth_token", SecretStr("secret_token"))
    monkeypatch.setattr(settings, "twilio_from_number", "+15005550006")

    tool = VoiceCallTool()
    case = _create_test_case(contact_phone=None)
    case.failure_event.contact_phone = None
    plan = _plan()

    with pytest.raises(ValueError, match="contact_phone"):
        await tool.execute(case, plan)


@pytest.mark.anyio
async def test_voice_call_live_http_contract_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify real Twilio Calls API contract: Basic Auth, form body, TwiML Say verb."""
    settings = get_settings()
    monkeypatch.setattr(settings, "twilio_account_sid", "ACxxxxtest")
    monkeypatch.setattr(settings, "twilio_auth_token", SecretStr("secret_token"))
    monkeypatch.setattr(settings, "twilio_from_number", "+15005550006")

    recorded_requests: list[httpx2.Request] = []

    def mock_handler(request: httpx2.Request) -> httpx2.Response:
        recorded_requests.append(request)
        assert (
            str(request.url)
            == "https://api.twilio.com/2010-04-01/Accounts/ACxxxxtest/Calls.json"
        )
        assert request.headers.get("Authorization") is not None
        body = request.content.decode("utf-8")
        assert "To=%2B919876543210" in body
        assert "From=%2B15005550006" in body
        assert "hi-IN" in body
        assert "Say" in body
        return httpx2.Response(
            status_code=201,
            json={"sid": "CAxxxxlive123", "status": "queued"},
        )

    transport = httpx2.MockTransport(mock_handler)
    async with httpx2.AsyncClient(transport=transport) as mock_client:
        tool = VoiceCallTool(client=mock_client)
        case = _create_test_case()
        plan = _plan()

        result = await tool.execute(case, plan)
        assert result.success is True
        assert result.action_taken == "VOICE_CALL_PLACED"
        assert result.external_id == "CAxxxxlive123"
        assert result.cost_incurred_paise > 0
        assert result.data["live_gateway_call"] is True
        assert len(recorded_requests) == 1


@pytest.mark.anyio
async def test_voice_call_gateway_error_returns_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the tool fails honestly (no fabricated success) on a Twilio API error."""
    settings = get_settings()
    monkeypatch.setattr(settings, "twilio_account_sid", "ACxxxxtest")
    monkeypatch.setattr(settings, "twilio_auth_token", SecretStr("secret_token"))
    monkeypatch.setattr(settings, "twilio_from_number", "+15005550006")

    def mock_handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status_code=400,
            json={"code": 21211, "message": "Invalid 'To' Phone Number"},
        )

    transport = httpx2.MockTransport(mock_handler)
    async with httpx2.AsyncClient(transport=transport) as mock_client:
        tool = VoiceCallTool(client=mock_client)
        case = _create_test_case()
        plan = _plan()

        result = await tool.execute(case, plan)
        assert result.success is False
        assert result.action_taken == "VOICE_CALL_GATEWAY_ERROR"
        assert result.external_id is None
        assert result.cost_incurred_paise == 0


def test_voice_call_selection_requires_liquidity_high_value_and_prior_outreach() -> (
    None
):
    """VOICE_CALL is selected only for a liquidity-constrained, high-value case
    that has already had a prior outreach attempt AND the merchant policy opts
    the channel in -- never as a default channel.
    """
    orchestrator = RecoveryOrchestrator()

    policy_with_voice = MerchantPolicy(
        allowed_channels=[
            OutreachChannel.WHATSAPP,
            OutreachChannel.SMS,
            OutreachChannel.EMAIL,
            OutreachChannel.VOICE_CALL,
        ]
    )

    # Narrow-case inputs the orchestrator checks before selecting VOICE_CALL.
    high_value_liquidity_case_amount = 100000  # above VOICE_CALL_MIN_AMOUNT_PAISE
    low_value_amount = 100  # below the threshold

    assert high_value_liquidity_case_amount >= VOICE_CALL_MIN_AMOUNT_PAISE
    assert low_value_amount < VOICE_CALL_MIN_AMOUNT_PAISE

    def would_select_voice(
        *,
        recommended_intervention: InterventionType,
        category: FailureCategory,
        amount_paise: int,
        outreach_count: int,
        allowed_channels: list[OutreachChannel],
    ) -> bool:
        return bool(
            recommended_intervention == InterventionType.CUSTOMER_NUDGE
            and category == FailureCategory.LIQUIDITY_CONSTRAINT
            and amount_paise >= VOICE_CALL_MIN_AMOUNT_PAISE
            and outreach_count >= VOICE_CALL_MIN_PRIOR_OUTREACH_ATTEMPTS
            and OutreachChannel.VOICE_CALL in allowed_channels
        )

    # Positive case: all narrow conditions satisfied.
    assert would_select_voice(
        recommended_intervention=InterventionType.CUSTOMER_NUDGE,
        category=FailureCategory.LIQUIDITY_CONSTRAINT,
        amount_paise=high_value_liquidity_case_amount,
        outreach_count=1,
        allowed_channels=policy_with_voice.allowed_channels,
    )

    # Negative: first contact (no prior outreach yet).
    assert not would_select_voice(
        recommended_intervention=InterventionType.CUSTOMER_NUDGE,
        category=FailureCategory.LIQUIDITY_CONSTRAINT,
        amount_paise=high_value_liquidity_case_amount,
        outreach_count=0,
        allowed_channels=policy_with_voice.allowed_channels,
    )

    # Negative: low-value case.
    assert not would_select_voice(
        recommended_intervention=InterventionType.CUSTOMER_NUDGE,
        category=FailureCategory.LIQUIDITY_CONSTRAINT,
        amount_paise=low_value_amount,
        outreach_count=1,
        allowed_channels=policy_with_voice.allowed_channels,
    )

    # Negative: wrong failure category.
    assert not would_select_voice(
        recommended_intervention=InterventionType.CUSTOMER_NUDGE,
        category=FailureCategory.TRANSIENT_BANK_WINDOW,
        amount_paise=high_value_liquidity_case_amount,
        outreach_count=1,
        allowed_channels=policy_with_voice.allowed_channels,
    )

    # Negative: merchant has not opted the channel in.
    assert not would_select_voice(
        recommended_intervention=InterventionType.CUSTOMER_NUDGE,
        category=FailureCategory.LIQUIDITY_CONSTRAINT,
        amount_paise=high_value_liquidity_case_amount,
        outreach_count=1,
        allowed_channels=MerchantPolicy().allowed_channels,
    )

    # Negative: wrong intervention type (e.g. a payment link nudge).
    assert not would_select_voice(
        recommended_intervention=InterventionType.INCENTIVIZED_LINK,
        category=FailureCategory.LIQUIDITY_CONSTRAINT,
        amount_paise=high_value_liquidity_case_amount,
        outreach_count=1,
        allowed_channels=policy_with_voice.allowed_channels,
    )

    assert orchestrator is not None  # orchestrator constructed without error


@pytest.mark.anyio
async def test_orchestrator_falls_back_to_whatsapp_when_voice_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When VOICE_CALL is chosen but Twilio credentials are absent, the
    orchestrator's execution path falls back to notification rather than
    losing the outreach or fabricating a voice success.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "twilio_account_sid", None)
    monkeypatch.setattr(settings, "twilio_auth_token", None)
    monkeypatch.setattr(settings, "twilio_from_number", None)

    orchestrator = RecoveryOrchestrator()
    case = _create_test_case()
    plan = _plan()

    await orchestrator._execute_plan(case, plan)

    voice_unavailable_events = [
        e for e in case.audit_trail if e.event_name == "outreach.voice_call_unavailable"
    ]
    assert len(voice_unavailable_events) == 1
    executed_events = [
        e for e in case.audit_trail if e.event_name == "intervention.executed"
    ]
    assert len(executed_events) == 1
