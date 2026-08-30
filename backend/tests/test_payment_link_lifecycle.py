"""Comprehensive tests for payment link managed lifecycle and webhook reconciliation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from app.audit.models import RecoveryCase
from app.audit.repository import get_case_repository
from app.core.enums import ExperimentArm, InterventionType, PaymentRail, RecoveryState
from app.detection.models import RawFailureEvent
from app.intervention.models import InterventionPlan
from app.intervention.tools.payment_link import RazorpayPaymentLinkTool

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


@pytest.mark.anyio
async def test_payment_link_persisted_on_case() -> None:
    """Verify tool execution sets payment_link_id, payment_link_url, and payment_link_expires_at on case."""
    tool = RazorpayPaymentLinkTool()
    now = datetime.now(UTC)

    case = RecoveryCase(
        case_id="case_plink_1",
        merchant_id="merch_1",
        state=RecoveryState.OUTREACH_PENDING,
        experiment_arm=ExperimentArm.TREATMENT,
        amount_paise=150000,
        currency="INR",
        failure_event=RawFailureEvent(
            event_id="evt_plink_1",
            payment_id="pay_plink_1",
            customer_id="cust_1",
            amount_paise=150000,
            currency="INR",
            payment_rail=PaymentRail.CARD,
            error_code="GATEWAY_ERROR",
            occurred_at=now,
        ),
    )

    plan = InterventionPlan(
        plan_id="plan_plink_1",
        case_id=case.case_id,
        intervention_type=InterventionType.SMART_PAYMENT_LINK,
        scheduled_at=now,
        idempotency_key="idem_plink_1",
        rationale="Issue fallback recovery payment link",
    )

    result = await tool.execute(case, plan)
    assert result.success is True
    assert case.payment_link_id is not None
    assert case.payment_link_url is not None
    assert case.payment_link_expires_at is not None


def test_payment_link_webhooks_paid_and_partial(client: TestClient) -> None:
    """Verify webhook processing for link paid and partially paid events."""
    repo = get_case_repository()
    now = datetime.now(UTC)
    case_id = "case_plink_rec_1"
    link_id = "plink_test_123456"

    case = RecoveryCase(
        case_id=case_id,
        merchant_id="merch_1",
        state=RecoveryState.OUTREACH_PENDING,
        experiment_arm=ExperimentArm.TREATMENT,
        amount_paise=200000,
        currency="INR",
        payment_link_id=link_id,
        failure_event=RawFailureEvent(
            event_id="evt_plink_rec_1",
            payment_id="pay_plink_rec_1",
            customer_id="cust_plink_1",
            amount_paise=200000,
            currency="INR",
            payment_rail=PaymentRail.CARD,
            error_code="AUTH_FAIL",
            occurred_at=now,
        ),
    )
    repo.save(case)

    # 1. Partial payment webhook
    partial_payload = {
        "event": "payment_link.partially_paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": link_id,
                    "amount_paid": 50000,
                    "notes": {"case_id": case_id},
                }
            }
        },
    }
    part_res = client.post("/api/webhooks/razorpay", json=partial_payload)
    assert part_res.status_code == 200
    assert part_res.json()["action_taken"] == "PARTIAL_PAYMENT_RECORDED"

    updated = repo.get_by_id(case_id)
    assert updated is not None
    assert updated.recovered_amount_paise == 50000
    assert updated.state == RecoveryState.OUTREACH_PENDING

    # 2. Full payment webhook
    paid_payload = {
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": link_id,
                    "amount_paid": 200000,
                    "notes": {"case_id": case_id},
                }
            }
        },
    }
    paid_res = client.post("/api/webhooks/razorpay", json=paid_payload)
    assert paid_res.status_code == 200
    assert paid_res.json()["action_taken"] == "RECOVERED"

    final = repo.get_by_id(case_id)
    assert final is not None
    assert final.state == RecoveryState.RECOVERED
    assert final.recovered_amount_paise == 200000
