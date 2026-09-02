"""Analytics and recovery performance metrics endpoint.

Provides real-time attribution, counterfactual A/B recovery metrics,
multi-rail failure breakdown, daily/monthly time series, and EV-prioritized operator escalation queue.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.audit.repository import get_case_repository
from app.core.enums import AuditActor, ExperimentArm, PaymentRail, RecoveryState
from app.detection.classifier import classify_failure
from app.detection.clustering import recompute_patterns
from app.detection.customer_profile import get_customer_profile_registry
from app.detection.ml import get_recovery_model, train_recovery_model
from app.detection.rail_health import get_rail_health_registry
from app.intervention.policy_gate import get_active_policy

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.audit.models import RecoveryCase

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/patterns")
async def get_patterns() -> list[dict[str, object]]:
    return get_case_repository().list_pattern_alerts()


@router.post("/patterns/recompute")
async def recompute_pattern_alerts() -> list[dict[str, object]]:
    return recompute_patterns()


@router.get("/recovery-model")
async def recovery_model_status() -> dict[str, object]:
    model = get_recovery_model()
    return {
        "status": "trained" if model.trained_count else "untrained",
        "version": model.version,
        "arch": "ensemble(logistic+naive-bayes) + intervention-scorer + recovery-time",
        "trained_count": model.trained_count,
        "cv_metrics": model.cv_metrics,
        "recovery_time_trained": model.recovery_time.trained,
        "expected_outputs": [
            "recovery_probability",
            "expected_recovery_value_paise",
            "expected_recovery_days",
            "intervention_scores",
        ],
        "holdout_metrics": model.holdout_metrics,
    }


@router.post("/recovery-model/train")
async def train_recovery_model_endpoint() -> dict[str, object]:
    model = train_recovery_model()
    return {
        "status": "trained",
        "version": model.version,
        "arch": "ensemble(logistic+naive-bayes) + intervention-scorer + recovery-time",
        "trained_count": model.trained_count,
        "cv_metrics": model.cv_metrics,
        "recovery_time_trained": model.recovery_time.trained,
        "expected_outputs": [
            "recovery_probability",
            "expected_recovery_value_paise",
            "expected_recovery_days",
            "intervention_scores",
        ],
        "holdout_metrics": model.holdout_metrics,
    }


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


class DailyMetricPoint(BaseModel):
    """Aggregated metrics per day for transaction volume, recovery, and escalations."""

    date: str
    total_transactions: int
    failed_count: int
    recovered_count: int
    escalated_count: int
    at_risk_paise: int
    recovered_paise: int
    net_recovered_value_paise: int
    recovery_rate_pct: float


class MonthlyMetricPoint(BaseModel):
    """Aggregated metrics per month for executive revenue tracking."""

    month: str
    total_transactions: int
    failed_count: int
    recovered_count: int
    escalated_count: int
    at_risk_paise: int
    recovered_paise: int
    net_recovered_value_paise: int
    recovery_rate_pct: float


class EscalationQueueItem(BaseModel):
    """Expected Recoverable Value (EV) prioritized operator escalation queue item."""

    case_id: str
    customer_id: str
    payment_id: str
    payment_rail: str
    amount_paise: int
    expected_recoverable_value_paise: int
    estimated_recovery_probability: float
    escalation_reason: str
    recommended_action: str
    recommended_discount_bps: int
    touches_count: int
    created_at: str
    state: str


class SegmentForecast(BaseModel):
    """Segment breakdown for expected recovery estimation."""

    segment: str
    expected_probability: float
    at_risk_paise: int
    expected_recoverable_paise: int


class RecoveryForecast(BaseModel):
    """Deterministic merchant recovery forecast funnel and remaining opportunity."""

    at_risk_paise: int
    expected_recoverable_paise: int
    recovered_paise: int
    remaining_opportunity_paise: int
    attributable_remaining_paise: int
    expected_recovery_rate_pct: float
    confidence_window_pct: float = 5.0
    segments: list[SegmentForecast] = Field(default_factory=list)


class CampaignMetrics(BaseModel):
    """Per-campaign recovery performance breakdown sourced from Razorpay notes."""

    campaign_id: str
    total_cases: int
    recovered_cases: int
    escalated_cases: int
    at_risk_paise: int
    recovered_paise: int
    net_recovered_value_paise: int
    recovery_rate_pct: float
    avg_amount_paise: int


class AnalyticsSummaryResponse(BaseModel):
    """Comprehensive recovery performance, queue sizes, and attribution summary."""

    total_cases: int
    active_cases: int
    escalated_cases: int
    recovered_cases: int
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

    forecast: RecoveryForecast | None = None
    category_distribution: list[CategoryBreakdown] = Field(default_factory=list)
    intervention_performance: list[ChannelPerformance] = Field(default_factory=list)
    rail_performance: list[RailPerformance] = Field(default_factory=list)
    time_series: list[TimePointStats] = Field(default_factory=list)
    time_to_recovery_buckets: list[TTRBucket] = Field(default_factory=list)
    daily_metrics: list[DailyMetricPoint] = Field(default_factory=list)
    monthly_metrics: list[MonthlyMetricPoint] = Field(default_factory=list)
    campaign_metrics: list[CampaignMetrics] = Field(default_factory=list)


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


def _compute_daily_metrics(cases: Sequence[RecoveryCase]) -> list[DailyMetricPoint]:
    """Aggregate cases by occurrence/creation day."""
    day_map: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "total": 0,
            "failed": 0,
            "recovered": 0,
            "escalated": 0,
            "at_risk": 0,
            "recovered_paise": 0,
            "nrv": 0,
        }
    )

    for c in cases:
        day_key = c.created_at.strftime("%Y-%m-%d")
        stats = day_map[day_key]
        stats["total"] += 1
        stats["at_risk"] += c.amount_paise

        if c.state == RecoveryState.RECOVERED:
            stats["recovered"] += 1
            stats["recovered_paise"] += c.recovered_amount_paise
            stats["nrv"] += c.net_recovered_value_paise
        elif c.state == RecoveryState.ESCALATED:
            stats["escalated"] += 1
        elif c.state in (RecoveryState.FAILED, RecoveryState.ABANDONED):
            stats["failed"] += 1
        else:
            # Active in-flight
            stats["failed"] += 1

    daily_points: list[DailyMetricPoint] = []
    for date_str in sorted(day_map.keys()):
        s = day_map[date_str]
        rate = (
            round((s["recovered"] / s["total"] * 100.0), 1) if s["total"] > 0 else 0.0
        )
        daily_points.append(
            DailyMetricPoint(
                date=date_str,
                total_transactions=s["total"],
                failed_count=s["failed"],
                recovered_count=s["recovered"],
                escalated_count=s["escalated"],
                at_risk_paise=s["at_risk"],
                recovered_paise=s["recovered_paise"],
                net_recovered_value_paise=s["nrv"],
                recovery_rate_pct=rate,
            )
        )
    return daily_points


def _compute_monthly_metrics(cases: Sequence[RecoveryCase]) -> list[MonthlyMetricPoint]:
    """Aggregate cases by month."""
    month_map: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "total": 0,
            "failed": 0,
            "recovered": 0,
            "escalated": 0,
            "at_risk": 0,
            "recovered_paise": 0,
            "nrv": 0,
        }
    )

    for c in cases:
        month_key = c.created_at.strftime("%Y-%m")
        stats = month_map[month_key]
        stats["total"] += 1
        stats["at_risk"] += c.amount_paise

        if c.state == RecoveryState.RECOVERED:
            stats["recovered"] += 1
            stats["recovered_paise"] += c.recovered_amount_paise
            stats["nrv"] += c.net_recovered_value_paise
        elif c.state == RecoveryState.ESCALATED:
            stats["escalated"] += 1
        elif c.state in (RecoveryState.FAILED, RecoveryState.ABANDONED):
            stats["failed"] += 1
        else:
            stats["failed"] += 1

    monthly_points: list[MonthlyMetricPoint] = []
    for m_str in sorted(month_map.keys()):
        s = month_map[m_str]
        rate = (
            round((s["recovered"] / s["total"] * 100.0), 1) if s["total"] > 0 else 0.0
        )
        monthly_points.append(
            MonthlyMetricPoint(
                month=m_str,
                total_transactions=s["total"],
                failed_count=s["failed"],
                recovered_count=s["recovered"],
                escalated_count=s["escalated"],
                at_risk_paise=s["at_risk"],
                recovered_paise=s["recovered_paise"],
                net_recovered_value_paise=s["nrv"],
                recovery_rate_pct=rate,
            )
        )
    return monthly_points


def _compute_time_to_recovery(cases: Sequence[RecoveryCase]) -> list[TTRBucket]:
    """Compute empirical time-to-recovery latency distribution from case resolution deltas."""
    recovered_cases = [c for c in cases if c.state == RecoveryState.RECOVERED]

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
        for entry in c.audit_trail:
            if entry.event_name in ("case.recovered", "payment.captured"):
                delta_seconds = max(
                    0.0, (entry.timestamp - c.created_at).total_seconds()
                )
                break

        for name, lower_s, upper_s in buckets_def:
            if lower_s <= delta_seconds < upper_s:
                counts[name] += 1
                break

    return [
        TTRBucket(
            bucket=name,
            count=count,
            percentage=round((count / len(recovered_cases) * 100.0), 1)
            if recovered_cases
            else 0.0,
        )
        for name, count in counts.items()
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
    daily_metrics = _compute_daily_metrics(cases)
    monthly_metrics = _compute_monthly_metrics(cases)

    active_count = sum(
        1
        for c in cases
        if c.state
        in (
            RecoveryState.IN_DUNNING,
            RecoveryState.RETRY_SCHEDULED,
            RecoveryState.OUTREACH_PENDING,
            RecoveryState.ANALYSIS_QUEUED,
        )
    )
    escalated_count = sum(1 for c in cases if c.state == RecoveryState.ESCALATED)
    recovered_count = sum(1 for c in cases if c.state == RecoveryState.RECOVERED)

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
    forecast_data = _compute_recovery_forecast(cases, lift)
    campaign_list = _compute_campaign_metrics(cases)

    return AnalyticsSummaryResponse(
        total_cases=total_cases,
        active_cases=active_count,
        escalated_cases=escalated_count,
        recovered_cases=recovered_count,
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
        forecast=forecast_data,
        category_distribution=cat_distribution,
        intervention_performance=perf_list,
        rail_performance=rail_list,
        time_series=time_series_points,
        time_to_recovery_buckets=ttr_buckets,
        daily_metrics=daily_metrics,
        monthly_metrics=monthly_metrics,
        campaign_metrics=campaign_list,
    )


def _compute_campaign_metrics(
    cases: Sequence[RecoveryCase],
) -> list[CampaignMetrics]:
    """Aggregate recovery metrics per campaign_id extracted from Razorpay notes."""
    buckets: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "total": 0,
            "recovered": 0,
            "escalated": 0,
            "at_risk": 0,
            "recovered_paise": 0,
            "nrv": 0,
        }
    )
    for c in cases:
        cid = getattr(c, "campaign_id", None) or getattr(
            c.failure_event, "campaign_id", None
        )
        if not cid:
            cid = "untagged"
        b = buckets[cid]
        b["total"] += 1
        b["at_risk"] += c.amount_paise
        if c.state == RecoveryState.RECOVERED:
            b["recovered"] += 1
            b["recovered_paise"] += c.recovered_amount_paise
            b["nrv"] += c.net_recovered_value_paise
        if c.state == RecoveryState.ESCALATED:
            b["escalated"] += 1

    result: list[CampaignMetrics] = []
    for campaign_id, b in sorted(
        buckets.items(), key=lambda x: x[1]["at_risk"], reverse=True
    ):
        rate = round((b["recovered"] / b["total"] * 100.0) if b["total"] else 0.0, 1)
        avg = b["at_risk"] // max(1, b["total"])
        result.append(
            CampaignMetrics(
                campaign_id=campaign_id,
                total_cases=b["total"],
                recovered_cases=b["recovered"],
                escalated_cases=b["escalated"],
                at_risk_paise=b["at_risk"],
                recovered_paise=b["recovered_paise"],
                net_recovered_value_paise=b["nrv"],
                recovery_rate_pct=rate,
                avg_amount_paise=avg,
            )
        )
    return result


def _compute_recovery_forecast(
    cases: Sequence[RecoveryCase], lift_pct: float
) -> RecoveryForecast:
    """Deterministic conversion model computing recovery funnel and remaining opportunity."""
    active_states = {
        RecoveryState.IN_DUNNING,
        RecoveryState.RETRY_SCHEDULED,
        RecoveryState.OUTREACH_PENDING,
        RecoveryState.ANALYSIS_QUEUED,
        RecoveryState.P2P_WAITING,
        RecoveryState.P2P_PROMISED,
    }
    open_cases = [c for c in cases if c.state in active_states]
    recovered_cases = [c for c in cases if c.state == RecoveryState.RECOVERED]

    total_at_risk_open = sum(c.amount_paise for c in open_cases)
    total_recovered_so_far = sum(c.recovered_amount_paise for c in recovered_cases)

    # Compute segmented baseline recovery rates by payment rail
    rail_rates: dict[str, float] = {}
    for rail in PaymentRail:
        rail_cases = [c for c in cases if c.failure_event.payment_rail == rail]
        rail_rec = [c for c in rail_cases if c.state == RecoveryState.RECOVERED]
        if len(rail_cases) >= 5:  # noqa: PLR2004
            rail_rates[rail.value] = len(rail_rec) / len(rail_cases)
        else:
            rail_rates[rail.value] = (
                (len(recovered_cases) / len(cases)) if cases else 0.50
            )

    segments: list[SegmentForecast] = []
    expected_recoverable_total = 0

    for rail in PaymentRail:
        r_cases = [c for c in open_cases if c.failure_event.payment_rail == rail]
        r_at_risk = sum(c.amount_paise for c in r_cases)
        p = round(rail_rates.get(rail.value, 0.50), 2)
        exp_paise = int(r_at_risk * p)
        expected_recoverable_total += exp_paise
        if r_at_risk > 0:
            segments.append(
                SegmentForecast(
                    segment=rail.value,
                    expected_probability=p,
                    at_risk_paise=r_at_risk,
                    expected_recoverable_paise=exp_paise,
                )
            )

    remaining_opportunity = expected_recoverable_total
    attributable_remaining = int(total_at_risk_open * max(0.0, lift_pct / 100.0))
    expected_rate = (
        round((expected_recoverable_total / total_at_risk_open * 100.0), 1)
        if total_at_risk_open > 0
        else 0.0
    )

    return RecoveryForecast(
        at_risk_paise=total_at_risk_open,
        expected_recoverable_paise=expected_recoverable_total,
        recovered_paise=total_recovered_so_far,
        remaining_opportunity_paise=remaining_opportunity,
        attributable_remaining_paise=attributable_remaining,
        expected_recovery_rate_pct=expected_rate,
        confidence_window_pct=5.0,
        segments=segments,
    )


@router.get(
    "/forecast",
    response_model=RecoveryForecast,
    summary="Get Merchant Recovery Forecast and Remaining Opportunity Funnel",
)
async def get_recovery_forecast() -> RecoveryForecast:
    """Return deterministic recovery forecast funnel and attributable lift."""
    repo = get_case_repository()
    cases = list(repo.list_cases(limit=10000))
    treatment_cases = [c for c in cases if c.experiment_arm == ExperimentArm.TREATMENT]
    holdout_cases = [
        c for c in cases if c.experiment_arm == ExperimentArm.HOLDOUT_CONTROL
    ]
    treatment_rec = sum(
        1 for c in treatment_cases if c.state == RecoveryState.RECOVERED
    )
    holdout_rec = sum(1 for c in holdout_cases if c.state == RecoveryState.RECOVERED)
    t_rate = (treatment_rec / len(treatment_cases) * 100.0) if treatment_cases else 0.0
    h_rate = (holdout_rec / len(holdout_cases) * 100.0) if holdout_cases else 0.0
    lift = round(t_rate - h_rate, 2)
    return _compute_recovery_forecast(cases, lift)


@router.get(
    "/escalations",
    response_model=list[EscalationQueueItem],
    summary="Get Expected Recoverable Value (EV) Prioritized Operator Escalation Queue",
)
async def get_escalation_queue() -> list[EscalationQueueItem]:
    """Return all cases currently requiring human operator action, prioritized by EV."""
    repo = get_case_repository()
    escalated_cases = repo.list_cases(state=RecoveryState.ESCALATED, limit=200)
    policy = get_active_policy()

    queue: list[EscalationQueueItem] = []

    for c in escalated_cases:
        # 1. Surface the persisted why from audit trail
        reason_found: str | None = None
        for entry in reversed(c.audit_trail):
            if entry.event_name in (
                "intervention.pending_human_approval",
                "intervention.escalated",
                "policy.blocked",
                "case.escalated",
            ) or entry.actor in (
                AuditActor.POLICY_GATE,
                AuditActor.HUMAN_OPERATOR,
                AuditActor.SYSTEM,
            ):
                reason_found = (
                    entry.notes
                    or getattr(entry, "reason", None)
                    or (
                        entry.decision_inputs.get("plan", {}).get("rationale")
                        if isinstance(entry.decision_inputs.get("plan"), dict)
                        else None
                    )
                )
                if reason_found:
                    break

        if not reason_found:
            reason_found = f"Policy ceiling exceeded: {c.touches_count} touches completed on {c.failure_event.payment_rail.value}."

        # 2. Customer Profile & Rail Health Informed Opportunity Scoring
        amount = c.amount_paise
        rail = c.failure_event.payment_rail
        touches = c.touches_count

        cust_profile = get_customer_profile_registry().get_profile(
            c.failure_event.customer_id
        )
        rail_degraded = get_rail_health_registry().is_rail_degraded(rail)

        recommended_action = "Approve smart retry on backup rail"
        recommended_discount = 0

        if "HITL" in reason_found or "human approval" in reason_found.lower():
            prob = 0.85
            recommended_action = "Approve formulated AI recovery plan"
        elif touches >= policy.max_touches:
            prob = 0.60
            recommended_discount = policy.max_discount_bps
            recommended_action = (
                f"Grant {recommended_discount / 100:.2f}% discount "
                "incentive link via WhatsApp"
            )
        elif rail in (PaymentRail.UPI, PaymentRail.UPI_AUTOPAY):
            prob = 0.75
            recommended_action = "Issue dynamic UPI intent payment link"
        elif amount > policy.require_human_above_paise:
            prob = 0.70
            recommended_action = "Operator manual phone outreach & payment concierge"
        else:
            prob = 0.50

        # Blend customer historical recovery rate if customer has prior history
        if cust_profile.total_cases >= 2:  # noqa: PLR2004
            prob = round(
                max(
                    0.20, min(0.95, (prob * 0.4) + (cust_profile.recovered_rate * 0.6))
                ),
                2,
            )

        # Discount expected probability if current rail is degraded
        if rail_degraded:
            prob = round(max(0.15, prob * 0.5), 2)
            recommended_action = (
                f"Rail {rail.value} degraded - convert to alternate rail link"
            )

        ev_paise = int(amount * prob)

        queue.append(
            EscalationQueueItem(
                case_id=c.case_id,
                customer_id=c.failure_event.customer_id,
                payment_id=c.failure_event.payment_id,
                payment_rail=c.failure_event.payment_rail.value,
                amount_paise=amount,
                expected_recoverable_value_paise=ev_paise,
                estimated_recovery_probability=prob,
                escalation_reason=reason_found,
                recommended_action=recommended_action,
                recommended_discount_bps=recommended_discount,
                touches_count=touches,
                created_at=c.created_at.isoformat(),
                state=c.state.value,
            )
        )

    # Sort strictly by Expected Recoverable Value descending
    queue.sort(key=lambda x: x.expected_recoverable_value_paise, reverse=True)
    return queue
