"""Durable workflow models, templates, signals, and state transitions for FORTX."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.enums import RecoveryState


class WorkflowTemplate(StrEnum):
    """Built-in durable workflow lifecycle templates."""

    FAILED_PAYMENT = "FAILED_PAYMENT"
    SUBSCRIPTION_FAILURE = "SUBSCRIPTION_FAILURE"
    OVERDUE_INVOICE = "OVERDUE_INVOICE"
    ABANDONED_PAYMENT = "ABANDONED_PAYMENT"
    PAYMENT_DEGRADATION = "PAYMENT_DEGRADATION"


class WorkflowTriggerType(StrEnum):
    PAYMENT_FAILED = "payment.failed"
    SUBSCRIPTION_HALTED = "subscription.halted"
    INVOICE_OVERDUE = "invoice.overdue"
    CHECKOUT_ABANDONED = "checkout.abandoned"
    RAIL_DEGRADED = "rail.degraded"


class WorkflowAction(StrEnum):
    DIAGNOSE = "diagnose"
    RETRY = "retry"
    NOTIFY = "notify"
    PAYMENT_LINK = "payment_link"
    ESCALATE = "escalate"


class WorkflowNodeType(StrEnum):
    TRIGGER = "trigger"
    DECISION = "decision"
    ACTION = "action"
    WAIT = "wait"
    HUMAN_HANDOFF = "human_handoff"
    TERMINAL = "terminal"


class WorkflowTemplateStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


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


class WorkflowTemplateDefinition(BaseModel):
    """Merchant-authored workflow configuration anchored to a safe built-in lifecycle."""

    template_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    status: WorkflowTemplateStatus = WorkflowTemplateStatus.DRAFT
    base_template: WorkflowTemplate = WorkflowTemplate.FAILED_PAYMENT
    trigger_type: WorkflowTriggerType = WorkflowTriggerType.PAYMENT_FAILED
    allowed_actions: list[WorkflowAction] = Field(default_factory=list)
    graph_nodes: list[dict[str, Any]] = Field(default_factory=list)
    graph_edges: list[dict[str, Any]] = Field(default_factory=list)
    stopping_rules: WorkflowStoppingRules = Field(default_factory=WorkflowStoppingRules)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("allowed_actions")
    @classmethod
    def unique_actions(cls, value: list[WorkflowAction]) -> list[WorkflowAction]:
        if len(set(value)) != len(value):
            raise ValueError("allowed_actions must not contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_graph(self) -> WorkflowTemplateDefinition:
        if not self.graph_nodes and not self.graph_edges:
            return self
        node_ids: set[str] = set()
        trigger_count = 0
        terminal_count = 0
        for node in self.graph_nodes:
            node_id = node.get("id")
            node_type = node.get("type")
            if not isinstance(node_id, str) or not node_id or node_id in node_ids:
                raise ValueError("graph node ids must be unique and non-empty")
            node_ids.add(node_id)
            try:
                parsed_type = WorkflowNodeType(str(node_type))
            except ValueError as exc:
                raise ValueError(f"unknown graph node type: {node_type}") from exc
            trigger_count += parsed_type == WorkflowNodeType.TRIGGER
            terminal_count += parsed_type == WorkflowNodeType.TERMINAL
        if trigger_count != 1:
            raise ValueError("workflow graph must contain exactly one trigger node")
        if terminal_count < 1:
            raise ValueError("workflow graph must contain at least one terminal node")
        adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
        for edge in self.graph_edges:
            source, target = edge.get("source"), edge.get("target")
            if source not in node_ids or target not in node_ids:
                raise ValueError("graph edges must reference known nodes")
            adjacency[source].append(target)
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError("workflow graph must not contain cycles")
            if node_id in visited:
                return
            visiting.add(node_id)
            for child in adjacency[node_id]:
                visit(child)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in node_ids:
            visit(node_id)
        return self


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
