"""Domain models for immutable audit trails, stateful recovery cases, scheduled jobs, and model telemetry."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.core.constants import DEFAULT_CURRENCY
from app.core.enums import (
    AuditActor,
    EscalationReason,
    ExperimentArm,
    FailureCategory,
    JobStatus,
    RecoveryState,
)
from app.core.money import calculate_net_recovered_value_paise
from app.detection.models import RawFailureEvent  # noqa: TC001


class AuditEntry(BaseModel):
    """Immutable record of an event, decision trace, or state transition."""

    entry_id: str = Field(default_factory=lambda: str(uuid4()))
    case_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_name: str
    actor: AuditActor
    from_state: RecoveryState | None = None
    to_state: RecoveryState | None = None
    decision_inputs: dict[str, Any] = Field(default_factory=dict)
    decision_outputs: dict[str, Any] = Field(default_factory=dict)
    cost_incurred_paise: int = Field(default=0, ge=0)
    model_metadata: dict[str, Any] | None = None
    notes: str | None = None


class ScheduledJob(BaseModel):
    """A durable scheduled task to be executed at due_at by the recovery worker."""

    job_id: str = Field(default_factory=lambda: str(uuid4()))
    case_id: str
    job_type: str
    due_at: datetime
    status: JobStatus = JobStatus.QUEUED
    idempotency_key: str
    attempts: int = Field(default=0, ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ModelTelemetryEntry(BaseModel):
    """Recorded model invocation telemetry for cost accounting and latency reporting."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    model: str
    provider: str
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0)
    latency_ms: float = Field(default=0.0, ge=0)
    success: bool = True
    used_fallback: bool = False
    version: str | None = None
    fallback_reason: str | None = None
    experiment_tag: str | None = None
    config_snapshot: dict[str, Any] | None = None
    case_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RecoveryCase(BaseModel):
    """Active or terminal state machine entity representing an at-risk revenue item."""

    case_id: str = Field(default_factory=lambda: str(uuid4()))
    merchant_id: str = "default_merchant"
    state: RecoveryState = RecoveryState.ANALYSIS_QUEUED
    experiment_arm: ExperimentArm = ExperimentArm.TREATMENT
    diagnosed_category: FailureCategory = FailureCategory.UNCLASSIFIED
    amount_paise: int = Field(gt=0)
    currency: str = Field(
        default=DEFAULT_CURRENCY, pattern=r"^[A-Z]{3}$", description="ISO 4217 code"
    )
    failure_event: RawFailureEvent
    campaign_id: str | None = None
    user_ref: str | None = None
    reference_id: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None

    attempts_count: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    outreach_count: int = Field(default=0, ge=0)
    discount_paise_granted: int = Field(default=0, ge=0)

    last_attempt_at: datetime | None = None
    total_cost_paise: int = Field(default=0, ge=0)
    recovered_amount_paise: int = Field(default=0, ge=0)
    # Can legitimately go negative: retry/outreach cost can exceed recovery.
    net_recovered_value_paise: int = 0

    is_opted_out: bool = False
    due_at: datetime | None = None
    next_action: str | None = None
    # Set only when state == ESCALATED, by transition_case's invariant that
    # forbids escalating without one. Says WHY the case is paused; state says
    # only THAT it is. Never infer this from audit_trail content or ordering.
    escalation_reason: EscalationReason | None = None
    version: int = Field(default=1, ge=1)

    # Set when a P2P_FOLLOWUP intervention is executed: the date by which the
    # customer committed to pay, used to schedule the P2P_FOLLOWUP_CHECK job.
    promised_payment_date: datetime | None = None
    p2p_reminder_count: int = Field(default=0, ge=0)

    # Smart Collect & Payment Link Lifecycle Extensions
    virtual_account_id: str | None = None
    bank_transfer_id: str | None = None
    collected_amount_paise: int | None = Field(default=None, ge=0)
    collection_mode: str | None = None
    collected_at: datetime | None = None
    payment_link_id: str | None = None
    payment_link_url: str | None = None
    payment_link_expires_at: datetime | None = None
    strategy_tag: str | None = None
    dunning_message_en: str | None = None
    dunning_message_hi: str | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    audit_trail: list[AuditEntry] = Field(default_factory=list)

    def recompute_nrv(self) -> None:
        """Recompute the Net Recovered Value based on current costs, retries, and recovered amount."""
        self.net_recovered_value_paise = calculate_net_recovered_value_paise(
            recovered_amount_paise=self.recovered_amount_paise,
            retry_count=self.retry_count,
            outreach_count=self.outreach_count,
            discount_paise=self.discount_paise_granted,
        )
        self.total_cost_paise = self.retry_count * 250 + self.outreach_count * 50
