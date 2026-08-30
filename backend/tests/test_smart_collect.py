"""Comprehensive tests for Razorpay Smart Collect virtual accounts and webhook reconciliation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from app.audit.models import RecoveryCase
from app.audit.repository import get_case_repository
from app.core.enums import ExperimentArm, InterventionType, PaymentRail, RecoveryState
from app.detection.models import RawFailureEvent
from app.intervention.models import InterventionPlan
from app.intervention.tools.smart_collect import SmartCollectTool

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


@pytest.mark.anyio
async def test_smart_collect_tool_virtual_account_creation() -> None:
    """Verify Smart Collect tool creates virtual account with receiver details in sandbox."""
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

    res = await tool.create_virtual_account(case, plan, close_by_hours=72)
    assert res.virtual_account_id is not None
    assert res.account_number is not None
    assert res.ifsc == "RAZR0000001"
    assert res.vpa is not None
    assert res.is_simulated is True


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
