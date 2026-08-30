"""Domain models for intervention planning and policy evaluation."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import (
    DEFAULT_HOLDOUT_PERCENTAGE,
    DEFAULT_MAX_DISCOUNT_BPS,
    DEFAULT_MAX_DUNNING_TOUCHES,
    DEFAULT_MIN_COOLDOWN_HOURS,
)
from app.core.enums import InterventionType, OutreachChannel, PolicyCheckResult


class MerchantPolicy(BaseModel):
    """Configurable safety invariants and guardrails for a merchant."""

    merchant_id: str = "default_merchant"
    max_touches: int = Field(default=DEFAULT_MAX_DUNNING_TOUCHES, ge=1, le=10)
    min_cooldown_hours: int = Field(default=DEFAULT_MIN_COOLDOWN_HOURS, ge=0)
    max_discount_bps: int = Field(default=DEFAULT_MAX_DISCOUNT_BPS, ge=0, le=5000)
    holdout_percentage: int = Field(default=DEFAULT_HOLDOUT_PERCENTAGE, ge=0, le=50)
    allowed_channels: list[OutreachChannel] = Field(
        default_factory=lambda: [
            OutreachChannel.WHATSAPP,
            OutreachChannel.SMS,
            OutreachChannel.EMAIL,
        ]
    )
    require_human_above_paise: int = Field(
        default=10_000_000,
        description="INR 1,00,000 threshold for mandatory operator review",
    )


class InterventionPlan(BaseModel):
    """Proposed intervention ready for policy evaluation and scheduled execution."""

    plan_id: str
    case_id: str
    intervention_type: InterventionType
    channel: OutreachChannel | None = None
    scheduled_at: datetime
    discount_bps: int = Field(default=0, ge=0, le=10000)
    discount_paise: int = Field(default=0, ge=0)
    idempotency_key: str
    rationale: str


class PolicyEvaluation(BaseModel):
    """Result of deterministic policy guardrail evaluation."""

    result: PolicyCheckResult
    is_allowed: bool
    reason: str
    evaluated_at: datetime
    modified_plan: InterventionPlan | None = None
