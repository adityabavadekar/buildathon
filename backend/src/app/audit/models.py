"""Domain models for immutable audit trails and stateful recovery cases."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.core.constants import DEFAULT_CURRENCY
from app.core.enums import AuditActor, ExperimentArm, RecoveryState
from app.core.money import calculate_net_recovered_value_paise
from app.detection.models import RawFailureEvent


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
    cost_incurred_paise: int = 0
    model_metadata: dict[str, Any] | None = None
    notes: str | None = None


class RecoveryCase(BaseModel):
    """Active or terminal state machine entity representing an at-risk revenue item."""

    case_id: str = Field(default_factory=lambda: str(uuid4()))
    merchant_id: str = "default_merchant"
    state: RecoveryState = RecoveryState.ANALYSIS_QUEUED
    experiment_arm: ExperimentArm = ExperimentArm.TREATMENT
    amount_paise: int = Field(gt=0)
    currency: str = Field(default=DEFAULT_CURRENCY)
    failure_event: RawFailureEvent

    touches_count: int = 0
    retry_count: int = 0
    outreach_count: int = 0
    discount_paise_granted: int = 0

    last_touch_at: datetime | None = None
    total_cost_paise: int = 0
    recovered_amount_paise: int = 0
    net_recovered_value_paise: int = 0

    is_opted_out: bool = False
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
