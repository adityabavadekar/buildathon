"""Fixed benchmark dataset: for a given (dataset_version, seed, size) the events
are byte-identical, timestamps included, so runs months apart stay comparable.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from app.core.enums import FailureCategory
from app.core.identifiers import RUN_TAG_SEPARATOR
from app.detection.models import RawFailureEvent
from app.simulation.seeder import CAMPAIGN_TAGS, CUSTOMER_NAMES, FAILURE_TEMPLATES

if TYPE_CHECKING:
    from collections.abc import Sequence

BENCHMARK_DATASET_VERSION = "fortx-bench-v1"
DEFAULT_BENCHMARK_SEED = 20260902
# Sized so every category clears MIN_CONTROL_CASES_PER_STRATUM at a 10% holdout.
# At 720 the thinnest strata fell under the floor and coverage dropped to 8%, so
# the harness correctly refused to attribute anything.
DEFAULT_BENCHMARK_SIZE = 1200

# Anchored so timestamps do not drift with wall-clock time between runs.
BENCHMARK_EPOCH = datetime(2026, 8, 1, 0, 0, 0, tzinfo=UTC)
BENCHMARK_WINDOW_MINUTES = 20160

# Modelling assumptions, not measured rates: no public dataset says whether a
# given failed payment later recovered. They set difficulty, not the verdict.
BASE_RECOVERY_PROPENSITY: dict[FailureCategory, float] = {
    FailureCategory.TRANSIENT_BANK_WINDOW: 0.42,
    FailureCategory.LIQUIDITY_CONSTRAINT: 0.18,
    FailureCategory.STRUCTURAL_MANDATE_FAILURE: 0.08,
    FailureCategory.CHECKOUT_DROP_OFF: 0.31,
    FailureCategory.B2B_RECEIVABLES_OVERDUE: 0.22,
    FailureCategory.PROMISE_TO_PAY_DELAY: 0.35,
    FailureCategory.SYSTEMIC_GATEWAY_FAILURE: 0.46,
    # An unknown outcome is often an authorization that already succeeded, so the
    # untreated rate is high; the agent adds little beyond reconciling it.
    FailureCategory.INDETERMINATE_AUTHORIZATION: 0.55,
    FailureCategory.UNCLASSIFIED: 0.05,
}

# How much a correct, executed intervention improves on the base rate. Expressed
# as a multiplier on the remaining headroom so it can never exceed 1.0.
TREATMENT_UPLIFT_SHARE = 0.38

# Partial captures exist in the dataset so the report exercises the
# recovered-less-than-at-risk accounting path.
PARTIAL_CAPTURE_SHARE = 0.18
PARTIAL_CAPTURE_FLOOR_BPS = 4000
PARTIAL_CAPTURE_CEILING_BPS = 9000


@dataclass(frozen=True)
class BenchmarkEvent:
    """One dataset row: the event to replay plus its ground-truth outcome."""

    event: RawFailureEvent
    category: FailureCategory
    base_propensity: float
    # Drawn once per row so arm assignment cannot change the coin flip.
    outcome_roll: float
    capture_roll: float
    partial_bps: int


def _iso_id(prefix: str, rng: random.Random, run_tag: str | None = None) -> str:
    # The tag is a suffix so stable_payment_key can recover the untagged id and
    # keep arm assignment identical across runs.
    body = f"{rng.getrandbits(56):014x}"
    if run_tag is None:
        return f"{prefix}{body}"
    return f"{prefix}{body}{RUN_TAG_SEPARATOR}{run_tag}"


def build_benchmark_events(
    *,
    size: int = DEFAULT_BENCHMARK_SIZE,
    seed: int = DEFAULT_BENCHMARK_SEED,
    run_tag: str | None = None,
) -> list[BenchmarkEvent]:
    """Materialise the dataset. Categories cycle so the mix holds across sizes, and
    run_tag namespaces ids or idempotency absorbs a repeat run and measures nothing.
    """
    if size <= 0:
        msg = "Benchmark size must be positive"
        raise ValueError(msg)

    rng = random.Random(seed)  # noqa: S311 - reproducibility, not cryptography
    rows: list[BenchmarkEvent] = []

    for index in range(size):
        template = FAILURE_TEMPLATES[index % len(FAILURE_TEMPLATES)]
        customer = CUSTOMER_NAMES[rng.randrange(len(CUSTOMER_NAMES))]
        amount_options: Sequence[int] = template["amounts"]
        amount = amount_options[rng.randrange(len(amount_options))]
        category: FailureCategory = template["category"]

        occurred_at = BENCHMARK_EPOCH + timedelta(
            minutes=rng.randrange(BENCHMARK_WINDOW_MINUTES)
        )
        error_code = str(template["error_code"])

        event = RawFailureEvent(
            event_id=_iso_id("evt_bench_", rng, run_tag),
            payment_id=_iso_id("pay_bench_", rng, run_tag),
            # Namespaced per run like payment_id: cooldown is scoped to the
            # customer, so a shared id would let one run's outreach suppress the
            # next run's and break replay determinism.
            customer_id=(
                customer[0]
                if run_tag is None
                else f"{customer[0]}{RUN_TAG_SEPARATOR}{run_tag}"
            ),
            amount_paise=amount,
            currency="INR",
            payment_rail=template["rail"],
            error_code=error_code,
            error_description=str(template["error_reason"]),
            error_reason=str(template["error_reason"]),
            npci_response_code=error_code
            if error_code.startswith("AP") or error_code == "XT"
            else None,
            occurred_at=occurred_at,
            campaign_id=CAMPAIGN_TAGS[rng.randrange(len(CAMPAIGN_TAGS))],
            contact_email=customer[2],
            contact_phone=customer[1],
            experiment_tag=BENCHMARK_DATASET_VERSION,
            metadata={
                "source": "benchmark",
                "dataset_version": BENCHMARK_DATASET_VERSION,
                "row_index": index,
                "run_tag": run_tag,
            },
        )

        rows.append(
            BenchmarkEvent(
                event=event,
                category=category,
                base_propensity=BASE_RECOVERY_PROPENSITY.get(category, 0.10),
                outcome_roll=rng.random(),
                capture_roll=rng.random(),
                partial_bps=rng.randrange(
                    PARTIAL_CAPTURE_FLOOR_BPS, PARTIAL_CAPTURE_CEILING_BPS
                ),
            )
        )

    return rows


def treated_propensity(base: float) -> float:
    """Return the recovery propensity once an intervention has been executed."""
    return base + (1.0 - base) * TREATMENT_UPLIFT_SHARE


def dataset_fingerprint(rows: Sequence[BenchmarkEvent]) -> dict[str, Any]:
    """Summarise a dataset so a report can prove which events it scored."""
    by_category: dict[str, int] = {}
    by_rail: dict[str, int] = {}
    total_paise = 0
    for row in rows:
        by_category[row.category.value] = by_category.get(row.category.value, 0) + 1
        rail = row.event.payment_rail.value
        by_rail[rail] = by_rail.get(rail, 0) + 1
        total_paise += row.event.amount_paise

    return {
        "dataset_version": BENCHMARK_DATASET_VERSION,
        "event_count": len(rows),
        "total_at_risk_paise": total_paise,
        "first_payment_id": rows[0].event.payment_id if rows else None,
        "last_payment_id": rows[-1].event.payment_id if rows else None,
        "category_mix": dict(sorted(by_category.items())),
        "rail_mix": dict(sorted(by_rail.items())),
    }
