"""Tests for end-to-end recovery orchestration."""

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import httpx2
import pytest

from app.audit.repository import CaseRepository
from app.core.config import get_settings
from app.core.enums import EscalationReason, ExperimentArm, PaymentRail, RecoveryState
from app.detection.models import RawFailureEvent
from app.intervention.orchestrator import RecoveryOrchestrator
from app.intervention.tools.mandate_retry import MandateRetryTool
from app.intervention.tools.payment_link import RazorpayPaymentLinkTool
from app.intervention.tools.smart_collect import SmartCollectTool


def _mock_mandate_retry_tool(charge_id: str) -> MandateRetryTool:
    """A MandateRetryTool wired to a mock transport that always charges successfully."""

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status_code=200, json={"id": charge_id})

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    return MandateRetryTool(client=client)


def _mock_payment_link_tool(link_id: str, short_url: str) -> RazorpayPaymentLinkTool:
    """A RazorpayPaymentLinkTool wired to a mock transport that always succeeds."""

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status_code=200, json={"id": link_id, "short_url": short_url}
        )

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    return RazorpayPaymentLinkTool(client=client)


def _isolated_repo() -> CaseRepository:
    """A CaseRepository on a fresh temp DB: the shared default persists a fixed
    payment_id's terminal state, which breaks the assertion on re-run.
    """
    return CaseRepository(
        storage_path=Path(tempfile.mkdtemp(prefix="orch_test_")) / "test.db"
    )


@pytest.mark.anyio
async def test_orchestrator_transient_window_passive_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_orch_1")
    monkeypatch.setattr(settings, "razorpay_key_secret", "orch_1_secret")

    repo = _isolated_repo()
    orchestrator = RecoveryOrchestrator(
        repository=repo,
        mandate_retry_tool=_mock_mandate_retry_tool("chg_orch_1"),
    )

    event = RawFailureEvent(
        event_id="evt_orch_1",
        payment_id="pay_orch_1",
        customer_id="cust_orch_1",
        amount_paise=200000,
        payment_rail=PaymentRail.UPI_AUTOPAY,
        error_code="BAD_REQUEST_ERROR",
        error_reason="bank_cutoff_in_progress",
        npci_response_code="XT",
        occurred_at=datetime.now(UTC),
    )

    case = await orchestrator.process_failure_event(
        event, experiment_arm_override=ExperimentArm.TREATMENT
    )
    assert case.state == RecoveryState.RETRY_SCHEDULED
    assert case.retry_count == 1
    assert case.attempts_count == 1
    assert len(case.audit_trail) >= 2


@pytest.mark.anyio
async def test_orchestrator_checkout_dropoff_incentivized_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_orch_2")
    monkeypatch.setattr(settings, "razorpay_key_secret", "orch_2_secret")

    repo = _isolated_repo()
    orchestrator = RecoveryOrchestrator(
        repository=repo,
        payment_link_tool=_mock_payment_link_tool(
            "plink_orch_2", "https://rzp.io/i/orch2"
        ),
    )

    event = RawFailureEvent(
        event_id="evt_orch_2",
        payment_id="pay_orch_2",
        customer_id="cust_orch_2",
        amount_paise=100000,
        payment_rail=PaymentRail.UPI,
        error_code="BAD_REQUEST_ERROR",
        error_step="payment_authentication",
        error_reason="otp_timeout",
        occurred_at=datetime.now(UTC),
    )

    case = await orchestrator.process_failure_event(
        event, experiment_arm_override=ExperimentArm.TREATMENT
    )
    assert case.state == RecoveryState.OUTREACH_PENDING
    assert case.discount_paise_granted == 5000  # 5% discount (500 bps)
    assert case.attempts_count == 1


@pytest.mark.anyio
async def test_orchestrator_idempotency_returns_existing_case() -> None:
    repo = _isolated_repo()
    orchestrator = RecoveryOrchestrator(repository=repo)

    event = RawFailureEvent(
        event_id="evt_orch_3",
        payment_id="pay_orch_3",
        customer_id="cust_orch_3",
        amount_paise=100000,
        payment_rail=PaymentRail.CARD,
        error_code="BAD_REQUEST_ERROR",
        error_reason="insufficient_funds",
        occurred_at=datetime.now(UTC),
    )

    case1 = await orchestrator.process_failure_event(
        event, experiment_arm_override=ExperimentArm.TREATMENT
    )
    case2 = await orchestrator.process_failure_event(
        event, experiment_arm_override=ExperimentArm.TREATMENT
    )

    assert case1.case_id == case2.case_id


