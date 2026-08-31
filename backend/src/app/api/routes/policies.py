"""Merchant policies and recovery guardrail inspection API."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.intervention.models import MerchantPolicy
from app.intervention.policy_gate import get_active_policy, set_active_policy

router = APIRouter(prefix="/policies", tags=["policies"])



class PolicyRuleDetail(BaseModel):
    """Details of an active recovery invariant rule."""

    id: str
    name: str
    description: str
    value: str
    enforced: bool


class PolicyResponse(BaseModel):
    """Response containing active merchant policy parameters and rules."""

    merchant_id: str
    max_touches: int
    min_cooldown_hours: int
    max_discount_bps: int
    holdout_percentage: int
    require_human_above_paise: int
    allowed_channels: list[str]
    rules: list[PolicyRuleDetail]


@router.get("", response_model=PolicyResponse, summary="Get Active Policies")
async def get_active_policies() -> PolicyResponse:
    """Retrieve active recovery policy rules, limits, and guardrails."""
    _ACTIVE_POLICY = get_active_policy()
    rules = [
        PolicyRuleDetail(
            id="max_touches",
            name="Maximum Touch Limit",
            description="Strict limit on total intervention attempts (retries + messages) per failed transaction.",
            value=f"{_ACTIVE_POLICY.max_touches} touches max",
            enforced=True,
        ),
        PolicyRuleDetail(
            id="cooldown",
            name="Intervention Cooldown Window",
            description="Minimum quiet time between successive customer contacts to prevent dunning spam.",
            value=f"{_ACTIVE_POLICY.min_cooldown_hours} hours",
            enforced=True,
        ),
        PolicyRuleDetail(
            id="discount_cap",
            name="Incentive Discount Cap",
            description="Maximum permitted promotional concession for checkout drop-off recovery.",
            value=f"{_ACTIVE_POLICY.max_discount_bps / 100:.1f}% max ({_ACTIVE_POLICY.max_discount_bps} bps)",
            enforced=True,
        ),
        PolicyRuleDetail(
            id="holdout_arm",
            name="A/B Holdout Control Allocation",
            description="Deterministic holdout ratio preserved with zero outreach for unassisted recovery baseline measurement.",
            value=f"{_ACTIVE_POLICY.holdout_percentage}% of cohort",
            enforced=True,
        ),
        PolicyRuleDetail(
            id="high_value_threshold",
            name="High-Value Operator Approval Threshold",
            description="Mandatory human ops operator review for failed transactions exceeding limit.",
            value=f"INR {_ACTIVE_POLICY.require_human_above_paise / 100:,.2f}",
            enforced=True,
        ),
    ]

    return PolicyResponse(
        merchant_id=_ACTIVE_POLICY.merchant_id,
        max_touches=_ACTIVE_POLICY.max_touches,
        min_cooldown_hours=_ACTIVE_POLICY.min_cooldown_hours,
        max_discount_bps=_ACTIVE_POLICY.max_discount_bps,
        holdout_percentage=_ACTIVE_POLICY.holdout_percentage,
        require_human_above_paise=_ACTIVE_POLICY.require_human_above_paise,
        allowed_channels=[channel.value for channel in _ACTIVE_POLICY.allowed_channels],
        rules=rules,
    )


@router.put("", response_model=MerchantPolicy)
async def update_active_policies(policy: MerchantPolicy) -> MerchantPolicy:
    return set_active_policy(policy)
