"""Tests for deterministic, descriptive recovery pattern clustering."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.audit.models import RecoveryCase
from app.audit.repository import CaseRepository
from app.core.enums import ExperimentArm, FailureCategory, PaymentRail, RecoveryState
from app.detection.clustering import recompute_patterns
from app.detection.models import RawFailureEvent


def make_case(index: int, customer_id: str = "customer") -> RecoveryCase:
    occurred_at = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=index)
    return RecoveryCase(
        case_id=f"case-{index}",
        amount_paise=10000 + index * 100,
        currency="INR",
        experiment_arm=ExperimentArm.TREATMENT,
        state=RecoveryState.RECOVERED if index % 2 == 0 else RecoveryState.IN_DUNNING,
        recovered_amount_paise=10000 if index % 2 == 0 else 0,
        diagnosed_category=FailureCategory.LIQUIDITY_CONSTRAINT,
        strategy_tag="SMART_RETRY",
        failure_event=RawFailureEvent(
            event_id=f"event-{index}",
            payment_id=f"payment-{index}",
            customer_id=customer_id,
            amount_paise=10000 + index * 100,
            currency="INR",
            payment_rail=PaymentRail.UPI,
            error_code="U30",
            error_reason="funds",
            occurred_at=occurred_at,
        ),
    )


def test_clustering_is_deterministic_and_persists(tmp_path: Path) -> None:
    repo = CaseRepository(storage_path=tmp_path / "patterns.db")
    cases = [make_case(index, f"customer-{index % 2}") for index in range(4)]
    first = recompute_patterns(cases, seed=19, repository=repo)
    second = recompute_patterns(cases, seed=19, repository=repo)
    assert [
        {
            key: value
            for key, value in item.items()
            if key not in {"alert_id", "run_id", "created_at"}
        }
        for item in first
    ] == [
        {
            key: value
            for key, value in item.items()
            if key not in {"alert_id", "run_id", "created_at"}
        }
        for item in second
    ]
    persisted = repo.list_pattern_alerts()
    assert all(
        item["dominant_category"] == FailureCategory.LIQUIDITY_CONSTRAINT.value
        for item in persisted
    )
    assert {item["dominant_intervention"] for item in persisted} == {
        "SMART_RETRY",
        "NO_ACTION",
    }


def test_clustering_handles_empty_single_and_same_customer_without_mutation(
    tmp_path: Path,
) -> None:
    repo = CaseRepository(storage_path=tmp_path / "patterns.db")
    assert recompute_patterns([], repository=repo) == []
    assert len(recompute_patterns([make_case(0)], repository=repo)) == 1
    cases = [make_case(1), make_case(2), make_case(3)]
    before = [case.model_dump(mode="json") for case in cases]
    alerts = recompute_patterns(cases, repository=repo)
    assert len(alerts) == len(cases)
    assert [case.model_dump(mode="json") for case in cases] == before
    assert all(case.experiment_arm == ExperimentArm.TREATMENT for case in cases)
