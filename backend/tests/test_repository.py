"""Tests for CaseRepository persistence, deduplication, and filtering."""

from datetime import UTC, datetime

from app.audit.models import RecoveryCase
from app.audit.repository import CaseRepository
from app.core.enums import ExperimentArm, RecoveryState
from app.detection.models import RawFailureEvent


def _make_case(case_id: str, payment_id: str, state: RecoveryState = RecoveryState.IN_DUNNING) -> RecoveryCase:
    event = RawFailureEvent(
        event_id=f"evt_{payment_id}",
        payment_id=payment_id,
        customer_id=f"cust_{case_id}",
        amount_paise=100000,
        error_code="BAD_REQUEST_ERROR",
        occurred_at=datetime.now(UTC),
    )
    return RecoveryCase(
        case_id=case_id,
        state=state,
        amount_paise=100000,
        failure_event=event,
    )


def test_repository_save_and_retrieve_by_various_keys() -> None:
    repo = CaseRepository()
    case = _make_case("case_1", "pay_1")

    repo.save(case, idempotency_key="idem_1")

    assert repo.get_by_id("case_1") == case
    assert repo.get_by_payment_id("pay_1") == case
    assert repo.get_by_idempotency_key("idem_1") == case
    assert repo.get_by_id("non_existent") is None


def test_repository_list_and_filter() -> None:
    repo = CaseRepository()
    case1 = _make_case("case_1", "pay_1", state=RecoveryState.IN_DUNNING)
    case2 = _make_case("case_2", "pay_2", state=RecoveryState.RECOVERED)
    case3 = _make_case("case_3", "pay_3", state=RecoveryState.ESCALATED)
    case3.experiment_arm = ExperimentArm.HOLDOUT_CONTROL

    repo.save(case1)
    repo.save(case2)
    repo.save(case3)

    all_cases = repo.list_cases(limit=10)
    assert len(all_cases) == 3

    recovered_cases = repo.list_cases(state=RecoveryState.RECOVERED)
    assert len(recovered_cases) == 1
    assert recovered_cases[0].case_id == "case_2"

    holdout_cases = repo.list_cases(experiment_arm=ExperimentArm.HOLDOUT_CONTROL)
    assert len(holdout_cases) == 1
    assert holdout_cases[0].case_id == "case_3"

    assert repo.count() == 3
    assert repo.count(state=RecoveryState.IN_DUNNING) == 1
