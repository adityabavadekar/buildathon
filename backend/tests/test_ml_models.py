"""Tests for the pure-Python supervised recovery models and holdout discipline."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.audit.models import RecoveryCase
from app.audit.repository import CaseRepository
from app.core.enums import (
    ExperimentArm,
    FailureCategory,
    InterventionType,
    PaymentRail,
    RecoveryState,
)
from app.detection.ml import (
    predict_and_audit,
    train_recovery_model,
)
from app.detection.models import RawFailureEvent
from app.intervention.models import InterventionPlan
from app.intervention.policy_gate import PolicyGate


def make_case(
    index: int,
    arm: ExperimentArm = ExperimentArm.TREATMENT,
    recovered: bool = True,
    strategy_tag: str = "SMART_RETRY",
) -> RecoveryCase:
    occurred_at = datetime(2026, 2, 1, tzinfo=UTC) + timedelta(hours=index)
    return RecoveryCase(
        case_id=f"ml-case-{index}",
        amount_paise=20000 + index * 500,
        currency="INR",
        experiment_arm=arm,
        state=RecoveryState.RECOVERED if recovered else RecoveryState.IN_DUNNING,
        recovered_amount_paise=20000 if recovered else 0,
        attempts_count=0,
        diagnosed_category=FailureCategory.LIQUIDITY_CONSTRAINT,
        strategy_tag=strategy_tag,
        failure_event=RawFailureEvent(
            event_id=f"ml-event-{index}",
            payment_id=f"ml-payment-{index}",
            customer_id=f"ml-customer-{index % 3}",
            amount_paise=20000 + index * 500,
            currency="INR",
            payment_rail=PaymentRail.UPI,
            error_code="U30",
            occurred_at=occurred_at,
        ),
    )


def test_training_is_deterministic(tmp_path: Path) -> None:
    repo = CaseRepository(storage_path=tmp_path / "ml.db")
    cases = [make_case(index) for index in range(10)]
    first = train_recovery_model(cases, repository=repo, seed=17)
    second = train_recovery_model(cases, repository=repo, seed=17)
    assert first.logistic.weights == second.logistic.weights
    assert first.naive_bayes.prior_pos == second.naive_bayes.prior_pos
    assert first.holdout_metrics == second.holdout_metrics
    sample = cases[0]
    assert first.predict_probability(sample) == second.predict_probability(sample)


def test_train_uses_treatment_only_and_evaluates_on_holdout(tmp_path: Path) -> None:
    repo = CaseRepository(storage_path=tmp_path / "ml.db")
    cases = [make_case(index) for index in range(10)]
    cases += [
        make_case(index, arm=ExperimentArm.HOLDOUT_CONTROL) for index in range(20, 24)
    ]
    model = train_recovery_model(cases, repository=repo, seed=17)
    assert model.trained_count == 10  # only TREATMENT cases were trained on
    assert model.holdout_metrics["cases"] == 4  # evaluated on HOLDOUT_CONTROL only
    persist = repo.get_ml_model()
    assert persist is not None
    assert persist["train_arm"] == ExperimentArm.TREATMENT.value


def test_holdout_labels_never_reach_fitter_directly(tmp_path: Path) -> None:
    repo = CaseRepository(storage_path=tmp_path / "ml.db")
    treatment = [make_case(index) for index in range(8)]
    holdout = [
        make_case(index, arm=ExperimentArm.HOLDOUT_CONTROL) for index in range(30, 38)
    ]
    model = train_recovery_model([*treatment, *holdout], repository=repo, seed=17)
    assert model.trained_count == len(treatment)
    assert set(model.holdout_metrics) == {
        "cases",
        "accuracy",
        "recovery_rate",
        "interventions_scored",
    }


def test_model_score_cannot_override_policy_gate(tmp_path: Path) -> None:
    repo = CaseRepository(storage_path=tmp_path / "ml.db")
    cases = [make_case(index) for index in range(10)]
    cases += [
        make_case(index, arm=ExperimentArm.HOLDOUT_CONTROL, recovered=True)
        for index in range(20, 24)
    ]
    train_recovery_model(cases, repository=repo, seed=17)
    holdout_case = next(
        c for c in cases if c.experiment_arm == ExperimentArm.HOLDOUT_CONTROL
    )

    scores = predict_and_audit(holdout_case, repository=repo)
    assert scores["recovery_probability"] >= 0.0

    plan = InterventionPlan(
        plan_id="p-1",
        case_id=holdout_case.case_id,
        intervention_type=InterventionType.SMART_RETRY,
        scheduled_at=datetime.now(UTC),
        idempotency_key="ik-1",
        rationale="advisory model says recoverable",
    )
    gate = PolicyGate()
    evaluation = gate.evaluate(holdout_case, plan)
    # A holdout case is always blocked regardless of any model score.
    assert evaluation.is_allowed is False


def test_amounts_remain_integer_paise(tmp_path: Path) -> None:
    repo = CaseRepository(storage_path=tmp_path / "ml.db")
    cases = [make_case(index) for index in range(10)]
    train_recovery_model(cases, repository=repo, seed=17)
    persist = repo.get_ml_model()
    assert persist is not None
    weights = persist["artifact"]["logistic"]["weights"]
    assert all(isinstance(w, (int, float)) for w in weights)
    for case in cases:
        assert isinstance(case.amount_paise, int)
        assert case.amount_paise > 0


def test_predict_and_audit_persists_predictions(tmp_path: Path) -> None:
    repo = CaseRepository(storage_path=tmp_path / "ml.db")
    cases = [make_case(index) for index in range(10)]
    cases += [
        make_case(index, arm=ExperimentArm.HOLDOUT_CONTROL) for index in range(20, 24)
    ]
    train_recovery_model(cases, repository=repo, seed=17)
    target = cases[0]
    scores = predict_and_audit(target, repository=repo)
    assert "recovery_probability" in scores
    assert scores["recovery_probability"] >= 0.0
    persisted_model = repo.get_ml_model()
    assert persisted_model is not None
    assert persisted_model["train_arm"] == ExperimentArm.TREATMENT.value


def test_strategy_tag_that_is_not_intervention_does_not_crash(tmp_path: Path) -> None:
    """Workflow strategy tags (e.g. RETRY_THEN_REMINDER) are not InterventionType
    members and must not break feature-spec training."""
    repo = CaseRepository(storage_path=tmp_path / "ml.db")
    cases = [make_case(index, strategy_tag="RETRY_THEN_REMINDER") for index in range(6)]
    cases += [make_case(index, strategy_tag="SMART_RETRY") for index in range(6, 12)]
    model = train_recovery_model(cases, repository=repo, seed=17)
    assert model.trained_count == len(cases)
    # Only valid InterventionType values become scored interventions.
    assert all(
        key in {it.value for it in InterventionType}
        for key in model.intervention_params
    )


def test_ensemble_outputs_expected_recovery_value_and_days(tmp_path: Path) -> None:
    repo = CaseRepository(storage_path=tmp_path / "ml.db")
    cases = [make_case(index) for index in range(12)]
    cases += [
        make_case(index, arm=ExperimentArm.HOLDOUT_CONTROL, recovered=False)
        for index in range(20, 26)
    ]
    model = train_recovery_model(cases, repository=repo, seed=17)

    target = cases[0]
    prob = model.predict_probability(target)
    assert 0.0 <= prob <= 1.0

    erv = model.expected_recovery_value_paise(target)
    assert isinstance(erv, int)
    # ERV cannot exceed the full recoverable amount.
    assert 0 <= erv <= target.amount_paise

    days = model.expected_recovery_days(target)
    assert days >= 0.0

    p, conf = model.predict_probability_with_confidence(target)
    assert 0.0 <= p <= 1.0
    assert 0.0 <= conf <= 0.5


def test_cv_metrics_recorded_on_treatment_only(tmp_path: Path) -> None:
    repo = CaseRepository(storage_path=tmp_path / "ml.db")
    cases = [make_case(index, recovered=index % 2 == 0) for index in range(12)]
    cases += [
        make_case(index, arm=ExperimentArm.HOLDOUT_CONTROL) for index in range(20, 26)
    ]
    model = train_recovery_model(cases, repository=repo, seed=17)
    assert "mean_accuracy" in model.cv_metrics
    assert "mean_auc" in model.cv_metrics


def test_repeated_customer_is_a_learned_feature(tmp_path: Path) -> None:
    repo = CaseRepository(storage_path=tmp_path / "ml.db")
    # Three distinct customers; one appears in many cases (repeating payer).
    cases = []
    for index in range(9):
        customer = (
            "ml-customer-a"
            if index < 6
            else ("ml-customer-b" if index < 8 else "ml-customer-c")
        )
        cases.append(
            RecoveryCase(
                case_id=f"rep-case-{index}",
                amount_paise=20000,
                currency="INR",
                experiment_arm=ExperimentArm.TREATMENT,
                state=RecoveryState.RECOVERED
                if index < 6
                else RecoveryState.IN_DUNNING,
                recovered_amount_paise=20000 if index < 6 else 0,
                diagnosed_category=FailureCategory.LIQUIDITY_CONSTRAINT,
                strategy_tag="SMART_RETRY",
                failure_event=RawFailureEvent(
                    event_id=f"rep-event-{index}",
                    payment_id=f"rep-payment-{index}",
                    customer_id=customer,
                    amount_paise=20000,
                    currency="INR",
                    payment_rail=PaymentRail.UPI,
                    error_code="U30",
                    occurred_at=datetime(2026, 2, 1, tzinfo=UTC)
                    + timedelta(hours=index),
                ),
            )
        )
    model = train_recovery_model(cases, repository=repo, seed=17)
    # The feature must be part of the persisted schema.
    assert "repeated_customer" in model.spec.names()
    # The training corpus produced both classes, so a real fit happened.
    assert model.trained_count == len(cases)
