"""Benchmark execution and reporting API."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.audit.global_log import record_global_audit
from app.benchmark.dataset import (
    BENCHMARK_DATASET_VERSION,
    DEFAULT_BENCHMARK_SEED,
    DEFAULT_BENCHMARK_SIZE,
    build_benchmark_events,
    dataset_fingerprint,
)
from app.benchmark.report import write_report
from app.benchmark.runner import run_benchmark
from app.core.constants import DEFAULT_CURRENCY
from app.core.enums import AuditActor
from app.core.logging import get_logger

router = APIRouter(prefix="/benchmark", tags=["benchmark"])

logger = get_logger("api.benchmark")

MAX_BENCHMARK_SIZE = 1000


class BenchmarkDatasetResponse(BaseModel):
    """Fingerprint of the fixed dataset, without replaying it."""

    dataset_version: str
    event_count: int
    total_at_risk_paise: int
    first_payment_id: str | None
    last_payment_id: str | None
    category_mix: dict[str, int]
    rail_mix: dict[str, int]


@router.get(
    "/dataset",
    response_model=BenchmarkDatasetResponse,
    summary="Describe The Fixed Benchmark Dataset",
)
async def get_benchmark_dataset(
    size: Annotated[int, Query(ge=1, le=MAX_BENCHMARK_SIZE)] = DEFAULT_BENCHMARK_SIZE,
    seed: Annotated[int, Query()] = DEFAULT_BENCHMARK_SEED,
) -> BenchmarkDatasetResponse:
    """Return the dataset fingerprint so a report can cite what it scored."""
    rows = build_benchmark_events(size=size, seed=seed)
    return BenchmarkDatasetResponse.model_validate(dataset_fingerprint(rows))


@router.post("/run", summary="Run The Benchmark And Score Against Holdout")
async def post_benchmark_run(
    size: Annotated[int, Query(ge=1, le=MAX_BENCHMARK_SIZE)] = DEFAULT_BENCHMARK_SIZE,
    seed: Annotated[int, Query()] = DEFAULT_BENCHMARK_SEED,
    use_llm: Annotated[bool, Query()] = False,
    write_markdown: Annotated[bool, Query()] = False,
) -> dict[str, Any]:
    """Replay the fixed dataset through the engine and report measured lift.

    Writes a system audit row so a published figure can be traced to the run
    that produced it.
    """
    run = await run_benchmark(size=size, seed=seed, use_llm=use_llm)
    payload = run.as_dict()

    if write_markdown:
        payload["report_path"] = str(write_report(run))

    record_global_audit(
        event_name="benchmark.completed",
        actor=AuditActor.SYSTEM,
        reason=(
            f"Benchmark {BENCHMARK_DATASET_VERSION} scored {size} events "
            f"at seed {seed}."
        ),
        notes=(
            f"Lift {run.lift_pct_points} pct points; attributable "
            f"{DEFAULT_CURRENCY} {run.attributable_recovered_paise / 100:,.2f}."
        ),
        decision_inputs={
            "run_id": run.run_id,
            "dataset_version": BENCHMARK_DATASET_VERSION,
            "seed": seed,
            "size": size,
            "use_llm": use_llm,
        },
        decision_outputs={
            "lift_pct_points": run.lift_pct_points,
            "attributable_recovered_paise": run.attributable_recovered_paise,
            "treatment_recovery_rate_pct": run.treatment.recovery_rate_pct,
            "holdout_recovery_rate_pct": run.holdout.recovery_rate_pct,
        },
    )
    return payload
