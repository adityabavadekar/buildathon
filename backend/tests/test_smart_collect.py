"""Comprehensive tests for Razorpay Smart Collect virtual accounts and webhook reconciliation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx2
import pytest

from app.audit.models import RecoveryCase
from app.audit.repository import get_case_repository
from app.core.config import get_settings
from app.core.enums import ExperimentArm, InterventionType, PaymentRail, RecoveryState
from app.detection.models import RawFailureEvent
from app.intervention.models import InterventionPlan
from app.intervention.tools.base import RazorpayGatewayError
from app.intervention.tools.smart_collect import SmartCollectTool

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


@pytest.mark.anyio
async def test_smart_collect_no_credentials_raises_gateway_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without Razorpay credentials, the tool must fail cleanly, never fabricate an account."""

    async def _no_auth() -> None:
        return None

    monkeypatch.setattr(
        "app.intervention.tools.smart_collect.resolve_razorpay_auth", _no_auth
    )

    tool = SmartCollectTool()
    now = datetime.now(UTC)

    case = RecoveryCase(
        case_id="case_b2b_collect_1",
        merchant_id="merch_b2b",
        state=RecoveryState.ANALYSIS_QUEUED,
        experiment_arm=ExperimentArm.TREATMENT,
        amount_paise=5000000,  # INR 50,000
        currency="INR",
        failure_event=RawFailureEvent(
            event_id="evt_b2b_1",
            payment_id="inv_b2b_999",
            customer_id="cust_b2b_enterprise",
            amount_paise=5000000,
            currency="INR",
            payment_rail=PaymentRail.B2B_INVOICE,
            error_code="INVOICE_OVERDUE",
            occurred_at=now,
        ),
    )

    plan = InterventionPlan(
        plan_id="plan_sc_1",
        case_id=case.case_id,
        intervention_type=InterventionType.SMART_COLLECT,
        scheduled_at=now,
        idempotency_key="idem_sc_1",
        rationale="Issue dedicated virtual account for NEFT/RTGS settlement",
    )

    with pytest.raises(RazorpayGatewayError, match="credentials not configured"):
        await tool.create_virtual_account(case, plan, close_by_hours=72)


@pytest.mark.anyio
async def test_smart_collect_live_http_contract_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify live virtual account contract: Basic Auth, receivers, close_by, notes."""
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_sc_key")
    monkeypatch.setattr(settings, "razorpay_key_secret", "sc_secret_456")

    now = datetime.now(UTC)
    recorded_requests: list[httpx2.Request] = []

    def mock_handler(request: httpx2.Request) -> httpx2.Response:
        recorded_requests.append(request)
        assert request.headers.get("Authorization") is not None
        body = json.loads(request.content.decode("utf-8"))
        assert body["receivers"]["types"] == ["bank_account", "vpa"]
        assert body["notes"]["case_id"] == "case_b2b_collect_1"
        return httpx2.Response(
            status_code=200,
            json={
                "id": "va_live_rzp_99",
                "receivers": [
                    {
                        "entity": "bank_account",
                        "account_number": "2223330099880000",
                        "ifsc": "RZPB0000001",
                    },
                    {"entity": "vpa", "address": "case1@rzp"},
                ],
            },
        )

    transport = httpx2.MockTransport(mock_handler)
    async with httpx2.AsyncClient(transport=transport) as mock_client:
        tool = SmartCollectTool(client=mock_client)
        case = RecoveryCase(
            case_id="case_b2b_collect_1",
            merchant_id="merch_b2b",
            state=RecoveryState.ANALYSIS_QUEUED,
            experiment_arm=ExperimentArm.TREATMENT,
            amount_paise=5000000,
            currency="INR",
            failure_event=RawFailureEvent(
                event_id="evt_b2b_1",
                payment_id="inv_b2b_999",
                customer_id="cust_b2b_enterprise",
                amount_paise=5000000,
                currency="INR",
                payment_rail=PaymentRail.B2B_INVOICE,
                error_code="INVOICE_OVERDUE",
                occurred_at=now,
            ),
        )
        plan = InterventionPlan(
            plan_id="plan_sc_1",
            case_id=case.case_id,
            intervention_type=InterventionType.SMART_COLLECT,
            scheduled_at=now,
            idempotency_key="idem_sc_1",
            rationale="Issue dedicated virtual account for NEFT/RTGS settlement",
        )

        res = await tool.create_virtual_account(case, plan, close_by_hours=72)
        assert res.virtual_account_id == "va_live_rzp_99"
        assert res.account_number == "2223330099880000"
        assert res.ifsc == "RZPB0000001"
        assert res.vpa == "case1@rzp"
        assert len(recorded_requests) == 1


@pytest.mark.anyio
async def test_smart_collect_gateway_error_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-2xx virtual account response must raise, not fabricate a fallback account."""
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_sc_key")
    monkeypatch.setattr(settings, "razorpay_key_secret", "sc_secret_456")

    def mock_handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status_code=400,
            json={"error": {"code": "BAD_REQUEST_ERROR", "description": "Bad"}},
        )

    transport = httpx2.MockTransport(mock_handler)
    async with httpx2.AsyncClient(transport=transport) as mock_client:
        tool = SmartCollectTool(client=mock_client)
        now = datetime.now(UTC)
        case = RecoveryCase(
            case_id="case_b2b_collect_err",
            merchant_id="merch_b2b",
            state=RecoveryState.ANALYSIS_QUEUED,
            experiment_arm=ExperimentArm.TREATMENT,
            amount_paise=5000000,
            currency="INR",
            failure_event=RawFailureEvent(
                event_id="evt_b2b_err",
                payment_id="inv_b2b_err",
                customer_id="cust_b2b_err",
                amount_paise=5000000,
                currency="INR",
                payment_rail=PaymentRail.B2B_INVOICE,
                error_code="INVOICE_OVERDUE",
                occurred_at=now,
            ),
        )
        plan = InterventionPlan(
            plan_id="plan_sc_err",
            case_id=case.case_id,
            intervention_type=InterventionType.SMART_COLLECT,
            scheduled_at=now,
            idempotency_key="idem_sc_err",
            rationale="Gateway error test",
        )

        with pytest.raises(RazorpayGatewayError, match="BAD_REQUEST_ERROR"):
            await tool.create_virtual_account(case, plan)