@pytest.mark.anyio
async def test_orchestrator_payment_captured_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_orch_4")
    monkeypatch.setattr(settings, "razorpay_key_secret", "orch_4_secret")

    repo = _isolated_repo()
    orchestrator = RecoveryOrchestrator(
        repository=repo,
        mandate_retry_tool=_mock_mandate_retry_tool("chg_orch_4"),
    )

    event = RawFailureEvent(
        event_id="evt_orch_4",
        payment_id="pay_orch_4",
        customer_id="cust_orch_4",
        amount_paise=500000,
        payment_rail=PaymentRail.UPI_AUTOPAY,
        error_code="BAD_REQUEST_ERROR",
        error_reason="bank_cutoff_in_progress",
        npci_response_code="XT",
        occurred_at=datetime.now(UTC),
    )

    case = await orchestrator.process_failure_event(
        event, experiment_arm_override=ExperimentArm.TREATMENT
    )
    assert case.state == RecoveryState.RETRY_SCHEDULED

    # Payment captured on recovery retry
    resolved = orchestrator.process_payment_captured("pay_orch_4", 500000)
    assert resolved is not None
    assert resolved.state == RecoveryState.RECOVERED
    assert (
        resolved.net_recovered_value_paise == 499750
    )  # 500000 - 250 (gateway retry cost)


@pytest.mark.anyio
async def test_orchestrator_unclassified_routes_to_escalated() -> None:
    repo = _isolated_repo()
    orchestrator = RecoveryOrchestrator(repository=repo)

    event = RawFailureEvent(
        event_id="evt_orch_esc_1",
        payment_id="pay_orch_esc_1",
        customer_id="cust_orch_esc_1",
        amount_paise=150000,
        payment_rail=PaymentRail.CARD,
        error_code="SUSPECTED_FRAUD_HOLD",
        error_reason="Risk engine flagged anomaly on card authorization",
        occurred_at=datetime.now(UTC),
    )

    case = await orchestrator.process_failure_event(
        event, experiment_arm_override=ExperimentArm.TREATMENT
    )
    assert case.state == RecoveryState.ESCALATED
    assert case.escalation_reason == EscalationReason.HUMAN_JUDGMENT
    assert case.attempts_count == 0  # Escalation does not increment customer attempts
    events = [e.event_name for e in case.audit_trail]
    assert "intervention.escalated" in events


@pytest.mark.anyio
async def test_orchestrator_high_value_routes_to_escalated() -> None:
    repo = _isolated_repo()
    orchestrator = RecoveryOrchestrator(repository=repo)

    # 15,000,000 paise = INR 1,50,000 (above default 10,000,000 paise threshold)
    event = RawFailureEvent(
        event_id="evt_orch_esc_2",
        payment_id="pay_orch_esc_2",
        customer_id="cust_orch_esc_2",
        amount_paise=15000000,
        payment_rail=PaymentRail.B2B_INVOICE,
        error_code="OVERDUE_RECEIVABLE",
        error_reason="Invoice overdue",
        occurred_at=datetime.now(UTC),
    )

    case = await orchestrator.process_failure_event(
        event, experiment_arm_override=ExperimentArm.TREATMENT
    )
    assert case.state == RecoveryState.ESCALATED
    assert case.escalation_reason == EscalationReason.HUMAN_JUDGMENT
    assert case.attempts_count == 0
    events = [e.event_name for e in case.audit_trail]
    assert "intervention.escalated" in events


@pytest.mark.anyio
async def test_orchestrator_p2p_followup_reaches_legal_state() -> None:
    """A P2P follow-up must not target a state unreachable from ANALYSIS_QUEUED:
    the notification had already gone out, so every retry re-messaged the customer.
    """
    repo = _isolated_repo()
    orchestrator = RecoveryOrchestrator(repository=repo)

    event = RawFailureEvent(
        event_id="evt_orch_p2p",
        payment_id="pay_orch_p2p",
        customer_id="cust_orch_p2p",
        amount_paise=400000,
        payment_rail=PaymentRail.UPI,
        error_code="P2P_PROMISED",
        error_reason="customer promised to pay after salary credit",
        occurred_at=datetime.now(UTC),
    )

    case = await orchestrator.process_failure_event(
        event, experiment_arm_override=ExperimentArm.TREATMENT
    )

    assert case.state != RecoveryState.ANALYSIS_QUEUED
    assert case.outreach_count == 1
    stored = repo.get_by_id(case.case_id)
    assert stored is not None
    assert stored.outreach_count == 1


