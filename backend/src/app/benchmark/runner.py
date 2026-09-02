"""Benchmark runner: replay the fixed dataset and score it against the holdout.

Outcomes use the dataset's pre-rolled values, so the arm a case lands in cannot
change its coin flip - only whether the treatment uplift applies. That keeps
measured lift attributable to the agent's actions rather than to sampling luck.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from app.audit.repository import get_case_repository
from app.benchmark.dataset import (
    BENCHMARK_DATASET_VERSION,
    DEFAULT_BENCHMARK_SEED,
    DEFAULT_BENCHMARK_SIZE,
    PARTIAL_CAPTURE_SHARE,
    build_benchmark_events,
    dataset_fingerprint,
    treated_propensity,
)
from app.core.enums import ExperimentArm, RecoveryState
from app.core.logging import get_logger
from app.intervention.orchestrator import get_recovery_orchestrator

if TYPE_CHECKING:
    from app.audit.models import RecoveryCase

logger = get_logger(__name__)

BPS_DIVISOR = 10000

# A stratum's control rate is an estimate; below this many control cases it is
# too noisy to scale onto a treatment base. At a 10% holdout, high-ticket
# categories can otherwise land 3 control cases whose rate swings the whole
# attribution by lakhs. Such strata are excluded and reported as uncovered
# rather than silently trusted.
MIN_CONTROL_CASES_PER_STRATUM = 8

# Below this share of treatment value having a comparator, an attributed money
# figure is not defensible and the report says so instead of printing one.
MIN_COVERAGE_PCT = 60.0


@dataclass
class ArmResult:
    """Aggregate outcome for one experiment arm."""

    arm: str
    case_count: int = 0
    recovered_count: int = 0
    at_risk_paise: int = 0
    recovered_paise: int = 0
    cost_paise: int = 0
    net_recovered_paise: int = 0
    touches: int = 0
    escalated_count: int = 0
    # At-risk value of the cases that recovered, used to derive capture depth.
    recovered_case_at_risk_paise: int = 0

    @property
    def recovery_rate_pct(self) -> float:
        if self.case_count == 0:
            return 0.0
        return round(self.recovered_count / self.case_count * 100, 2)

    @property
    def value_recovery_rate_pct(self) -> float:
        """Share of at-risk money recovered, which case counts alone hide."""
        if self.at_risk_paise == 0:
            return 0.0
        return round(self.recovered_paise / self.at_risk_paise * 100, 2)

    def as_dict(self) -> dict[str, Any]:
        return {
            "arm": self.arm,
            "case_count": self.case_count,
            "recovered_count": self.recovered_count,
            "at_risk_paise": self.at_risk_paise,
            "recovered_paise": self.recovered_paise,
            "cost_paise": self.cost_paise,
            "net_recovered_paise": self.net_recovered_paise,
            "escalated_count": self.escalated_count,
            "recovered_case_at_risk_paise": self.recovered_case_at_risk_paise,
            "total_touches": self.touches,
            "recovery_rate_pct": self.recovery_rate_pct,
            "value_recovery_rate_pct": self.value_recovery_rate_pct,
        }


@dataclass
class BenchmarkRun:
    """A completed benchmark, carrying everything needed to defend its numbers."""

    run_id: str
    dataset: dict[str, Any]
    seed: int
    started_at: datetime
    finished_at: datetime
    treatment: ArmResult
    holdout: ArmResult
    per_category: dict[str, dict[str, Any]] = field(default_factory=dict)
    # category -> (treatment, holdout), the strata the counterfactual uses.
    per_category_arms: dict[str, tuple[ArmResult, ArmResult]] = field(
        default_factory=dict
    )
    failures: list[str] = field(default_factory=list)

    @property
    def replay_failures_count(self) -> int:
        """Rows the engine could not process, which would invalidate a claim."""
        return len(self.failures)

    @property
    def lift_pct_points(self) -> float:
        """Treatment minus holdout recovery rate, in percentage points."""
        return round(
            self.treatment.recovery_rate_pct - self.holdout.recovery_rate_pct, 2
        )

    @property
    def counterfactual_recovered_paise(self) -> int:
        """What the treatment arm would likely have recovered untouched.

        Stratified by category, never pooled: ticket sizes span three orders of
        magnitude, so a pooled rate lets one recovered B2B invoice in a small
        holdout drive attributable recovery negative. Strata below the control
        floor are skipped, which biases the claim high - hence
        ``counterfactual_coverage_pct``.
        """
        total = 0
        for stratum in self.per_category_arms.values():
            treated, control = stratum
            if (
                control.case_count < MIN_CONTROL_CASES_PER_STRATUM
                or treated.at_risk_paise == 0
            ):
                continue
            # Probability from the control arm, amounts from the treatment arm,
            # so differing ticket mixes cannot distort the comparison.
            control_probability = control.recovered_count / control.case_count
            capture_depth = (
                control.recovered_paise / control.recovered_case_at_risk_paise
                if control.recovered_case_at_risk_paise > 0
                else 1.0
            )
            total += int(treated.at_risk_paise * control_probability * capture_depth)
        return total

    @property
    def counterfactual_coverage_pct(self) -> float:
        """Share of treatment at-risk value that had a holdout comparator."""
        if self.treatment.at_risk_paise == 0:
            return 0.0
        covered = sum(
            treated.at_risk_paise
            for treated, control in self.per_category_arms.values()
            if (
                control.case_count >= MIN_CONTROL_CASES_PER_STRATUM
                and treated.at_risk_paise > 0
            )
        )
        return round(covered / self.treatment.at_risk_paise * 100, 2)

    @property
    def attributable_recovered_paise(self) -> int:
        """Money the agent can claim beyond the stratified counterfactual.

        Only the covered portion of the treatment arm is compared, so this is a
        like-for-like figure rather than gross recovery minus a partial estimate.
        """
        covered_recovered = sum(
            treated.recovered_paise
            for treated, control in self.per_category_arms.values()
            if control.case_count >= MIN_CONTROL_CASES_PER_STRATUM
            and treated.at_risk_paise > 0
        )
        return covered_recovered - self.counterfactual_recovered_paise

    @property
    def is_attribution_reliable(self) -> bool:
        """Whether the counterfactual covers enough value to quote a figure."""
        return self.counterfactual_coverage_pct >= MIN_COVERAGE_PCT

    @property
    def cost_per_recovered_rupee(self) -> float:
        """Outreach and discount spend per rupee of attributable recovery."""
        attributable = self.attributable_recovered_paise
        if attributable <= 0:
            return 0.0
        return round(self.treatment.cost_paise / attributable, 4)

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "dataset": self.dataset,
            "seed": self.seed,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "duration_seconds": round(
                (self.finished_at - self.started_at).total_seconds(), 3
            ),
            "treatment": self.treatment.as_dict(),
            "holdout": self.holdout.as_dict(),
            "lift_pct_points": self.lift_pct_points,
            "counterfactual_recovered_paise": self.counterfactual_recovered_paise,
            "counterfactual_coverage_pct": self.counterfactual_coverage_pct,
            "is_attribution_reliable": self.is_attribution_reliable,
            "min_control_cases_per_stratum": MIN_CONTROL_CASES_PER_STRATUM,
            "attributable_recovered_paise": self.attributable_recovered_paise,
            "cost_per_recovered_rupee": self.cost_per_recovered_rupee,
            "per_category": self.per_category,
            "replay_failures": self.failures,
        }


def _was_treated(case: RecoveryCase) -> bool:
    # A policy block or escalation must not earn the uplift, or the benchmark
    # credits the agent for work it did not do.
    if case.experiment_arm == ExperimentArm.HOLDOUT_CONTROL:
        return False
    return case.touches_count > 0 or case.outreach_count > 0


def _accumulate(target: ArmResult, case: RecoveryCase, *, recovered: bool) -> None:
    target.case_count += 1
    target.at_risk_paise += case.amount_paise
    target.touches += case.touches_count
    target.cost_paise += case.total_cost_paise
    if case.state == RecoveryState.ESCALATED:
        target.escalated_count += 1
    if recovered:
        target.recovered_count += 1
        target.recovered_case_at_risk_paise += case.amount_paise
        target.recovered_paise += case.recovered_amount_paise
        target.net_recovered_paise += case.net_recovered_value_paise


async def run_benchmark(
    *,
    size: int = DEFAULT_BENCHMARK_SIZE,
    seed: int = DEFAULT_BENCHMARK_SEED,
    use_llm: bool = False,
    isolate: bool = True,
) -> BenchmarkRun:
    """Replay the benchmark dataset through the live engine and score it.

    ``use_llm`` is off by default so a run is reproducible and free.
    """
    run_id = f"bench_{uuid4().hex[:12]}"
    # Namespacing payment ids to this run keeps repeat runs measurable; without
    # it the orchestrator's payment_id dedupe absorbs the second run entirely.
    rows = build_benchmark_events(
        size=size, seed=seed, run_tag=None if isolate is False else run_id[6:]
    )
    orchestrator = get_recovery_orchestrator()
    repo = get_case_repository()
    started_at = datetime.now(UTC)
    treatment = ArmResult(arm=ExperimentArm.TREATMENT.value)
    holdout = ArmResult(arm=ExperimentArm.HOLDOUT_CONTROL.value)
    category_totals: dict[str, ArmResult] = {}
    category_arms: dict[str, tuple[ArmResult, ArmResult]] = {}
    failures: list[str] = []

    logger.info(
        "benchmark.started",
        run_id=run_id,
        dataset_version=BENCHMARK_DATASET_VERSION,
        size=size,
        seed=seed,
        use_llm=use_llm,
    )

    for row in rows:
        try:
            case = await orchestrator.process_failure_event(row.event, use_llm=use_llm)
        except Exception as exc:  # noqa: BLE001 - one bad row must not void the run
            failures.append(f"{row.event.payment_id}: {type(exc).__name__}")
            logger.warning(
                "benchmark.event_failed",
                run_id=run_id,
                payment_id=row.event.payment_id,
                error=str(exc),
            )
            continue

        threshold = (
            treated_propensity(row.base_propensity)
            if _was_treated(case)
            else row.base_propensity
        )
        recovered = row.outcome_roll < threshold

        if recovered:
            amount = row.event.amount_paise
            if row.capture_roll < PARTIAL_CAPTURE_SHARE:
                amount = amount * row.partial_bps // BPS_DIVISOR
            orchestrator.process_payment_captured(
                payment_id=row.event.payment_id,
                amount_paise=amount,
                gateway_capture_id=f"bench_cap_{uuid4().hex[:10]}",
            )

        stored = repo.get_by_id(case.case_id) or case
        bucket = (
            holdout
            if stored.experiment_arm == ExperimentArm.HOLDOUT_CONTROL
            else treatment
        )
        _accumulate(bucket, stored, recovered=recovered)

        cat_key = row.category.value
        cat_bucket = category_totals.setdefault(cat_key, ArmResult(arm=cat_key))
        _accumulate(cat_bucket, stored, recovered=recovered)

        strata = category_arms.setdefault(
            cat_key,
            (
                ArmResult(arm=f"{cat_key}:treatment"),
                ArmResult(arm=f"{cat_key}:holdout"),
            ),
        )
        stratum = (
            strata[1]
            if stored.experiment_arm == ExperimentArm.HOLDOUT_CONTROL
            else strata[0]
        )
        _accumulate(stratum, stored, recovered=recovered)

    finished_at = datetime.now(UTC)
    run = BenchmarkRun(
        run_id=run_id,
        dataset=dataset_fingerprint(rows),
        seed=seed,
        started_at=started_at,
        finished_at=finished_at,
        treatment=treatment,
        holdout=holdout,
        per_category={k: v.as_dict() for k, v in sorted(category_totals.items())},
        per_category_arms=category_arms,
        failures=failures,
    )

    logger.info(
        "benchmark.completed",
        run_id=run_id,
        lift_pct_points=str(run.lift_pct_points),
        attributable_paise=run.attributable_recovered_paise,
        replay_failures=len(failures),
    )
    return run
