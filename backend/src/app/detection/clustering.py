"""Deterministic descriptive K-means pattern alerts for recovery cases."""

from __future__ import annotations

import random
from collections import Counter
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from app.audit.repository import CaseRepository, get_case_repository
from app.core.enums import InterventionType

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.audit.models import RecoveryCase

CLUSTER_SEED = 731
FEATURE_SCOPE = (
    "amount_paise,category,payment_rail,hour_of_day,day_of_week,repeated_customer"
)


def _features(cases: Sequence[RecoveryCase]) -> list[list[float]]:
    customers = Counter(case.failure_event.customer_id for case in cases)
    categories = sorted({case.diagnosed_category.value for case in cases})
    rails = sorted({case.failure_event.payment_rail.value for case in cases})
    vectors: list[list[float]] = []
    for case in cases:
        occurred = case.failure_event.occurred_at.astimezone(UTC)
        category = case.diagnosed_category.value
        vector = [float(case.amount_paise)]
        vector.extend(float(category == item) for item in categories)
        vector.extend(
            float(case.failure_event.payment_rail.value == item) for item in rails
        )
        vector.extend(
            [
                float(occurred.hour),
                float(occurred.weekday()),
                float(customers[case.failure_event.customer_id] > 1),
            ]
        )
        vectors.append(vector)
    return vectors


def _scale(rows: list[list[float]]) -> list[list[float]]:
    if not rows:
        return []
    mins = [min(row[index] for row in rows) for index in range(len(rows[0]))]
    maxs = [max(row[index] for row in rows) for index in range(len(rows[0]))]
    return [
        [
            0.0
            if maxs[index] == mins[index]
            else (value - mins[index]) / (maxs[index] - mins[index])
            for index, value in enumerate(row)
        ]
        for row in rows
    ]


def _distance(left: list[float], right: list[float]) -> float:
    return sum((a - b) ** 2 for a, b in zip(left, right, strict=True))


def recompute_patterns(
    cases: Sequence[RecoveryCase] | None = None,
    seed: int = CLUSTER_SEED,
    repository: CaseRepository | None = None,
) -> list[dict[str, Any]]:
    repo = repository or get_case_repository()
    rows = list(cases or repo.list_cases(limit=10000))
    if not rows:
        return []
    scaled = _scale(_features(rows))
    k = min(5, len(rows))
    rng = random.Random(seed)  # noqa: S311
    centers = [scaled[index] for index in rng.sample(range(len(scaled)), k)]
    assignments = [0] * len(rows)
    for _ in range(30):
        assignments = [
            min(range(k), key=lambda cluster: _distance(vector, centers[cluster]))
            for vector in scaled
        ]
        next_centers = []
        for cluster in range(k):
            scaled_members = [
                scaled[index]
                for index, assigned in enumerate(assignments)
                if assigned == cluster
            ]
            next_centers.append(
                centers[cluster]
                if not scaled_members
                else [
                    sum(row[col] for row in scaled_members) / len(scaled_members)
                    for col in range(len(scaled[0]))
                ]
            )
        if next_centers == centers:
            break
        centers = next_centers
    run_id = str(uuid4())
    now = datetime.now(UTC).isoformat()
    alerts: list[dict[str, Any]] = []
    for cluster in range(k):
        members = [
            case for index, case in enumerate(rows) if assignments[index] == cluster
        ]
        if not members:
            continue
        category = Counter(
            case.diagnosed_category.value for case in members
        ).most_common(1)[0][0]
        recovered_actions = [
            case.strategy_tag
            for case in members
            if case.recovered_amount_paise > 0 and case.strategy_tag
        ]
        intervention = (
            Counter(recovered_actions).most_common(1)[0][0]
            if recovered_actions
            else InterventionType.NO_ACTION.value
        )
        alerts.append(
            {
                "alert_id": str(uuid4()),
                "run_id": run_id,
                "seed": seed,
                "feature_scope": FEATURE_SCOPE,
                "dominant_category": category,
                "dominant_intervention": intervention,
                "member_count": len(members),
                "mean_amount_paise": sum(case.amount_paise for case in members)
                // len(members),
                "example_case_ids": [case.case_id for case in members[:5]],
                "created_at": now,
            }
        )
    repo.save_pattern_alerts(alerts)
    return alerts
