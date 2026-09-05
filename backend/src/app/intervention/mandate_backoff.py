"""Escalating retry-spacing calculation for UPI Autopay / eNACH mandate retries."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.enums import InterventionType, PaymentRail

if TYPE_CHECKING:
    from app.intervention.models import MerchantPolicy

MANDATE_RETRY_INTERVENTION_TYPES = frozenset(
    {InterventionType.PASSIVE_RETRY, InterventionType.SMART_RETRY}
)


def is_mandate_retry(intervention_type: InterventionType) -> bool:
    """True if this intervention type is a mandate/subscription auto-debit retry."""
    return intervention_type in MANDATE_RETRY_INTERVENTION_TYPES


def mandate_backoff_schedule_for_rail(
    policy: MerchantPolicy, rail: PaymentRail
) -> list[int]:
    """eNACH clears through bank batch cycles, so it gets its own schedule."""
    if rail == PaymentRail.ENACH:
        return policy.enach_retry_backoff_hours
    return policy.mandate_retry_backoff_hours


def compute_mandate_backoff_hours(
    policy: MerchantPolicy, rail: PaymentRail, attempt_number: int
) -> int:
    """Hours to wait before a mandate retry at attempt_number (1-indexed).

    Past the schedule's length, the last entry repeats rather than zero wait.
    """
    schedule = mandate_backoff_schedule_for_rail(policy, rail)
    index = min(max(attempt_number, 1) - 1, len(schedule) - 1)
    return schedule[index]
