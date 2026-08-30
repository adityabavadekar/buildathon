"""Durable workflow models, templates, signals, and state transitions for FORTX."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.core.enums import RecoveryState


class WorkflowTemplate(StrEnum):
    """Built-in durable workflow lifecycle templates."""

    FAILED_PAYMENT = "FAILED_PAYMENT"
    SUBSCRIPTION_FAILURE = "SUBSCRIPTION_FAILURE"
    OVERDUE_INVOICE = "OVERDUE_INVOICE"
    ABANDONED_PAYMENT = "ABANDONED_PAYMENT"
    PAYMENT_DEGRADATION = "PAYMENT_DEGRADATION"


class WorkflowStage(StrEnum):
    """Resumable stages in a FORTX recovery workflow state machine."""

    TRIGGERED = "TRIGGERED"
    CONTEXT_HYDRATED = "CONTEXT_HYDRATED"
    DIAGNOSING = "DIAGNOSING"
    POLICY_EVALUATING = "POLICY_EVALUATING"
    ACTION_EXECUTING = "ACTION_EXECUTING"
    WAITING_SIGNAL_OR_TIMER = "WAITING_SIGNAL_OR_TIMER"
    EVALUATING_OUTCOME = "EVALUATING_OUTCOME"
    REPLANNING = "REPLANNING"
    HUMAN_ESCALATED = "HUMAN_ESCALATED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WorkflowSignalType(StrEnum):
    """External events that immediately wake or alter a running workflow."""

    PAYMENT_CAPTURED = "PAYMENT_CAPTURED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    INVOICE_PAID = "INVOICE_PAID"
    CUSTOMER_RESPONSE = "CUSTOMER_RESPONSE"
    RAIL_DEGRADED = "RAIL_DEGRADED"
    PROMISED_PAYMENT = "PROMISED_PAYMENT"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    TIMER_EXPIRED = "TIMER_EXPIRED"


class WorkflowSignal(BaseModel):
    """Durable payload representing an external event signal delivered to a workflow."""

    signal_id: str = Field(default_factory=lambda: str(uuid4()))
    signal_type: WorkflowSignalType
    payload: dict[str, Any] = Field(default_factory=dict)
    source: str = "system"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WorkflowHistoryEvent(BaseModel):
    """Persisted event record in a workflow execution history for replay and debugging."""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    from_stage: WorkflowStage | None = None
    to_stage: WorkflowStage
    event_name: str
    details: dict[str, Any] = Field(default_factory=dict)


class WorkflowTimer(BaseModel):
    """Durable timer waiting for a specific timestamp or duration."""

    timer_id: str = Field(default_factory=lambda: str(uuid4()))
    timer_type: str
    fire_at: datetime
    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowStoppingRules(BaseModel):
    """Deterministic bounds and stopping limits for workflow execution."""

    max_retries: int = 4
    max_touches: int = 5
    max_duration_hours: int = 168  # 7 days
    max_discount_bps: int = 1000  # 10%
    stop_on_recovered: bool = True
    stop_on_human_pause: bool = True


class WorkflowInstance(BaseModel):
    """Complete persisted state for a durable, resumable recovery case workflow."""

    workflow_id: str = Field(default_factory=lambda: str(uuid4()))
    case_id: str
    template: WorkflowTemplate
    current_stage: WorkflowStage = WorkflowStage.TRIGGERED
    recovery_state: RecoveryState = RecoveryState.ANALYSIS_QUEUED
    context: dict[str, Any] = Field(default_factory=dict)
    stopping_rules: WorkflowStoppingRules = Field(default_factory=WorkflowStoppingRules)
    timers: list[WorkflowTimer] = Field(default_factory=list)
    signals_received: list[WorkflowSignal] = Field(default_factory=list)
    history: list[WorkflowHistoryEvent] = Field(default_factory=list)
    attempts_count: int = 0
    touches_count: int = 0
    is_terminal: bool = False
    terminal_outcome: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
