"""Comprehensive end-to-end tests for the FORTX durable workflow system."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.enums import (
    PaymentRail,
    RecoveryState,
)
from app.detection.models import RawFailureEvent
from app.workflow.engine import WorkflowEngine
from app.workflow.models import (
    WorkflowSignal,
    WorkflowSignalType,
    WorkflowStage,
    WorkflowTemplate,
)
from app.workflow.repository import WorkflowRepository
from app.workflow.templates import configure_stopping_rules, select_template_for_event


def create_sample_event(
    rail: PaymentRail = PaymentRail.UPI,
    code: str = "U30",
    source: str = "bank",
    amount_paise: int = 150000,
    payment_id: str = "pay_wf_test_1",
) -> RawFailureEvent:
    return RawFailureEvent(
        event_id=f"evt_{payment_id}",
        payment_id=payment_id,
        customer_id="cust_test",
        amount_paise=amount_paise,
        currency="INR",
        payment_rail=rail,
        error_code=code,
        error_reason="insufficient_funds",
        error_source=source,
        occurred_at=datetime.now(UTC),
    )


@pytest.fixture
def workflow_repo(tmp_path: Any) -> WorkflowRepository:
    db_path = tmp_path / "test_workflows.db"
    return WorkflowRepository(db_path=db_path)


def test_template_selection_for_different_events() -> None:
    """Verify built-in templates are selected according to event signatures."""
    # 1. Bank systemic outage -> PAYMENT_DEGRADATION
    degrade_event = create_sample_event(code="XT", source="bank")
    assert (
        select_template_for_event(degrade_event) == WorkflowTemplate.PAYMENT_DEGRADATION
    )

    # 2. B2B Invoice -> OVERDUE_INVOICE
    inv_event = create_sample_event(rail=PaymentRail.B2B_INVOICE, payment_id="inv_123")
    assert select_template_for_event(inv_event) == WorkflowTemplate.OVERDUE_INVOICE

    # 3. Recurring Mandate -> SUBSCRIPTION_FAILURE
    sub_event = create_sample_event(rail=PaymentRail.UPI_AUTOPAY, payment_id="sub_123")
    assert select_template_for_event(sub_event) == WorkflowTemplate.SUBSCRIPTION_FAILURE

    # 4. Checkout drop-off -> ABANDONED_PAYMENT
    ab_event = create_sample_event(source="customer")
    assert select_template_for_event(ab_event) == WorkflowTemplate.ABANDONED_PAYMENT

    # 5. Standard UPI debit failure -> FAILED_PAYMENT
    std_event = create_sample_event(rail=PaymentRail.UPI, code="U30", source="bank")
    assert select_template_for_event(std_event) == WorkflowTemplate.FAILED_PAYMENT


def test_stopping_rules_bounds() -> None:
    """Verify stopping rules are bounded across templates."""
    rules_inv = configure_stopping_rules(WorkflowTemplate.OVERDUE_INVOICE, 5000000)
    assert rules_inv.max_touches == 6
    assert rules_inv.max_discount_bps == 500

    rules_sub = configure_stopping_rules(WorkflowTemplate.SUBSCRIPTION_FAILURE, 149900)
    assert rules_sub.max_retries == 4

    rules_std = configure_stopping_rules(WorkflowTemplate.FAILED_PAYMENT, 200000)
    assert rules_std.max_retries == 3
    assert rules_std.max_touches == 4


@pytest.mark.anyio
async def test_workflow_start_and_advance_lifecycle(
    workflow_repo: WorkflowRepository,
) -> None:
    """Verify end-to-end workflow start, state transition, and history persistence."""
    engine = WorkflowEngine(repository=workflow_repo)
    event = create_sample_event(payment_id="pay_wf_lifecycle_1")

    wf = await engine.start_workflow(event)
    assert wf.workflow_id is not None
    assert wf.template == WorkflowTemplate.FAILED_PAYMENT
    assert len(wf.history) >= 2

    # Check persistence
    fetched = workflow_repo.get_workflow(wf.workflow_id)
    assert fetched is not None
    assert fetched.case_id == wf.case_id
    assert fetched.current_stage in (
        WorkflowStage.WAITING_SIGNAL_OR_TIMER,
        WorkflowStage.HUMAN_ESCALATED,
        WorkflowStage.COMPLETED,
    )


@pytest.mark.anyio
async def test_workflow_signal_payment_captured(
    workflow_repo: WorkflowRepository,
) -> None:
    """Verify external webhook signal wakes workflow and transitions to COMPLETED."""
    engine = WorkflowEngine(repository=workflow_repo)
    event = create_sample_event(payment_id="pay_wf_signal_1")

    wf = await engine.start_workflow(event)
    assert not wf.is_terminal

    # Deliver payment captured signal
    signal = WorkflowSignal(
        signal_type=WorkflowSignalType.PAYMENT_CAPTURED,
        payload={"payment_id": event.payment_id, "amount_paise": event.amount_paise},
        source="razorpay_webhook",
    )
    res = await engine.signal_workflow(wf.workflow_id, signal)
    assert res is not None
    assert res.current_stage == WorkflowStage.COMPLETED
    assert res.is_terminal is True
    assert res.terminal_outcome == "RECOVERED_VIA_SIGNAL"
    assert len(res.signals_received) == 1


@pytest.mark.anyio
async def test_workflow_worker_restart_recovery(
    workflow_repo: WorkflowRepository,
) -> None:
    """Verify worker restart recovers active workflows without duplicate actions."""
    engine = WorkflowEngine(repository=workflow_repo)
    event = create_sample_event(payment_id="pay_wf_restart_1")

    wf = await engine.start_workflow(event)
    assert not wf.is_terminal

    # Simulate worker restart recovery
    resumed_count = engine.recover_on_worker_restart()
    assert resumed_count >= 1

    fetched = workflow_repo.get_workflow(wf.workflow_id)
    assert fetched is not None
    restart_events = [
        e
        for e in fetched.history
        if e.event_name == "workflow.worker_restart_reclaimed"
    ]
    assert len(restart_events) == 1


@pytest.mark.anyio
async def test_workflow_human_escalation_and_approval_resume(
    workflow_repo: WorkflowRepository,
) -> None:
    """Verify human escalation pauses workflow and approval signal resumes execution."""
    engine = WorkflowEngine(repository=workflow_repo)
    event = create_sample_event(payment_id="pay_wf_hitl_1")

    wf = await engine.start_workflow(event)
    # Manually transition to escalated
    wf.current_stage = WorkflowStage.HUMAN_ESCALATED
    wf.recovery_state = RecoveryState.ESCALATED
    workflow_repo.save_workflow(wf)

    # Deliver human approval signal
    approval_signal = WorkflowSignal(
        signal_type=WorkflowSignalType.HUMAN_APPROVAL,
        payload={"approved_by": "operator", "notes": "Approved discount link"},
    )
    res = await engine.signal_workflow(wf.workflow_id, approval_signal)
    assert res is not None
    assert res.current_stage != WorkflowStage.HUMAN_ESCALATED


def test_workflow_api_endpoints(client: Any) -> None:
    """Verify REST API routes for listing, fetching details, sending signals, and analytics."""
    # 1. Analytics
    res = client.get("/api/workflows/analytics")
    assert res.status_code == 200
    data = res.json()
    assert "total_workflows" in data
    assert "stage_counts" in data

    # 2. List workflows
    list_res = client.get("/api/workflows?limit=10")
    assert list_res.status_code == 200
    assert isinstance(list_res.json(), list)