@pytest.mark.anyio
async def test_smart_collect_tool_execute_sets_case_virtual_account_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """execute() must set case.virtual_account_id so the virtual_account.credited
    webhook handler (which matches on that field) has something to reconcile.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_sc_key2")
    monkeypatch.setattr(settings, "razorpay_key_secret", "sc_secret_789")

    now = datetime.now(UTC)

    def mock_handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status_code=200,
            json={
                "id": "va_live_exec_1",
                "receivers": [
                    {
                        "entity": "bank_account",
                        "account_number": "2223330011112222",
                        "ifsc": "RZPB0000002",
                    },
                    {"entity": "vpa", "address": "case2@rzp"},
                ],
            },
        )

    transport = httpx2.MockTransport(mock_handler)
    async with httpx2.AsyncClient(transport=transport) as mock_client:
        tool = SmartCollectTool(client=mock_client)

        case = RecoveryCase(
            case_id="case_b2b_collect_2",
            merchant_id="merch_b2b",
            state=RecoveryState.ANALYSIS_QUEUED,
            experiment_arm=ExperimentArm.TREATMENT,
            amount_paise=750000,
            currency="INR",
            failure_event=RawFailureEvent(
                event_id="evt_b2b_2",
                payment_id="inv_b2b_1000",
                customer_id="cust_b2b_enterprise_2",
                amount_paise=750000,
                currency="INR",
                payment_rail=PaymentRail.B2B_INVOICE,
                error_code="INVOICE_OVERDUE",
                occurred_at=now,
            ),
        )

        plan = InterventionPlan(
            plan_id="plan_sc_2",
            case_id=case.case_id,
            intervention_type=InterventionType.B2B_INVOICE_CHASER,
            scheduled_at=now,
            idempotency_key="idem_sc_2",
            rationale="Issue dedicated virtual account for NEFT/RTGS settlement",
        )

        result = await tool.execute(case, plan)
        assert result.success is True
        assert result.action_taken == "VIRTUAL_ACCOUNT_CREATED"
        assert case.virtual_account_id is not None
        assert case.virtual_account_id == result.external_id

        # Retrying the same plan against an already-issued case must not open a
        # second virtual account.
        second = await tool.execute(case, plan)
        assert second.success is True
        assert second.action_taken == "VIRTUAL_ACCOUNT_ALREADY_ISSUED"
        assert second.external_id == case.virtual_account_id


def test_smart_collect_webhook_reconciliation(client: TestClient) -> None:
    """Verify virtual_account.credited webhook reconciles case to RECOVERED with mode and amount."""
    repo = get_case_repository()
    now = datetime.now(UTC)
    case_id = "case_sc_rec_1"
    va_id = "va_test_987654"

    case = RecoveryCase(
        case_id=case_id,
        merchant_id="merch_b2b",
        state=RecoveryState.P2P_WAITING,
        experiment_arm=ExperimentArm.TREATMENT,
        amount_paise=2500000,  # INR 25,000
        currency="INR",
        virtual_account_id=va_id,
        failure_event=RawFailureEvent(
            event_id="evt_sc_1",
            payment_id="pay_sc_1",
            customer_id="cust_b2b_1",
            amount_paise=2500000,
            currency="INR",
            payment_rail=PaymentRail.B2B_INVOICE,
            error_code="OVERDUE",
            occurred_at=now,
        ),
    )
    repo.save(case)

    credited_payload = {
        "event": "virtual_account.credited",
        "payload": {
            "virtual_account": {
                "entity": {
                    "id": va_id,
                    "notes": {"case_id": case_id},
                }
            },
            "payment": {
                "entity": {
                    "id": "pay_neft_bank_123",
                    "amount": 2500000,
                    "method": "NEFT",
                    "virtual_account_id": va_id,
                    "notes": {"case_id": case_id},
                }
            },
        },
    }

    # 1. Ingest credit webhook
    res = client.post("/api/webhooks/razorpay", json=credited_payload)
    assert res.status_code == 200
    assert res.json()["status"] == "processed"
    assert res.json()["action_taken"] == "RECOVERED"

    # 2. Check case updated
    updated = repo.get_by_id(case_id)
    assert updated is not None
    assert updated.state == RecoveryState.RECOVERED
    assert updated.collected_amount_paise == 2500000
    assert updated.collection_mode == "NEFT"
    assert updated.bank_transfer_id == "pay_neft_bank_123"

    # 3. Duplicate delivery is idempotent
    res2 = client.post("/api/webhooks/razorpay", json=credited_payload)
    assert res2.status_code == 200
    assert res2.json()["action_taken"] == "RECOVERED"
