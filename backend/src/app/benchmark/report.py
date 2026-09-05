"""Markdown report writer: JSON cannot be cited in a PR or a pitch, so each run
lands in docs/benchmarks/ with its fingerprint and a verdict on defensibility.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from app.benchmark.runner import MIN_CONTROL_CASES_PER_STRATUM, MIN_COVERAGE_PCT
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.benchmark.runner import BenchmarkRun

logger = get_logger(__name__)

REPORTS_DIRNAME = "benchmarks"
PAISE_PER_RUPEE = 100


def _inr(paise: int) -> str:
    return f"INR {paise / PAISE_PER_RUPEE:,.2f}"


def _docs_root() -> Path:
    return Path(__file__).resolve().parents[4] / "docs"


def render_report(run: BenchmarkRun) -> str:
    """Render a benchmark run as a Markdown report."""
    data = run.as_dict()
    treatment = run.treatment
    holdout = run.holdout
    reliable = run.is_attribution_reliable

    lines: list[str] = [
        f"# Benchmark report - {run.run_id}",
        "",
        (
            f"Dataset `{data['dataset']['dataset_version']}`, seed `{run.seed}`, "
            f"{data['dataset']['event_count']} events replayed through the live "
            f"recovery engine on "
            f"{run.started_at.strftime('%Y-%m-%d %H:%M:%S')} UTC "
            f"in {data['duration_seconds']}s."
        ),
        "",
        "## Verdict",
        "",
    ]

    if reliable:
        lines += [
            (
                f"**Attribution is defensible.** "
                f"{run.counterfactual_coverage_pct}% of treatment value had a "
                f"same-category control comparator with at least "
                f"{MIN_CONTROL_CASES_PER_STRATUM} control cases."
            ),
            "",
            (
                f"- Recovery rate lift over holdout: **{run.lift_pct_points} "
                f"percentage points**"
            ),
            f"- Attributable recovery: **{_inr(run.attributable_recovered_paise)}**",
            (
                f"- Counterfactual (what the untouched arm predicts): "
                f"{_inr(run.counterfactual_recovered_paise)}"
            ),
        ]
    else:
        lines += [
            (
                f"**No attributable money figure is quoted for this run.** Only "
                f"{run.counterfactual_coverage_pct}% of treatment value had a "
                f"control comparator meeting the "
                f"{MIN_CONTROL_CASES_PER_STRATUM}-case floor, below the "
                f"{MIN_COVERAGE_PCT}% threshold. Raise the event count so each "
                f"failure category's holdout stratum is large enough to "
                f"estimate from."
            ),
            "",
            (
                f"- Recovery rate lift over holdout: {run.lift_pct_points} "
                f"percentage points (rate comparison only)"
            ),
        ]

    lines += [
        "",
        "## Arms",
        "",
        "| Arm | Cases | Recovered | Rate | At risk | Recovered | Cost | Escalated |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for arm in (treatment, holdout):
        lines.append(
            f"| {arm.arm} | {arm.case_count} | {arm.recovered_count} | "
            f"{arm.recovery_rate_pct}% | {_inr(arm.at_risk_paise)} | "
            f"{_inr(arm.recovered_paise)} | {_inr(arm.cost_paise)} | "
            f"{arm.escalated_count} |"
        )

    lines += [
        "",
        "## Per-category strata",
        "",
        (
            "A category contributes to the counterfactual only when its control "
            f"arm holds at least {MIN_CONTROL_CASES_PER_STRATUM} cases; smaller "
            "strata are listed as excluded rather than estimated from."
        ),
        "",
        "| Category | T cases | T recovered | C cases | C recovered | In counterfactual |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for category, (treated, control) in sorted(run.per_category_arms.items()):
        included = (
            control.case_count >= MIN_CONTROL_CASES_PER_STRATUM
            and treated.at_risk_paise > 0
        )
        lines.append(
            f"| {category} | {treated.case_count} | {treated.recovered_count} | "
            f"{control.case_count} | {control.recovered_count} | "
            f"{'yes' if included else 'excluded'} |"
        )

    mix = data["dataset"]
    lines += [
        "",
        "## Dataset fingerprint",
        "",
        f"- Total at risk: {_inr(mix['total_at_risk_paise'])}",
        f"- First payment id: `{mix['first_payment_id']}`",
        f"- Last payment id: `{mix['last_payment_id']}`",
        f"- Rail mix: {mix['rail_mix']}",
        f"- Category mix: {mix['category_mix']}",
        "",
        "## Integrity checks",
        "",
        (
            "- Base recovery propensities are modelling assumptions, not measured "
            "rates (see `benchmark/dataset.py`). They set the difficulty of the "
            "scenario; the lift, counterfactual, and coverage gate are computed "
            "from the engine's real behaviour on these events."
        ),
        f"- Events the engine failed to process: {run.replay_failures_count}",
        f"- Outreach cost booked to treatment: {_inr(treatment.cost_paise)}",
        f"- Cost per attributable rupee: {run.cost_per_recovered_rupee}",
    ]
    if run.failures:
        lines += ["", "Failed rows:", ""]
        lines += [f"- `{failure}`" for failure in run.failures[:20]]

    lines += [
        "",
        "---",
        "",
        (
            "Regenerate with "
            f"`POST /api/benchmark/run?size={mix['event_count']}"
            f"&seed={run.seed}`. The dataset is fixed, so the same seed scores "
            "the same events; payment ids carry a per-run suffix so repeat runs "
            "are not absorbed by idempotency, and experiment-arm assignment "
            "ignores that suffix so arms stay identical between runs."
        ),
        "",
    ]
    return "\n".join(lines)


def write_report(run: BenchmarkRun, *, docs_dir: Path | None = None) -> Path:
    """Write the run's Markdown report and return its path."""
    target_dir = (docs_dir or _docs_root()) / REPORTS_DIRNAME
    target_dir.mkdir(parents=True, exist_ok=True)

    stamp = run.started_at.strftime("%Y%m%d-%H%M%S")
    path = target_dir / f"{stamp}-{run.run_id}.md"
    path.write_text(render_report(run), encoding="utf-8")

    logger.info(
        "benchmark.report_written",
        run_id=run.run_id,
        path=str(path),
        reliable=run.is_attribution_reliable,
    )
    return path
