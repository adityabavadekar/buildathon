"""Deterministic action parameters (delay, discount, channel) per diagnosis
category and intervention type -- the single source both the rule-based
classifier and the LLM-derived path pull from, so they cannot silently diverge.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.constants import (
    SALARY_CYCLE_RETRY_SPACING_HOURS,
    TRANSIENT_BANK_WINDOW_DELAY_HOURS,
)
from app.core.enums import FailureCategory, InterventionType, OutreachChannel


@dataclass(frozen=True, slots=True)
class ActionParams:
    delay_hours: int
    discount_bps: int
    channel: OutreachChannel | None
    requires_human_approval: bool


# Keyed by (category, intervention_type): the pair, not category alone, since
# LIQUIDITY_CONSTRAINT legitimately resolves to either SMART_RETRY or
# MANUAL_ESCALATION depending on runtime customer history (see
# classifier.py's _liquidity_result) -- that branch decision stays in Python,
# this table only supplies the params once the pair is known.
_ACTION_PARAMS: dict[tuple[FailureCategory, InterventionType], ActionParams] = {
    (FailureCategory.B2B_RECEIVABLES_OVERDUE, InterventionType.B2B_INVOICE_CHASER): (
        ActionParams(24, 0, OutreachChannel.EMAIL, False)
    ),
    (FailureCategory.PROMISE_TO_PAY_DELAY, InterventionType.P2P_FOLLOWUP): (
        ActionParams(72, 0, OutreachChannel.WHATSAPP, False)
    ),
    (
        FailureCategory.INDETERMINATE_AUTHORIZATION,
        InterventionType.MANUAL_ESCALATION,
    ): ActionParams(0, 0, None, True),
    (FailureCategory.TRANSIENT_BANK_WINDOW, InterventionType.PASSIVE_RETRY): (
        ActionParams(TRANSIENT_BANK_WINDOW_DELAY_HOURS, 0, None, False)
    ),
    (
        FailureCategory.STRUCTURAL_MANDATE_FAILURE,
        InterventionType.SMART_PAYMENT_LINK,
    ): ActionParams(0, 0, None, False),
    (FailureCategory.LIQUIDITY_CONSTRAINT, InterventionType.SMART_RETRY): (
        ActionParams(
            SALARY_CYCLE_RETRY_SPACING_HOURS, 0, OutreachChannel.WHATSAPP, False
        )
    ),
    (FailureCategory.LIQUIDITY_CONSTRAINT, InterventionType.MANUAL_ESCALATION): (
        ActionParams(0, 0, None, True)
    ),
    (FailureCategory.CHECKOUT_DROP_OFF, InterventionType.INCENTIVIZED_LINK): (
        ActionParams(0, 500, OutreachChannel.WHATSAPP, False)
    ),
    (FailureCategory.SYSTEMIC_GATEWAY_FAILURE, InterventionType.PASSIVE_RETRY): (
        ActionParams(1, 0, None, False)
    ),
    (FailureCategory.UNCLASSIFIED, InterventionType.MANUAL_ESCALATION): (
        ActionParams(0, 0, None, True)
    ),
}


def get_action_params(
    category: FailureCategory, intervention_type: InterventionType
) -> ActionParams:
    """Static delay/discount/channel/approval for a known (category, intervention)
    pair. Raises for a pair with no static answer -- callers with a runtime
    decision (e.g. liquidity's customer-history branch) build their own
    ActionParams rather than calling this for that pair.
    """
    key = (category, intervention_type)
    if key not in _ACTION_PARAMS:
        msg = f"No static action params for ({category}, {intervention_type})"
        raise KeyError(msg)
    return _ACTION_PARAMS[key]


__all__ = [
    "ActionParams",
    "get_action_params",
]