@pytest.mark.anyio
async def test_orchestrator_b2b_invoice_chaser_routes_to_smart_collect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B2B_INVOICE_CHASER must dispatch to smart_collect_tool, not payment_link_tool,
    so the case ends up with a virtual_account_id for webhook reconciliation.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_orch_b2b_key")
    monkeypatch.setattr(settings, "razorpay_key_secret", "orch_b2b_secret")

    def mock_handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status_code=200,
            json={
                "id": "va_orch_b2b_1",
                "receivers": [
                    {
                        "entity": "bank_account",
                        "account_number": "2223330099990001",
                        "ifsc": "RZPB0000009",
                    },
                    {"entity": "vpa", "address": "orchb2b@rzp"},
                ],
            },
        )

    transport = httpx2.MockTransport(mock_handler)
    mock_client = httpx2.AsyncClient(transport=transport)

    repo = _isolated_repo()
    orchestrator = RecoveryOrchestrator(
        repository=repo, smart_collect_tool=SmartCollectTool(client=mock_client)
    )

    orchestrator.payment_link_tool.execute = AsyncMock(  # type: ignore[method-assign]
        wraps=orchestrator.payment_link_tool.execute
    )
    orchestrator.smart_collect_tool.execute = AsyncMock(  # type: ignore[method-assign]
        wraps=orchestrator.smart_collect_tool.execute
    )

    # Below the require_human_above_paise threshold so the plan reaches execution.
    event = RawFailureEvent(
        event_id="evt_orch_b2b_1",
        payment_id="pay_orch_b2b_1",
        customer_id="cust_orch_b2b_1",
        amount_paise=500000,
        payment_rail=PaymentRail.B2B_INVOICE,
        error_code="OVERDUE_RECEIVABLE",
        error_reason="invoice_past_due",
        occurred_at=datetime.now(UTC),
    )

    try:
        case = await orchestrator.process_failure_event(
            event, experiment_arm_override=ExperimentArm.TREATMENT
        )
    finally:
        await mock_client.aclose()

    assert case.state == RecoveryState.IN_DUNNING
    assert case.virtual_account_id == "va_orch_b2b_1"
    orchestrator.smart_collect_tool.execute.assert_awaited_once()
    orchestrator.payment_link_tool.execute.assert_not_awaited()


@pytest.mark.anyio
async def test_orchestrator_escalates_when_gateway_credentials_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tool that cannot reach Razorpay must escalate the case with an audited
    reason, never fabricate a successful virtual account.
    """

    async def _no_auth() -> None:
        return None

    monkeypatch.setattr(
        "app.intervention.tools.smart_collect.resolve_razorpay_auth", _no_auth
    )

    repo = _isolated_repo()
    orchestrator = RecoveryOrchestrator(repository=repo)

    event = RawFailureEvent(
        event_id="evt_orch_b2b_nocreds",
        payment_id="pay_orch_b2b_nocreds",
        customer_id="cust_orch_b2b_nocreds",
        amount_paise=500000,
        payment_rail=PaymentRail.B2B_INVOICE,
        error_code="OVERDUE_RECEIVABLE",
        error_reason="invoice_past_due",
        occurred_at=datetime.now(UTC),
    )

    case = await orchestrator.process_failure_event(
        event, experiment_arm_override=ExperimentArm.TREATMENT
    )

    assert case.state == RecoveryState.ESCALATED
    assert case.escalation_reason == EscalationReason.SYSTEM_ERROR
    assert case.virtual_account_id is None
    escalation_entries = [
        e for e in case.audit_trail if e.event_name == "intervention.execution_failed"
    ]
    assert len(escalation_entries) == 1
    assert escalation_entries[0].notes is not None
    assert "credentials not configured" in escalation_entries[0].notes


@pytest.mark.anyio
async def test_discount_uses_integer_paise_arithmetic() -> None:
    """Discount must be computed in integer paise, never via float division."""
    repo = _isolated_repo()
    orchestrator = RecoveryOrchestrator(repository=repo)

    # 500 bps of 100003 paise is 5000.15; integer arithmetic must floor to 5000.
    event = RawFailureEvent(
        event_id="evt_orch_disc",
        payment_id="pay_orch_disc",
        customer_id="cust_orch_disc",
        amount_paise=100003,
        payment_rail=PaymentRail.UPI,
        error_code="BAD_REQUEST_ERROR",
        error_step="payment_authentication",
        error_reason="otp_timeout",
        occurred_at=datetime.now(UTC),
    )

    case = await orchestrator.process_failure_event(
        event, experiment_arm_override=ExperimentArm.TREATMENT
    )
    assert case.discount_paise_granted == 5000
    assert isinstance(case.discount_paise_granted, int)
