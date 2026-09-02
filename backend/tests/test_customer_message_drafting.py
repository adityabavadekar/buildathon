"""Comprehensive tests for LLM customer message drafting, policy guardrails, and audit trail."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from app.audit.models import RecoveryCase
from app.audit.postgres_store import RelationalCaseStore
from app.audit.repository import CaseRepository
from app.core.enums import (
    ExperimentArm,
    FailureCategory,
    InterventionType,
    PaymentRail,
    PolicyCheckResult,
    RecoveryState,
)
from app.detection.classifier import FailureClassifier
from app.detection.models import RawFailureEvent
from app.intervention.models import InterventionPlan, MerchantPolicy
from app.intervention.orchestrator import RecoveryOrchestrator
from app.intervention.policy_gate import PolicyGate
from app.llm.planner import RecoveryPlanner


def make_test_event(
    rail: PaymentRail = PaymentRail.UPI,
    code: str = "U30",
    reason: str = "Bank technical error",
    amount_paise: int = 150000,
) -> RawFailureEvent:
    return RawFailureEvent(
        event_id=f"evt_{uuid4().hex[:8]}",
        payment_id=f"pay_{uuid4().hex[:8]}",
        customer_id="cust_test_msg",
        amount_paise=amount_paise,
        currency="INR",
        payment_rail=rail,
        error_code=code,
        error_description=reason,
        error_reason=reason,
        occurred_at=datetime.now(UTC),
    )


def test_classifier_drafts_multilingual_messages() -> None:
    """Verify deterministic fallback classifier creates contextual EN and HI dunning messages."""
    classifier = FailureClassifier()

    # 1. Checkout drop off
    event1 = make_test_event(
        code="BAD_REQUEST_ERROR", reason="otp_timeout", amount_paise=250000
    )
    res1 = classifier.classify(event1)
    assert res1.category == FailureCategory.CHECKOUT_DROP_OFF
    assert res1.dunning_message_en is not None
    assert "INR 2500" in res1.dunning_message_en
    assert res1.dunning_message_hi is not None
    assert "INR 2500" in res1.dunning_message_hi
    assert "dunning_message_en" in res1.signals_evaluated

    # 2. B2B Overdue
    event2 = make_test_event(
        rail=PaymentRail.B2B_INVOICE, reason="invoice_past_due", amount_paise=5000000
    )
    res2 = classifier.classify(event2)
    assert res2.category == FailureCategory.B2B_RECEIVABLES_OVERDUE
    assert res2.dunning_message_en is not None
    assert "INR 50000" in res2.dunning_message_en


@pytest.mark.anyio
async def test_planner_and_orchestrator_carries_drafted_messages(tmp_path: Any) -> None:
    """Verify orchestrator attaches drafted messages and emits agent.message_drafted audit entry."""
    db_path = tmp_path / "test_msg_audit.db"
    repo = CaseRepository(storage_path=db_path)
    planner = RecoveryPlanner()
    gate = PolicyGate()
    orchestrator = RecoveryOrchestrator(
        repository=repo, planner=planner, policy_gate=gate
    )

    event = make_test_event(reason="authentication_failed", amount_paise=300000)
    case = await orchestrator.process_failure_event(
        event, experiment_arm_override=ExperimentArm.TREATMENT
    )

    assert case.dunning_message_en is not None
    assert "3000" in case.dunning_message_en or "3,000" in case.dunning_message_en
    assert case.dunning_message_hi is not None

    # Verify agent.message_drafted is in audit trail
    draft_entry = next(
        (e for e in case.audit_trail if e.event_name == "agent.message_drafted"), None
    )
    assert draft_entry is not None
    assert (
        draft_entry.decision_outputs.get("dunning_message_en")
        == case.dunning_message_en
    )


def test_policy_gate_sanitizes_over_discounting_messages() -> None:
    """Verify PolicyGate catches and sanitizes messages claiming discounts above policy cap."""
    gate = PolicyGate()
    policy = MerchantPolicy(max_discount_bps=500)  # Max 5%
    case = RecoveryCase(
        merchant_id="test_merchant",
        state=RecoveryState.ANALYSIS_QUEUED,
        amount_paise=100000,
        currency="INR",
        failure_event=make_test_event(amount_paise=100000),
    )

    # Plan with hallucinated 50% discount in message text
    plan = InterventionPlan(
        plan_id="plan_test_overdiscount",
        case_id=case.case_id,
        intervention_type=InterventionType.INCENTIVIZED_LINK,
        scheduled_at=datetime.now(UTC),
        discount_bps=500,
        idempotency_key="idem_test_msg",
        rationale="Over-promising message test",
        dunning_message_en="Complete your payment now for an exclusive 50% discount!",
        dunning_message_hi="Abhi pay karein aur 50% discount payein!",
    )

    eval_res = gate.evaluate(case, plan, policy)
    assert eval_res.result == PolicyCheckResult.APPROVED
    assert eval_res.modified_plan is not None
    # Verify hallucinated 50% claim was sanitized out
    assert "50%" not in (eval_res.modified_plan.dunning_message_en or "")
    assert "50%" not in (eval_res.modified_plan.dunning_message_hi or "")


def test_postgres_persists_dunning_messages() -> None:
    """Verify dunning messages are persisted to and reloaded from PostgreSQL database."""
    store = RelationalCaseStore()

    case = RecoveryCase(
        case_id="case_msg_123",
        merchant_id="merchant_msg_test",
        state=RecoveryState.ANALYSIS_QUEUED,
        amount_paise=150000,
        currency="INR",
        failure_event=make_test_event(amount_paise=150000),
        dunning_message_en="Custom drafted English outreach message.",
        dunning_message_hi="Custom drafted Hindi outreach message.",
    )

    store.save_case(case)
    loaded = store.get_case("case_msg_123")
    assert loaded is not None
    assert loaded.dunning_message_en == "Custom drafted English outreach message."
    assert loaded.dunning_message_hi == "Custom drafted Hindi outreach message."
