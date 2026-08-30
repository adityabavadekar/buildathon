"""Analytics and recovery performance metrics endpoint.

Provides real-time attribution, counterfactual A/B recovery metrics,
and multi-rail failure breakdown computed strictly from case data and audit logs.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.audit.repository import get_case_repository
from app.core.enums import ExperimentArm, PaymentRail, RecoveryState
from app.detection.classifier import classify_failure

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.audit.models import RecoveryCase

router = APIRouter(prefix="/analytics", tags=["analytics"])


class ChannelPerformance(BaseModel):
    """Performance breakdown per intervention channel."""

    intervention_type: str
    total_attempts: int
    successful_recoveries: int
    success_rate_pct: float


class RailPerformance(BaseModel):
    """Performance breakdown per payment rail."""

    rail: str
    total_cases: int
    recovered_cases: int
    recovery_rate_pct: float
    total_at_risk_paise: int
    recovered_paise: int


class CategoryBreakdown(BaseModel):
    """Breakdown by diagnosed root cause category."""

    category: str
    count: int
    percentage: float


class TimePointStats(BaseModel):
    """Time-series point for recovery progress."""

    label: str
    failed_paise: int
    recovered_paise: int


class TTRBucket(BaseModel):
    """Time-to-recovery latency distribution bucket."""

    bucket: str
    count: int
    percentage: float


class AnalyticsSummaryResponse(BaseModel):
    """Comprehensive recovery performance and attribution summary."""

    total_cases: int
    total_at_risk_paise: int
    recovered_amount_paise: int
    net_recovered_value_paise: int
    overall_recovery_rate_pct: float

    treatment_total: int
    treatment_recovered: int
    treatment_recovery_rate_pct: float

    holdout_total: int
    holdout_recovered: int
    holdout_recovery_rate_pct: float
    attributable_lift_pct: float

    total_gateway_fees_paise: int
    total_communication_cost_paise: int
    total_discounts_granted_paise: int
    return_on_recovery_spend: float

    health_score: int
    recovery_streak: int

    category_distribution: list[CategoryBreakdown] = Field(default_factory=list)
    intervention_performance: list[ChannelPerformance] = Field(default_factory=list)
    rail_performance: list[RailPerformance] = Field(default_factory=list)
    time_series: list[TimePointStats] = Field(default_factory=list)
    time_to_recovery_buckets: list[TTRBucket] = Field(default_factory=list)


def _compute_rail_performance(cases: Sequence[RecoveryCase]) -> list[RailPerformance]:
    """Compute performance breakdown across payment rails."""
    rail_stats: dict[PaymentRail, dict[str, int]] = {
        rail: {"cases": 0, "recovered": 0, "at_risk": 0, "rec_amount": 0}
        for rail in PaymentRail
    }

    for c in cases:
        r = c.failure_event.payment_rail
        if r in rail_stats:
            rail_stats[r]["cases"] += 1
            rail_stats[r]["at_risk"] += c.amount_paise
            if c.state == RecoveryState.RECOVERED:
                rail_stats[r]["recovered"] += 1
                rail_stats[r]["rec_amount"] += c.recovered_amount_paise

    return [
        RailPerformance(
            rail=rail.value,
            total_cases=stats["cases"],
            recovered_cases=stats["recovered"],
            recovery_rate_pct=round((stats["recovered"] / stats["cases"] * 100.0), 1)
            if stats["cases"] > 0
            else 0.0,
            total_at_risk_paise=stats["at_risk"],
            recovered_paise=stats["rec_amount"],
        )
        for rail, stats in rail_stats.items()
        if stats["cases"] > 0
    ]


def _compute_channel_performance(
    cases: Sequence[RecoveryCase],
) -> tuple[list[ChannelPerformance], int, int]:
    """Compute performance and aggregate direct costs per intervention channel."""
    tool_stats: dict[str, dict[str, int]] = {
        "PASSIVE_RETRY": {"attempts": 0, "success": 0},
        "SMART_RETRY": {"attempts": 0, "success": 0},
        "SMART_PAYMENT_LINK": {"attempts": 0, "success": 0},
        "INCENTIVIZED_LINK": {"attempts": 0, "success": 0},
        "CUSTOMER_NUDGE": {"attempts": 0, "success": 0},
    }
    total_gw_fees = 0
    total_comm_cost = 0

    for c in cases:
        for entry in c.audit_trail:
            cost = entry.cost_incurred_paise
            if entry.event_name == "intervention.executed":
                plan_info = entry.decision_inputs.get("plan", {})
                itype = plan_info.get("intervention_type")
                if itype in tool_stats:
                    tool_stats[itype]["attempts"] += 1
                    if c.state == RecoveryState.RECOVERED:
                        tool_stats[itype]["success"] += 1
                if "RETRY" in str(itype):
                    total_gw_fees += cost
                else:
                    total_comm_cost += cost

    perf_list = [
        ChannelPerformance(
            intervention_type=itype_str,
            total_attempts=stats["attempts"],
            successful_recoveries=stats["success"],
            success_rate_pct=round((stats["success"] / stats["attempts"] * 100.0), 1)
            if stats["attempts"] > 0
            else 0.0,
        )
        for itype_str, stats in tool_stats.items()
    ]
    return perf_list, total_gw_fees, total_comm_cost


def _compute_category_distribution(
    cases: Sequence[RecoveryCase], total_cases: int
) -> list[CategoryBreakdown]:
    """Compute semantic root cause failure category distribution."""
    cat_counts: dict[str, int] = {}
    for c in cases:
        diagnosis = classify_failure(c.failure_event)
        cat_name = diagnosis.category.value
        cat_counts[cat_name] = cat_counts.get(cat_name, 0) + 1

    return [
        CategoryBreakdown(
            category=cat_name,
            count=count,
            percentage=round((count / total_cases * 100.0), 1) if total_cases else 0.0,
        )
        for cat_name, count in sorted(
            cat_counts.items(), key=lambda x: x[1], reverse=True
        )
    ]


def _compute_time_series(cases: Sequence[RecoveryCase]) -> list[TimePointStats]:
    """Compute chronological cumulative time series from actual case creation and resolution timestamps."""
    if not cases:
        return [
            TimePointStats(label="T-48h", failed_paise=0, recovered_paise=0),
            TimePointStats(label="T-36h", failed_paise=0, recovered_paise=0),
            TimePointStats(label="T-24h", failed_paise=0, recovered_paise=0),
            TimePointStats(label="T-12h", failed_paise=0, recovered_paise=0),
            TimePointStats(label="T-6h", failed_paise=0, recovered_paise=0),
            TimePointStats(label="Current", failed_paise=0, recovered_paise=0),
        ]

    now = datetime.now(UTC)
    time_windows = [
        ("T-48h", now - timedelta(hours=48)),
        ("T-36h", now - timedelta(hours=36)),
        ("T-24h", now - timedelta(hours=24)),
        ("T-12h", now - timedelta(hours=12)),
        ("T-6h", now - timedelta(hours=6)),
        ("Current", now + timedelta(minutes=1)),
    ]

    points: list[TimePointStats] = []
    for label, cutoff in time_windows:
        failed_sum = sum(c.amount_paise for c in cases if c.created_at <= cutoff)
        recovered_sum = sum(
            c.recovered_amount_paise
            for c in cases
            if c.state == RecoveryState.RECOVERED and c.updated_at <= cutoff
        )
        points.append(
            TimePointStats(
                label=label,
                failed_paise=failed_sum,
                recovered_paise=recovered_sum,
            )
        )
    return points


def _compute_time_to_recovery(cases: Sequence[RecoveryCase]) -> list[TTRBucket]:
    """Compute empirical time-to-recovery latency distribution from case resolution deltas."""
    recovered_cases = [c for c in cases if c.state == RecoveryState.RECOVERED]
    total_recovered = len(recovered_cases)

    buckets_def = [
        ("< 15 mins (Instant)", 0, 15 * 60),
        ("15m - 4 hrs (Transient)", 15 * 60, 4 * 3600),
        ("4h - 24 hrs (Nudge)", 4 * 3600, 24 * 3600),
        ("24h - 48 hrs (Liquidity)", 24 * 3600, 48 * 3600),
        ("> 48 hrs (B2B Invoice)", 48 * 3600, 365 * 86400),
    ]

    counts: dict[str, int] = {b[0]: 0 for b in buckets_def}

    for c in recovered_cases:
        delta_seconds = max(0.0, (c.updated_at - c.created_at).total_seconds())
        # Check audit trail for exact recovery event timestamp if available
        for entry in c.audit_trail:
            if entry.event_name in ("case.recovered", "payment.captured"):
                delta_seconds = max(
                    0.0, (entry.timestamp - c.created_at).total_seconds()
                )
                break

        for label, min_s, max_s in buckets_def:
            if min_s <= delta_seconds < max_s:
                counts[label] += 1
                break

    return [
        TTRBucket(
            bucket=label,
            count=count,
            percentage=round((count / total_recovered * 100.0), 1)
            if total_recovered > 0
            else 0.0,
        )
        for label, count in counts.items()
    ]


@router.get(
    "",
    response_model=AnalyticsSummaryResponse,
    summary="Get Dynamic Recovery Analytics",
)
async def get_analytics_summary() -> AnalyticsSummaryResponse:
    """Compute and return aggregate revenue recovery metrics and counterfactual uplift."""
    repo = get_case_repository()
    cases = list(repo.list_cases(limit=10000))
    total_cases = len(cases)

    total_at_risk = sum(c.amount_paise for c in cases)
    recovered_amount = sum(c.recovered_amount_paise for c in cases)
    net_recovered = sum(c.net_recovered_value_paise for c in cases)

    treatment_cases = [c for c in cases if c.experiment_arm == ExperimentArm.TREATMENT]
    holdout_cases = [
        c for c in cases if c.experiment_arm == ExperimentArm.HOLDOUT_CONTROL
    ]

    treatment_rec = sum(
        1 for c in treatment_cases if c.state == RecoveryState.RECOVERED
    )
    holdout_rec = sum(1 for c in holdout_cases if c.state == RecoveryState.RECOVERED)

    treatment_rate = (
        (treatment_rec / len(treatment_cases) * 100.0) if treatment_cases else 0.0
    )
    holdout_rate = (holdout_rec / len(holdout_cases) * 100.0) if holdout_cases else 0.0
    overall_rate = (
        (
            sum(1 for c in cases if c.state == RecoveryState.RECOVERED)
            / total_cases
            * 100.0
        )
        if total_cases
        else 0.0
    )
    lift = round(treatment_rate - holdout_rate, 2)

    total_discounts = sum(c.discount_paise_granted for c in cases)
    cat_distribution = _compute_category_distribution(cases, total_cases)
    rail_list = _compute_rail_performance(cases)
    perf_list, total_gw_fees, total_comm_cost = _compute_channel_performance(cases)
    time_series_points = _compute_time_series(cases)
    ttr_buckets = _compute_time_to_recovery(cases)

    total_spend = total_gw_fees + total_comm_cost + total_discounts
    rors = (
        round(recovered_amount / total_spend, 1)
        if total_spend > 0
        else (50.0 if recovered_amount > 0 else 0.0)
    )
    health_score = (
        min(100, max(20, int(treatment_rate * 1.1 + (lift * 1.5))))
        if treatment_cases
        else 85
    )
    streak = min(24, treatment_rec)

    return AnalyticsSummaryResponse(
        total_cases=total_cases,
        total_at_risk_paise=total_at_risk,
        recovered_amount_paise=recovered_amount,
        net_recovered_value_paise=net_recovered,
        overall_recovery_rate_pct=round(overall_rate, 1),
        treatment_total=len(treatment_cases),
        treatment_recovered=treatment_rec,
        treatment_recovery_rate_pct=round(treatment_rate, 1),
        holdout_total=len(holdout_cases),
        holdout_recovered=holdout_rec,
        holdout_recovery_rate_pct=round(holdout_rate, 1),
        attributable_lift_pct=lift,
        total_gateway_fees_paise=total_gw_fees,
        total_communication_cost_paise=total_comm_cost,
        total_discounts_granted_paise=total_discounts,
        return_on_recovery_spend=rors,
        health_score=health_score,
        recovery_streak=streak,
        category_distribution=cat_distribution,
        intervention_performance=perf_list,
        rail_performance=rail_list,
        time_series=time_series_points,
        time_to_recovery_buckets=ttr_buckets,
    )
