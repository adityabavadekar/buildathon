"""Comprehensive tests for recovery strategy experiments and incremental rupee attribution."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.audit.models import RecoveryCase
from app.audit.repository import get_case_repository
from app.core.enums import ExperimentArm, PaymentRail, RecoveryState
from app.detection.models import RawFailureEvent

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def test_strategy_experiments_report(client: TestClient) -> None:
    """Verify strategy experiments endpoint reports gross, net, incremental value, and ROI."""
    repo = get_case_repository()
    now = datetime.now(UTC)

    # 1. Seed holdout control baseline
    h_case = RecoveryCase(
        case_id="case_strat_h1",
        merchant_id="merch_1",
        state=RecoveryState.RECOVERED,
        experiment_arm=ExperimentArm.HOLDOUT_CONTROL,
        amount_paise=100000,
        recovered_amount_paise=100000,
        currency="INR",
        failure_event=RawFailureEvent(
            event_id="evt_h1",
            payment_id="pay_h1",
            customer_id="cust_h1",
            amount_paise=100000,
            currency="INR",
            payment_rail=PaymentRail.UPI,
            error_code="U30",
            occurred_at=now,
        ),
    )
    repo.save(h_case)

    # 2. Seed treatment case with explicit strategy_tag
    t_case = RecoveryCase(
        case_id="case_strat_t1",
        merchant_id="merch_1",
        state=RecoveryState.RECOVERED,
        experiment_arm=ExperimentArm.TREATMENT,
        strategy_tag="RETRY_THEN_REMINDER",
        amount_paise=300000,
        recovered_amount_paise=300000,
        currency="INR",
        retry_count=1,
        outreach_count=1,
        failure_event=RawFailureEvent(
            event_id="evt_t1",
            payment_id="pay_t1",
            customer_id="cust_t1",
            amount_paise=300000,
            currency="INR",
            payment_rail=PaymentRail.UPI,
            error_code="U30",
            occurred_at=now,
        ),
    )
    t_case.recompute_nrv()
    repo.save(t_case)

    # 3. Query strategy experiments endpoint
    res = client.get("/api/experiments/strategies")
    assert res.status_code == 200
    strats = res.json()
    assert isinstance(strats, list)

    s1 = next((s for s in strats if s["strategy_tag"] == "RETRY_THEN_REMINDER"), None)
    assert s1 is not None
    assert s1["cohort_size"] >= 1
    assert s1["gross_recovered_paise"] >= 300000
    assert "incremental_recovered_paise" in s1
    assert "return_on_spend" in s1
