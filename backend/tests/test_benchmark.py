"""Tests for the fixed benchmark dataset and measurement harness."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.audit.repository import get_case_repository
from app.benchmark.cli import main as cli_main
from app.benchmark.dataset import (
    BASE_RECOVERY_PROPENSITY,
    BENCHMARK_DATASET_VERSION,
    build_benchmark_events,
    dataset_fingerprint,
    treated_propensity,
)
from app.benchmark.report import write_report
from app.benchmark.runner import run_benchmark
from app.core.enums import FailureCategory, PaymentRail
from app.intervention.models import MerchantPolicy
from app.intervention.policy_gate import get_active_policy, set_active_policy

if TYPE_CHECKING:
    from pathlib import Path

    from fastapi.testclient import TestClient


def test_dataset_is_deterministic_for_a_seed() -> None:
    """The same seed must reproduce byte-identical events, ids included."""
    first = build_benchmark_events(size=40, seed=1234)
    second = build_benchmark_events(size=40, seed=1234)

    assert [r.event.payment_id for r in first] == [r.event.payment_id for r in second]
    assert [r.event.amount_paise for r in first] == [
        r.event.amount_paise for r in second
    ]
    assert [r.outcome_roll for r in first] == [r.outcome_roll for r in second]
    assert [r.event.occurred_at for r in first] == [r.event.occurred_at for r in second]


def test_different_seeds_produce_different_datasets() -> None:
    a = build_benchmark_events(size=40, seed=1)
    b = build_benchmark_events(size=40, seed=2)
    assert [r.event.payment_id for r in a] != [r.event.payment_id for r in b]


def test_dataset_timestamps_do_not_drift_with_wall_clock() -> None:
    """Anchored to a fixed epoch so a rerun months later scores the same events."""
    rows = build_benchmark_events(size=20, seed=99)
    assert all(r.event.occurred_at.year == 2026 for r in rows)
    assert all(r.event.occurred_at.tzinfo is not None for r in rows)


def test_dataset_covers_every_rail_and_category() -> None:
    rows = build_benchmark_events(size=180, seed=7)
    rails = {r.event.payment_rail for r in rows}
    categories = {r.category for r in rows}

    for rail in PaymentRail:
        if rail is not PaymentRail.UNKNOWN:
            assert rail in rails, rail
    for category in FailureCategory:
        assert category in categories, category


def test_every_category_has_a_base_propensity() -> None:
    for category in FailureCategory:
        assert category in BASE_RECOVERY_PROPENSITY, category


@pytest.mark.parametrize("base", [0.0, 0.05, 0.5, 0.95, 1.0])
def test_treated_propensity_never_exceeds_one(base: float) -> None:
    treated = treated_propensity(base)
    assert base <= treated <= 1.0


def test_fingerprint_reports_the_scored_events() -> None:
    rows = build_benchmark_events(size=36, seed=42)
    fp = dataset_fingerprint(rows)
    assert fp["dataset_version"] == BENCHMARK_DATASET_VERSION
    assert fp["event_count"] == 36
    assert fp["total_at_risk_paise"] == sum(r.event.amount_paise for r in rows)
    assert fp["first_payment_id"] == rows[0].event.payment_id


def test_rejects_non_positive_size() -> None:
    with pytest.raises(ValueError, match="positive"):
        build_benchmark_events(size=0)


@pytest.mark.anyio
async def test_benchmark_run_reports_both_arms() -> None:
    run = await run_benchmark(size=60, seed=555, use_llm=False)

    assert run.treatment.case_count > 0
    assert run.holdout.case_count > 0
    assert run.treatment.case_count + run.holdout.case_count == 60
    assert run.replay_failures_count == 0


@pytest.mark.anyio
async def test_benchmark_shows_positive_lift_over_holdout() -> None:
    """The treated arm must beat the untouched counterfactual."""
    run = await run_benchmark(size=200, seed=808, use_llm=False)

    assert run.treatment.recovery_rate_pct > run.holdout.recovery_rate_pct
    assert run.lift_pct_points > 0


@pytest.mark.anyio
async def test_attributable_recovery_is_net_of_the_counterfactual() -> None:
    """Attributable money must be less than gross, or the holdout is ignored."""
    run = await run_benchmark(size=720, seed=909, use_llm=False)

    assert run.counterfactual_recovered_paise > 0
    assert run.attributable_recovered_paise < run.treatment.recovered_paise
    payload = run.as_dict()
    assert payload["dataset"]["dataset_version"] == BENCHMARK_DATASET_VERSION
    assert payload["seed"] == 909


@pytest.mark.anyio
async def test_small_batch_refuses_to_claim_attribution() -> None:
    """A batch too small for per-category controls must not quote a figure: scaling
    a 3-case rate onto a large treatment base produced a negative one before.
    """
    run = await run_benchmark(size=60, seed=4242, use_llm=False)
    assert run.is_attribution_reliable is False
    assert run.counterfactual_coverage_pct < 60.0


@pytest.mark.anyio
async def test_large_batch_reports_reliable_positive_attribution() -> None:
    run = await run_benchmark(size=1200, seed=20260902, use_llm=False)
    assert run.is_attribution_reliable is True
    assert run.attributable_recovered_paise > 0


@pytest.mark.anyio
async def test_report_is_written_and_states_its_verdict(tmp_path: Path) -> None:
    run = await run_benchmark(size=1200, seed=20260902, use_llm=False)
    path = write_report(run, docs_dir=tmp_path)

    assert path.exists()
    body = path.read_text(encoding="utf-8")
    assert run.run_id in body
    assert "## Verdict" in body
    assert "Attribution is defensible" in body
    assert "modelling assumptions, not measured" in body
    assert "| TREATMENT |" in body and "| HOLDOUT_CONTROL |" in body


@pytest.mark.anyio
async def test_report_refuses_to_quote_a_figure_when_coverage_is_low(
    tmp_path: Path,
) -> None:
    run = await run_benchmark(size=60, seed=4242, use_llm=False)
    body = write_report(run, docs_dir=tmp_path).read_text(encoding="utf-8")

    assert "No attributable money figure is quoted" in body
    assert "Attributable recovery: **" not in body


@pytest.mark.anyio
async def test_repeat_run_replays_rather_than_being_deduped() -> None:
    """A rerun must score the events again, not be absorbed by idempotency."""
    repo = get_case_repository()
    repo.clear()
    try:
        first = await run_benchmark(size=120, seed=777, use_llm=False)
        after_first = len(repo.list_cases(limit=9000))
        second = await run_benchmark(size=120, seed=777, use_llm=False)
        after_second = len(repo.list_cases(limit=9000))

        assert after_second > after_first, "second run was deduped away"
        # Same seed must still produce identical arm results.
        assert first.as_dict()["treatment"] == second.as_dict()["treatment"]
        assert first.lift_pct_points == second.lift_pct_points
    finally:
        repo.clear()


@pytest.mark.anyio
async def test_holdout_share_follows_the_live_policy() -> None:
    """Arm assignment must read the persisted policy, not a construction-time copy."""
    repo = get_case_repository()
    repo.clear()
    original = get_active_policy()
    try:
        set_active_policy(MerchantPolicy(holdout_percentage=0))
        none_held = await run_benchmark(size=200, seed=61, use_llm=False)
        assert none_held.holdout.case_count == 0

        set_active_policy(MerchantPolicy(holdout_percentage=30))
        many_held = await run_benchmark(size=200, seed=61, use_llm=False)
        assert many_held.holdout.case_count > 40
    finally:
        set_active_policy(original)
        repo.clear()


@pytest.mark.anyio
async def test_holdout_is_never_contacted_or_charged() -> None:
    """The counterfactual is void if the control arm receives any outreach."""
    run = await run_benchmark(size=400, seed=20260902, use_llm=False)

    assert run.holdout.touches == 0
    assert run.holdout.cost_paise == 0
    assert run.holdout.escalated_count == 0


@pytest.mark.anyio
async def test_http_run_does_not_write_a_report_by_default(
    client: TestClient, tmp_path: Path
) -> None:
    """Reports are opt-in over HTTP so routine runs do not litter docs/."""
    before = set(tmp_path.iterdir())
    res = client.post("/api/benchmark/run", params={"size": 40, "seed": 5})
    assert res.status_code == 200
    assert "report_path" not in res.json()
    assert set(tmp_path.iterdir()) == before


def test_cli_writes_a_report_and_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.benchmark.cli.write_report",
        lambda run: write_report(run, docs_dir=tmp_path),
    )
    code = cli_main(["--size", "80", "--seed", "13"])
    assert code == 0
    assert list((tmp_path / "benchmarks").glob("*.md"))


def test_cli_can_skip_the_report(tmp_path: Path) -> None:
    code = cli_main(["--size", "40", "--seed", "14", "--no-report"])
    assert code == 0
    assert not list(tmp_path.glob("**/*.md"))
