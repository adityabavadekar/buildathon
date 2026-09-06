"""Recovery analytics: attribution, counterfactual metrics, rail breakdown, time
series, and the EV-prioritised escalation queue.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.audit.global_log import record_global_audit
from app.audit.repository import get_case_repository
from app.core.cache import cached_model, get_cached_json, set_cached_json
from app.core.config import get_settings
from app.core.enums import (
    AuditActor,
    EscalationReason,
    PaymentRail,
    RecoveryState,
)
from app.detection.clustering import recompute_patterns
from app.detection.customer_profile import get_customer_profile_registry
from app.detection.ml import get_recovery_model, train_recovery_model
from app.detection.rail_health import get_rail_health_registry
from app.intervention.policy_gate import get_active_policy

if TYPE_CHECKING:
    from app.audit.models import AuditEntry, RecoveryCase

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
    # Retraining changes how every open case is scored, so it belongs in the
    # trail. Zero cases is reported as untrained rather than as a success.
    record_global_audit(
        event_name="model.retrained",
        actor=AuditActor.HUMAN_OPERATOR,
        reason=f"Operator retrained the recovery model to {model.version}.",
        notes=(
            f"Trained on {model.trained_count} treatment cases."
            if model.trained_count
            else "No treatment cases available, so the model is untrained."
        ),
        decision_outputs={
            "version": model.version,
            "trained_count": model.trained_count,
            "cv_metrics": model.cv_metrics,
            "holdout_metrics": model.holdout_metrics,
        },
    )
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
    attempts_count: int
    created_at: str
    state: str


class FailedExecutionQueueItem(BaseModel):
    """A case escalated only because a live gateway call failed -- needs a retry
    or an engineer, not merchant judgment. Kept out of EscalationQueueItem so the
    two never mix in one queue or one count.
    """

    case_id: str
    customer_id: str
    payment_id: str
    payment_rail: str
    amount_paise: int
    attempted_intervention: str
    failure_reason: str
    attempts_count: int
    failed_at: str
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

    # Quoting recovery without the live/simulated split is unfalsifiable.
    live_executions: int
    simulated_executions: int
    simulated_cost_paise: int

    health_score: int
    # False until at least one treatment case has resolved (recovered or not).
    # The score formula floors at 20 with zero signal, which reads as "unhealthy"
    # rather than "no data yet" -- callers must check this before showing the score.
    health_score_available: bool

    forecast: RecoveryForecast | None = None
    category_distribution: list[CategoryBreakdown] = Field(default_factory=list)
    intervention_performance: list[ChannelPerformance] = Field(default_factory=list)
    rail_performance: list[RailPerformance] = Field(default_factory=list)
    time_series: list[TimePointStats] = Field(default_factory=list)
    time_to_recovery_buckets: list[TTRBucket] = Field(default_factory=list)
    daily_metrics: list[DailyMetricPoint] = Field(default_factory=list)
    monthly_metrics: list[MonthlyMetricPoint] = Field(default_factory=list)
    campaign_metrics: list[CampaignMetrics] = Field(default_factory=list)


def _bucket_recovery_rate(total: int, recovered: int) -> float:
    return round((recovered / total * 100.0), 1) if total > 0 else 0.0


def _time_series_from_windows(windows: dict[str, Any]) -> list[TimePointStats]:
    labels = [
        ("T-48h", "t48"),
        ("T-36h", "t36"),
        ("T-24h", "t24"),
        ("T-12h", "t12"),
        ("T-6h", "t06"),
        ("Current", "current"),
    ]
    return [
        TimePointStats(
            label=label,
            failed_paise=int(windows.get(f"failed_{key}", 0) or 0),
            recovered_paise=int(windows.get(f"recovered_{key}", 0) or 0),
        )
        for label, key in labels
    ]


def _rail_performance_from_rows(rows: list[dict[str, Any]]) -> list[RailPerformance]:
    return [
        RailPerformance(
            rail=r["rail"],
            total_cases=r["total_cases"],
            recovered_cases=r["recovered_cases"],
            recovery_rate_pct=_bucket_recovery_rate(
                r["total_cases"], r["recovered_cases"]
            ),
            total_at_risk_paise=r["total_at_risk_paise"],
            recovered_paise=r["recovered_paise"],
        )
        for r in rows
        if r["total_cases"] > 0
    ]


def _channel_performance_from_rows(
    rows: list[dict[str, Any]],
) -> tuple[list[ChannelPerformance], int, int]:
    known_types = (
        "PASSIVE_RETRY",
        "SMART_RETRY",
        "SMART_PAYMENT_LINK",
        "INCENTIVIZED_LINK",
        "CUSTOMER_NUDGE",
    )
    by_type = {r["intervention_type"]: r for r in rows}
    total_gw_fees = 0
    total_comm_cost = 0
    for r in rows:
        itype = r["intervention_type"]
        cost = int(r["cost_paise"] or 0)
        if "RETRY" in str(itype):
            total_gw_fees += cost
        else:
            total_comm_cost += cost

    perf_list = [
        ChannelPerformance(
            intervention_type=itype,
            total_attempts=int(by_type.get(itype, {}).get("attempts", 0)),
            successful_recoveries=int(by_type.get(itype, {}).get("successes", 0)),
            success_rate_pct=_bucket_recovery_rate(
                int(by_type.get(itype, {}).get("attempts", 0)),
                int(by_type.get(itype, {}).get("successes", 0)),
            ),
        )
        for itype in known_types
    ]
    return perf_list, total_gw_fees, total_comm_cost


def _category_distribution_from_rows(
    rows: list[dict[str, Any]], total_cases: int
) -> list[CategoryBreakdown]:
    return [
        CategoryBreakdown(
            category=r["category"],
            count=r["count"],
            percentage=round((r["count"] / total_cases * 100.0), 1)
            if total_cases
            else 0.0,
        )
        for r in rows
    ]


def _daily_metrics_from_rows(rows: list[dict[str, Any]]) -> list[DailyMetricPoint]:
    return [
        DailyMetricPoint(
            date=r["bucket"],
            total_transactions=r["total"],
            failed_count=r["failed"],
            recovered_count=r["recovered"],
            escalated_count=r["escalated"],
            at_risk_paise=r["at_risk_paise"],
            recovered_paise=r["recovered_paise"],
            net_recovered_value_paise=r["nrv_paise"],
            recovery_rate_pct=_bucket_recovery_rate(r["total"], r["recovered"]),
        )
        for r in rows
    ]


def _monthly_metrics_from_rows(rows: list[dict[str, Any]]) -> list[MonthlyMetricPoint]:
    return [
        MonthlyMetricPoint(
            month=r["bucket"],
            total_transactions=r["total"],
            failed_count=r["failed"],
            recovered_count=r["recovered"],
            escalated_count=r["escalated"],
            at_risk_paise=r["at_risk_paise"],
            recovered_paise=r["recovered_paise"],
            net_recovered_value_paise=r["nrv_paise"],
            recovery_rate_pct=_bucket_recovery_rate(r["total"], r["recovered"]),
        )
        for r in rows
    ]


def _time_to_recovery_from_deltas(deltas: list[float]) -> list[TTRBucket]:
    # Uses updated_at - created_at, not the recovery-event audit timestamp
    # the prior Python version preferred -- minor precision loss.
    buckets_def = [
        ("< 15 mins (Instant)", 0, 15 * 60),
        ("15m - 4 hrs (Transient)", 15 * 60, 4 * 3600),
        ("4h - 24 hrs (Nudge)", 4 * 3600, 24 * 3600),
        ("24h - 48 hrs (Liquidity)", 24 * 3600, 48 * 3600),
        ("> 48 hrs (B2B Invoice)", 48 * 3600, 365 * 86400),
    ]
    counts: dict[str, int] = {b[0]: 0 for b in buckets_def}
    for raw_delta in deltas:
        delta_seconds = max(0.0, raw_delta)
        for name, lower_s, upper_s in buckets_def:
            if lower_s <= delta_seconds < upper_s:
                counts[name] += 1
                break

    total = len(deltas)
    return [
        TTRBucket(
            bucket=name,
            count=count,
            percentage=round((count / total * 100.0), 1) if total else 0.0,
        )
        for name, count in counts.items()
    ]


def _campaign_metrics_from_rows(rows: list[dict[str, Any]]) -> list[CampaignMetrics]:
    return [
        CampaignMetrics(
            campaign_id=r["campaign"],
            total_cases=r["total"],
            recovered_cases=r["recovered"],
            escalated_cases=r["escalated"],
            at_risk_paise=r["at_risk_paise"],
            recovered_paise=r["recovered_paise"],
            net_recovered_value_paise=r["nrv_paise"],
            recovery_rate_pct=_bucket_recovery_rate(r["total"], r["recovered"]),
            avg_amount_paise=r["at_risk_paise"] // max(1, r["total"]),
        )
        for r in rows
    ]


@router.get(
    "",
    response_model=AnalyticsSummaryResponse,
    summary="Get Dynamic Recovery Analytics",
)
async def get_analytics_summary() -> AnalyticsSummaryResponse:
    """Compute and return aggregate revenue recovery metrics and counterfactual uplift."""
    cache_key = "analytics:summary:v1"
    cached = await get_cached_json(cache_key)
    if cached is not None:
        return AnalyticsSummaryResponse.model_validate_json(cached)

    repo = get_case_repository()
    agg = repo.get_analytics_aggregates()
    totals = agg["totals"]

    total_cases = int(totals.get("total_cases", 0) or 0)
    total_at_risk = int(totals.get("total_at_risk_paise", 0) or 0)
    recovered_amount = int(totals.get("recovered_amount_paise", 0) or 0)
    net_recovered = int(totals.get("net_recovered_paise", 0) or 0)
    total_discounts = int(totals.get("total_discounts_paise", 0) or 0)

    treatment_total = int(totals.get("treatment_total", 0) or 0)
    treatment_rec = int(totals.get("treatment_recovered", 0) or 0)
    holdout_total = int(totals.get("holdout_total", 0) or 0)
    holdout_rec = int(totals.get("holdout_recovered", 0) or 0)
    recovered_count = int(totals.get("recovered_count", 0) or 0)

    treatment_rate = (
        (treatment_rec / treatment_total * 100.0) if treatment_total else 0.0
    )
    holdout_rate = (holdout_rec / holdout_total * 100.0) if holdout_total else 0.0
    overall_rate = (recovered_count / total_cases * 100.0) if total_cases else 0.0
    lift = round(treatment_rate - holdout_rate, 2)

    cat_distribution = _category_distribution_from_rows(agg["categories"], total_cases)
    rail_list = _rail_performance_from_rows(agg["rails"])
    perf_list, total_gw_fees, total_comm_cost = _channel_performance_from_rows(
        agg["channels"]
    )
    time_series_points = _time_series_from_windows(agg["windows"])
    ttr_buckets = _time_to_recovery_from_deltas(agg["ttr_delta_seconds"])
    daily_metrics = _daily_metrics_from_rows(agg["daily"])
    monthly_metrics = _monthly_metrics_from_rows(agg["monthly"])
    campaign_list = _campaign_metrics_from_rows(agg["campaigns"])

    active_count = int(totals.get("active_count", 0) or 0)
    escalated_count = int(totals.get("escalated_count", 0) or 0)

    total_spend = total_gw_fees + total_comm_cost + total_discounts
    rors = (
        round(recovered_amount / total_spend, 1)
        if total_spend > 0
        else (50.0 if recovered_amount > 0 else 0.0)
    )
    health_score_available = int(totals.get("treatment_settled_count", 0) or 0) > 0
    health_score = (
        min(100, max(20, int(treatment_rate * 1.1 + (lift * 1.5))))
        if health_score_available
        else 0
    )
    forecast_data = _recovery_forecast_from_rows(agg["rails"], lift)
    fidelity = repo.get_execution_fidelity()

    response = AnalyticsSummaryResponse(
        total_cases=total_cases,
        active_cases=active_count,
        escalated_cases=escalated_count,
        recovered_cases=recovered_count,
        total_at_risk_paise=total_at_risk,
        recovered_amount_paise=recovered_amount,
        net_recovered_value_paise=net_recovered,
        overall_recovery_rate_pct=round(overall_rate, 1),
        treatment_total=treatment_total,
        treatment_recovered=treatment_rec,
        treatment_recovery_rate_pct=round(treatment_rate, 1),
        holdout_total=holdout_total,
        holdout_recovered=holdout_rec,
        holdout_recovery_rate_pct=round(holdout_rate, 1),
        attributable_lift_pct=lift,
        total_gateway_fees_paise=total_gw_fees,
        total_communication_cost_paise=total_comm_cost,
        total_discounts_granted_paise=total_discounts,
        live_executions=fidelity["live_executions"],
        simulated_executions=fidelity["simulated_executions"],
        simulated_cost_paise=fidelity["simulated_cost_paise"],
        return_on_recovery_spend=rors,
        health_score=health_score,
        health_score_available=health_score_available,
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
    await set_cached_json(
        cache_key,
        response.model_dump_json(),
        get_settings().analytics_cache_ttl_seconds,
    )
    return response


def _recovery_forecast_from_rows(
    rail_rows: list[dict[str, Any]], lift_pct: float
) -> RecoveryForecast:
    """Per-rail recovery rate uses that rail's own history when it has enough
    volume (>=5 cases) to be meaningful; thin rails fall back to the overall
    recovery rate across all cases, matching the previous Python version.
    """
    total_cases = sum(r["total_cases"] for r in rail_rows)
    total_recovered_cases = sum(r["recovered_cases"] for r in rail_rows)
    overall_rate = (total_recovered_cases / total_cases) if total_cases else 0.50

    total_at_risk_open = sum(r["open_at_risk_paise"] for r in rail_rows)
    total_recovered_so_far = sum(r["recovered_paise"] for r in rail_rows)

    segments: list[SegmentForecast] = []
    expected_recoverable_total = 0

    for r in rail_rows:
        rail_total = r["total_cases"]
        rail_rec = r["recovered_cases"]
        p = (rail_rec / rail_total) if rail_total >= 5 else overall_rate  # noqa: PLR2004
        p = round(p, 2)
        r_at_risk = r["open_at_risk_paise"]
        exp_paise = int(r_at_risk * p)
        expected_recoverable_total += exp_paise
        if r_at_risk > 0:
            segments.append(
                SegmentForecast(
                    segment=r["rail"],
                    expected_probability=p,
                    at_risk_paise=r_at_risk,
                    expected_recoverable_paise=exp_paise,
                )
            )

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
        remaining_opportunity_paise=expected_recoverable_total,
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

    async def _compute() -> RecoveryForecast:
        repo = get_case_repository()
        agg = repo.get_analytics_aggregates()
        totals = agg["totals"]
        treatment_total = int(totals.get("treatment_total", 0) or 0)
        treatment_rec = int(totals.get("treatment_recovered", 0) or 0)
        holdout_total = int(totals.get("holdout_total", 0) or 0)
        holdout_rec = int(totals.get("holdout_recovered", 0) or 0)
        t_rate = (treatment_rec / treatment_total * 100.0) if treatment_total else 0.0
        h_rate = (holdout_rec / holdout_total * 100.0) if holdout_total else 0.0
        lift = round(t_rate - h_rate, 2)
        return _recovery_forecast_from_rows(agg["rails"], lift)

    return await cached_model(
        "analytics:forecast:v1",
        get_settings().analytics_cache_ttl_seconds,
        RecoveryForecast,
        _compute,
    )


def _escalation_reason(case: RecoveryCase) -> str:
    """Human-facing why for a case in the human-judgment escalation queue.

    Called only for cases already filtered to escalation_reason ==
    HUMAN_JUDGMENT, so the entry that actually recorded the escalation (its
    to_state transition into ESCALATED) is exactly the one worth quoting.
    """
    for entry in reversed(case.audit_trail):
        if entry.to_state == RecoveryState.ESCALATED:
            reason = (
                entry.notes
                or getattr(entry, "reason", None)
                or (
                    entry.decision_inputs.get("plan", {}).get("rationale")
                    if isinstance(entry.decision_inputs.get("plan"), dict)
                    else None
                )
            )
            if reason:
                return reason
    return (
        f"Policy ceiling exceeded: {case.attempts_count} attempts completed "
        f"on {case.failure_event.payment_rail.value}."
    )


@router.get(
    "/escalations",
    response_model=list[EscalationQueueItem],
    summary="Get Expected Recoverable Value (EV) Prioritized Operator Escalation Queue",
)
async def get_escalation_queue() -> list[EscalationQueueItem]:
    """Cases where a human must exercise judgment: fraud suspicion, policy-required
    approval, or a plan the agent explicitly routed for review. Excludes cases
    escalated only because a live gateway call failed (see /failed-executions) --
    those need a retry or an engineer, not a merchant's judgment, and mixing them
    in here would both misrepresent what the queue means and inflate the
    Manual Approvals count with infrastructure noise.
    """
    repo = get_case_repository()
    escalated_cases = repo.list_cases(
        state=RecoveryState.ESCALATED,
        escalation_reason=EscalationReason.HUMAN_JUDGMENT.value,
        limit=200,
    )
    policy = get_active_policy()

    queue: list[EscalationQueueItem] = []

    for c in escalated_cases:
        reason_found = _escalation_reason(c)

        # 2. Customer Profile & Rail Health Informed Opportunity Scoring
        amount = c.amount_paise
        rail = c.failure_event.payment_rail
        attempts = c.attempts_count

        cust_profile = get_customer_profile_registry().get_profile(
            c.failure_event.customer_id
        )
        rail_degraded = get_rail_health_registry().is_rail_degraded(rail)

        recommended_action = "Approve smart retry on backup rail"
        recommended_discount = 0

        if "routed to human operations queue" in reason_found:
            # The plan itself asked for a human, e.g. suspected fraud, an
            # ambiguous customer decline, or an unresolved gateway timeout --
            # "retry" or "send another link" would be actively wrong advice
            # here, not just generic.
            prob = 0.50
            recommended_action = "Review case detail and rationale before acting"
        elif "HITL" in reason_found or "human approval" in reason_found.lower():
            prob = 0.85
            recommended_action = "Approve formulated AI recovery plan"
        elif attempts >= policy.max_attempts:
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
                attempts_count=attempts,
                created_at=c.created_at.isoformat(),
                state=c.state.value,
            )
        )

    # Highest expected recoverable value first.
    queue.sort(key=lambda x: x.expected_recoverable_value_paise, reverse=True)
    return queue


@router.get(
    "/failed-executions",
    response_model=list[FailedExecutionQueueItem],
    summary="Get cases stuck on a failed live gateway call, most recent first",
)
async def get_failed_execution_queue() -> list[FailedExecutionQueueItem]:
    """Cases where the agent chose a valid intervention but the live Razorpay
    call itself failed (rate limit, missing credentials, 4xx/5xx, network
    error) -- distinct from /escalations, which is for cases needing a human's
    judgment on what to do. Nothing here needs a decision; it needs the
    underlying call retried or the integration fixed.
    """
    repo = get_case_repository()
    escalated_cases = repo.list_cases(
        state=RecoveryState.ESCALATED,
        escalation_reason=EscalationReason.SYSTEM_ERROR.value,
        limit=200,
    )

    queue: list[FailedExecutionQueueItem] = []

    for c in escalated_cases:
        latest_failure: AuditEntry | None = None
        for entry in reversed(c.audit_trail):
            if entry.to_state == RecoveryState.ESCALATED:
                latest_failure = entry
                break

        if latest_failure is None:
            continue

        plan = latest_failure.decision_inputs.get("plan")
        attempted_intervention = (
            plan.get("intervention_type", "UNKNOWN")
            if isinstance(plan, dict)
            else "UNKNOWN"
        )

        queue.append(
            FailedExecutionQueueItem(
                case_id=c.case_id,
                customer_id=c.failure_event.customer_id,
                payment_id=c.failure_event.payment_id,
                payment_rail=c.failure_event.payment_rail.value,
                amount_paise=c.amount_paise,
                attempted_intervention=attempted_intervention,
                failure_reason=latest_failure.notes or "Execution failed.",
                attempts_count=c.attempts_count,
                failed_at=latest_failure.timestamp.isoformat(),
                state=c.state.value,
            )
        )

    queue.sort(key=lambda x: x.failed_at, reverse=True)
    return queue
