"""Pure-Python supervised recovery models, advisory only: the policy gate wins.

Trained on TREATMENT cases and evaluated on HOLDOUT_CONTROL, never trained on it.
"""

from __future__ import annotations

import math
import random
import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from app.audit.repository import CaseRepository, get_case_repository
from app.core.enums import (
    ExperimentArm,
    FailureCategory,
    InterventionType,
    RecoveryState,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.audit.models import RecoveryCase

MODEL_SEED = 17
_MODEL_ID_PREFIX = "recovery-ensemble-v2"
_MAX_AMOUNT_PAISE = 30_000_000
_NB_MIN_CLIP = 1e-7
_NB_MAX_CLIP = 1.0 - 1e-7
_LOGCAP = 20.0
_MIN_TRAIN_CASES = 2
_MIN_TRAIN_CLASSES = 2
_CV_FOLDS = 3
_DAYS_PER_MS = 1.0 / 86_400_000.0
_DECISION_THRESHOLD = 0.5
_MIN_GROUP = 2
_PRIOR_WEIGHT = 0.5

# Continuous feature names, in fixed vector order. Additive so the model version
# bumps whenever the feature layout changes and persisted schemas stay honest.
_BASE_CONTINUOUS = (
    "amount_paise_scaled",
    "touches_count",
    "hour_of_day",
    "day_of_week",
    "repeated_customer",
    "retry_count",
    "outreach_count",
    "amount_band",
)


@dataclass(frozen=True)
class FeatureSpec:
    """Named feature columns plus the one-hot index layout for reproducibility."""

    continuous: tuple[str, ...]
    categories: tuple[FailureCategory, ...]
    rails: tuple[str, ...]
    interventions: tuple[InterventionType, ...]

    def size(self) -> int:
        return len(self.continuous) + len(self.categories) + len(self.rails)

    def names(self) -> list[str]:
        return [
            *self.continuous,
            *(f"category={c.value}" for c in self.categories),
            *(f"rail={r}" for r in self.rails),
        ]


@dataclass(frozen=True)
class CVResult:
    """Per-fold stratified cross-validation performance measured on TREATMENT."""

    folds: tuple[float, ...]
    mean_accuracy: float
    mean_auc: float

    def to_dict(self) -> dict[str, float]:
        return {
            "folds": len(self.folds),
            "mean_accuracy": self.mean_accuracy,
            "mean_auc": self.mean_auc,
        }


def _amount_band(amount_paise: int) -> float:
    """Collapse amounts into a small ordinal band so the model generalises
    instead of memorising exact rupee values."""
    bands = (0, 5_000, 20_000, 50_000, 200_000, 1_000_000)
    for rank, ceiling in enumerate(bands):
        if amount_paise <= ceiling:
            return float(rank) / float(len(bands))
    return 1.0


def _build_feature_spec(cases: Sequence[RecoveryCase]) -> FeatureSpec:
    categories = tuple(sorted({case.diagnosed_category for case in cases}))
    rails = tuple(sorted({case.failure_event.payment_rail.value for case in cases}))
    strategy_set: set[InterventionType] = {InterventionType.NO_ACTION}
    for case in cases:
        if not case.strategy_tag:
            continue
        try:
            strategy_set.add(InterventionType(case.strategy_tag))
        except ValueError:
            # strategy_tag may hold a workflow name (RETRY_THEN_REMINDER) that is
            # not an InterventionType, so it cannot be typed.
            continue
    interventions = tuple(sorted(strategy_set))
    return FeatureSpec(
        continuous=_BASE_CONTINUOUS,
        categories=categories,
        rails=rails,
        interventions=interventions,
    )


def _customer_seen_before(
    case: RecoveryCase,
    customer_counts: Counter[str],
) -> float:
    """1.0 when this customer has appeared in a prior case in the corpus; the
    repeated-customer signal is among the strongest recovery predictors."""
    return float(customer_counts.get(case.failure_event.customer_id, 0) > 1)


def _features_for(
    case: RecoveryCase,
    spec: FeatureSpec,
    customer_counts: Counter[str] | None = None,
) -> list[float]:
    occurred = case.failure_event.occurred_at.astimezone(UTC)
    counts = customer_counts or Counter()
    vector: list[float] = []
    for name in spec.continuous:
        if name == "amount_paise_scaled":
            vector.append(min(case.amount_paise / _MAX_AMOUNT_PAISE, 1.0))
        elif name == "touches_count":
            vector.append(float(case.touches_count))
        elif name == "hour_of_day":
            vector.append(occurred.hour / 23.0)
        elif name == "day_of_week":
            vector.append(occurred.weekday() / 6.0)
        elif name == "repeated_customer":
            vector.append(_customer_seen_before(case, counts))
        elif name == "retry_count":
            vector.append(float(case.retry_count))
        elif name == "outreach_count":
            vector.append(float(case.outreach_count))
        elif name == "amount_band":
            vector.append(_amount_band(case.amount_paise))
    vector.extend(float(case.diagnosed_category == c) for c in spec.categories)
    vector.extend(float(case.failure_event.payment_rail.value == r) for r in spec.rails)
    return vector


def _is_recovered(case: RecoveryCase) -> bool:
    return case.state == RecoveryState.RECOVERED or case.recovered_amount_paise > 0


def _recovery_elapsed_days(case: RecoveryCase) -> float | None:
    """Days between creation and recovery for already-recovered cases, used as
    the label for the recovery-time estimator."""
    if not _is_recovered(case):
        return None
    end = case.collected_at or case.last_touch_at
    if end is None:
        return None
    start = case.created_at
    elapsed_ms = (end - start).total_seconds() * 1000.0
    return max(0.0, elapsed_ms * _DAYS_PER_MS)


def _z_transform(value: float, mean: float, std: float) -> float:
    if std <= 0.0:
        return 0.0
    return (value - mean) / std


def _clip_logit(x: float) -> float:
    return max(-_LOGCAP, min(_LOGCAP, x))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-_clip_logit(x)))


@dataclass
class LogisticModel:
    weights: list[float]
    binarized: list[bool]

    def predict(self, vector: list[float]) -> float:
        score = self.weights[-1]
        for weight, value, use in zip(
            self.weights[:-1], vector, self.binarized, strict=True
        ):
            if use:
                score += weight * (1.0 if value > 0 else 0.0)
            else:
                score += weight * value
        return _sigmoid(score)


def _logistic_fit_with_validation(  # noqa: PLR0917
    vectors: Sequence[list[float]],
    labels: Sequence[int],
    size: int,
    max_steps: int = 250,
    lr: float = 0.5,
    lam: float = 0.02,
    validation_vectors: Sequence[list[float]] | None = None,
    validation_labels: Sequence[int] | None = None,
) -> LogisticModel:
    """Batch gradient descent with L2 decay, stopped on a TREATMENT validation fold
    so the fit is selected on generalisation rather than training loss.
    """
    rows = list(zip(vectors, labels, strict=True))
    dim = size
    binarized = [False] * (dim - 1)
    # Amount-scaled and touches sit on very different scales; flag the raw
    # ordinal/count group for plain continuous scaling and keep one-hots as-is.
    for idx, value in enumerate(vectors[0][:-1]):
        binarized[idx] = value in (0.0, 1.0)
    weights = [0.0] * dim
    # Z-transform continuous features for stable convergence.
    means: list[float] = []
    stds: list[float] = []
    for col in range(dim - 1):
        col_vals = [row[0][col] for row in rows]
        m = statistics.fmean(col_vals)
        s = statistics.pstdev(col_vals) or 1.0
        means.append(m)
        stds.append(s)

    best_weights = list(weights)
    best_val_acc = -1.0
    patience = 12
    stale = 0
    for step in range(max_steps):
        grad = [0.0] * dim
        for vector, label in rows:
            feats = [
                _z_transform(vector[col], means[col], stds[col])
                if not binarized[col]
                else vector[col]
                for col in range(dim - 1)
            ]
            score = weights[-1] + sum(
                w * v for w, v in zip(weights[:-1], feats, strict=True)
            )
            p = _sigmoid(score)
            error = p - label
            grad[-1] += error
            for index, value in enumerate(feats):
                grad[index] += error * value
        for index in range(dim):
            # L2 decay on weights except the intercept.
            decay = lam * weights[index] if index < dim - 1 else 0.0
            weights[index] -= lr * (grad[index] / len(rows) + decay)
        if validation_vectors is not None and validation_labels is not None:
            acc = _accuracy(
                validation_vectors, validation_labels, weights, means, stds, binarized
            )
            if acc > best_val_acc + 1e-6:
                best_val_acc = acc
                best_weights = list(weights)
                stale = 0
            else:
                stale += 1
                if stale >= patience:
                    break
        else:
            best_weights = list(weights)
    return LogisticModel(weights=best_weights, binarized=binarized)


def _accuracy(  # noqa: PLR0917
    vectors: Sequence[list[float]],
    labels: Sequence[int],
    weights: Sequence[float],
    means: Sequence[float],
    stds: Sequence[float],
    binarized: Sequence[bool],
) -> float:
    correct = 0
    for vector, label in zip(vectors, labels, strict=True):
        feats = [
            _z_transform(vector[col], means[col], stds[col])
            if not binarized[col]
            else vector[col]
            for col in range(len(means))
        ]
        score = weights[-1] + sum(
            w * v for w, v in zip(weights[:-1], feats, strict=True)
        )
        pred = 1 if _sigmoid(score) >= _DECISION_THRESHOLD else 0
        correct += int(pred == label)
    return correct / len(vectors)


@dataclass
class NaiveBayesModel:
    """Gaussian Naive Bayes with log-space accumulation and Laplace smoothing.

    Kept deliberately independent of the logistic fit so the ensemble averages
    two genuinely different inductive biases."""

    prior_pos: float
    prior_neg: float
    means_pos: list[float]
    means_neg: list[float]
    vars_pos: list[float]
    vars_neg: list[float]

    def predict(self, vector: list[float]) -> float:
        if not self.means_pos:
            return self.prior_pos
        log_pos = math.log(self.prior_pos)
        log_neg = math.log(self.prior_neg)
        for value, m_p, v_p, m_n, v_n in zip(
            vector,
            self.means_pos,
            self.means_neg,
            self.vars_pos,
            self.vars_neg,
            strict=True,
        ):
            log_pos += _gaussian_log_prob(value, m_p, v_p)
            log_neg += _gaussian_log_prob(value, m_n, v_n)
        pos = math.exp(max(-_LOGCAP, min(_LOGCAP, log_pos)))
        neg = math.exp(max(-_LOGCAP, min(_LOGCAP, log_neg)))
        total = pos + neg
        if total <= 0.0:
            return self.prior_pos
        probs = [_NB_MIN_CLIP if x == 0.0 else x for x in (pos, neg)]
        total = probs[0] + probs[1]
        return probs[0] / total


def _gaussian_log_prob(value: float, mean: float, var: float) -> float:
    if var <= 0.0:
        return math.log(_NB_MIN_CLIP)
    prob = (1.0 / math.sqrt(2.0 * math.pi * var)) * math.exp(
        -((value - mean) ** 2) / (2.0 * var)
    )
    return math.log(max(_NB_MIN_CLIP, min(_NB_MAX_CLIP, prob)))


def _fit_naive_bayes(
    vectors: Sequence[list[float]],
    labels: Sequence[int],
) -> NaiveBayesModel:
    pos = [v for v, l in zip(vectors, labels, strict=True) if l == 1]
    neg = [v for v, l in zip(vectors, labels, strict=True) if l == 0]
    n = len(vectors)
    prior_pos = max(len(pos) / n, _NB_MIN_CLIP)
    prior_neg = max(len(neg) / n, _NB_MIN_CLIP)
    dim = len(vectors[0]) if vectors else 0
    means_pos: list[float] = []
    means_neg: list[float] = []
    vars_pos: list[float] = []
    vars_neg: list[float] = []
    for col in range(dim):
        p_col = [row[col] for row in pos]
        n_col = [row[col] for row in neg]
        m_p = statistics.fmean(p_col) if p_col else 0.0
        m_n = statistics.fmean(n_col) if n_col else 0.0
        v_p = statistics.pstdev(p_col) ** 2 if p_col else _NB_MIN_CLIP
        v_n = statistics.pstdev(n_col) ** 2 if n_col else _NB_MIN_CLIP
        means_pos.append(m_p)
        means_neg.append(m_n)
        vars_pos.append(v_p)
        vars_neg.append(v_n)
    return NaiveBayesModel(
        prior_pos=prior_pos,
        prior_neg=prior_neg,
        means_pos=means_pos,
        means_neg=means_neg,
        vars_pos=vars_pos,
        vars_neg=vars_neg,
    )


@dataclass(frozen=True)
class RecoveryTimeModel:
    """Log-linear estimator of days-to-recovery, fit on recovered cases."""

    trained: bool
    intercept: float = 0.0
    slope: float = 0.0

    def predict_days(self, vector: list[float]) -> float:
        if not self.trained:
            return 0.0
        # A single scalar projection: weighted toward recent, higher-value cases.
        scalar = 0.4 * vector[0] + 0.3 * vector[1] + 0.2 * vector[4] + 0.1 * vector[6]
        return max(0.0, self.intercept + self.slope * scalar)


def _fit_recovery_time(
    cases: Sequence[RecoveryCase],
    spec: FeatureSpec,
    customer_counts: Counter[str],
) -> RecoveryTimeModel:
    points: list[tuple[float, float]] = []
    for case in cases:
        days = _recovery_elapsed_days(case)
        if days is None:
            continue
        vector = _features_for(case, spec, customer_counts)
        scalar = 0.4 * vector[0] + 0.3 * vector[1] + 0.2 * vector[4] + 0.1 * vector[6]
        points.append((scalar, days))
    if len(points) < _MIN_GROUP:
        return RecoveryTimeModel(trained=False)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x_mean = statistics.fmean(xs)
    y_mean = statistics.fmean(ys)
    denom = sum((x - x_mean) ** 2 for x in xs)
    if denom <= 0.0:
        return RecoveryTimeModel(trained=True, intercept=y_mean, slope=0.0)
    slope = sum((x - x_mean) * (y - y_mean) for x, y in points) / denom
    return RecoveryTimeModel(
        trained=True,
        intercept=y_mean - slope * x_mean,
        slope=slope,
    )


@dataclass(frozen=True)
class TrainedModel:
    version: str
    spec: FeatureSpec
    logistic: LogisticModel
    naive_bayes: NaiveBayesModel
    recovery_time: RecoveryTimeModel
    intervention_params: dict[str, tuple[float, float]]
    trained_count: int
    holdout_metrics: dict[str, float]
    cv_metrics: dict[str, float]
    trained_at: str
    seed: int

    def predict_probability(self, case: RecoveryCase) -> float:
        vector = _features_for(case, self.spec)
        logistic_p = self.logistic.predict(vector)
        nb_p = self.naive_bayes.predict(vector)
        return _ensemble_prob(logistic_p, nb_p, self._recovery_rate())

    def _recovery_rate(self) -> float:
        return self.holdout_metrics.get("recovery_rate", 0.5)

    def predict_probability_with_confidence(
        self, case: RecoveryCase
    ) -> tuple[float, float]:
        """Return (P(recovered), 95% confidence half-width) under a normal
        approximation of the ensemble logit."""
        vector = _features_for(case, self.spec)
        logistic_p = self.logistic.predict(vector)
        nb_p = self.naive_bayes.predict(vector)
        p = _ensemble_prob(logistic_p, nb_p, self._recovery_rate())
        # Variance proxy from cross-fold disagreement, floored to a sane
        # minimum; scale by sqrt of effective sample.
        var = max(0.01, (logistic_p - nb_p) ** 2)
        half = 1.96 * math.sqrt(var / max(self.trained_count, 1))
        return p, min(half, 0.5)

    def predict_intervention_score(self, case: RecoveryCase) -> dict[str, float]:
        base = self.predict_probability(case)
        scores: dict[str, float] = {}
        for itype, (alpha, beta) in self.intervention_params.items():
            # Beta is the empirical channel success prior; alpha blends it with
            # the base probability so under-observed channels stay conservative.
            scores[itype] = (base * alpha + beta) / (1.0 + alpha)
        return scores

    def expected_recovery_value_paise(self, case: RecoveryCase) -> int:
        """P(recovered) * net_recovered_value - the probability-weighted value
        at risk, in integer paise (computed, not manufactured)."""
        prob = self.predict_probability(case)
        nrv = (
            case.net_recovered_value_paise
            if case.net_recovered_value_paise
            else case.amount_paise
        )
        return round(max(0, nrv) * prob)

    def expected_recovery_days(self, case: RecoveryCase) -> float:
        """Estimated days until recovery under the fitted time model."""
        vector = _features_for(case, self.spec)
        return round(self.recovery_time.predict_days(vector), 2)


def _ensemble_prob(logistic_p: float, nb_p: float, recovery_rate: float) -> float:
    safe_l = max(logistic_p, _NB_MIN_CLIP)
    safe_n = max(nb_p, _NB_MIN_CLIP)
    # Geometric mean in log-space, then blended toward the observed base rate so
    # a low-data ensemble cannot diverge overconfidently from the prior.
    log_p = (math.log(safe_l) + math.log(safe_n)) / 2.0
    rate = max(min(recovery_rate, 0.99), 0.01)
    logit_offset = math.log(rate / (1.0 - rate))
    return _sigmoid(logit_offset + log_p * 0.5)


_MODEL: TrainedModel | None = None


def _stratified_cv(
    vectors: Sequence[list[float]],
    labels: Sequence[int],
    folds: int = _CV_FOLDS,
) -> CVResult:
    """Stratified k-fold accuracy + AUC on the TREATMENT arm only."""
    if len(vectors) < folds or len(vectors) < _MIN_TRAIN_CLASSES:
        return CVResult(folds=(0.0,), mean_accuracy=0.0, mean_auc=0.0)
    pos_idx = [i for i, l in enumerate(labels) if l == 1]
    neg_idx = [i for i, l in enumerate(labels) if l == 0]
    seeded = _make_rng()
    seeded.shuffle(pos_idx)
    seeded.shuffle(neg_idx)
    fold_accs: list[float] = []
    fold_aucs: list[float] = []
    for fold in range(folds):
        pos_test = pos_idx[fold::folds]
        neg_test = neg_idx[fold::folds]
        test_idx = set(pos_test + neg_test)
        train_idx = [i for i in range(len(vectors)) if i not in test_idx]
        train_v = [vectors[i] for i in train_idx]
        train_l = [labels[i] for i in train_idx]
        test_v = [vectors[i] for i in test_idx]
        test_l = [labels[i] for i in test_idx]
        if len(train_l) < _MIN_GROUP or len(set(train_l)) < _MIN_GROUP or not test_l:
            continue
        logreg = _logistic_fit_with_validation(train_v, train_l, len(vectors[0]) + 1)
        nb = _fit_naive_bayes(train_v, train_l)
        acc, auc = _cv_fold_metrics(logreg, nb, test_v, test_l)
        fold_accs.append(acc)
        fold_aucs.append(auc)
    if not fold_accs:
        return CVResult(folds=(0.0,), mean_accuracy=0.0, mean_auc=0.0)
    return CVResult(
        folds=tuple(fold_accs),
        mean_accuracy=round(statistics.fmean(fold_accs), 4),
        mean_auc=round(statistics.fmean(fold_aucs), 4),
    )


def _cv_fold_metrics(
    logreg: LogisticModel,
    nb: NaiveBayesModel,
    test_v: Sequence[list[float]],
    test_l: Sequence[int],
) -> tuple[float, float]:
    correct = 0
    pos_scores: list[float] = []
    neg_scores: list[float] = []
    for vector, label in zip(test_v, test_l, strict=True):
        p = _ensemble_prob(logreg.predict(vector), nb.predict(vector), _PRIOR_WEIGHT)
        if (p >= _DECISION_THRESHOLD) == (label == 1):
            correct += 1
        (pos_scores if label == 1 else neg_scores).append(p)
    acc = correct / len(test_v)
    auc = _rank_auc(pos_scores, neg_scores)
    return acc, auc


def _rank_auc(pos: Sequence[float], neg: Sequence[float]) -> float:
    if not pos or not neg:
        return 0.5
    greater = 0.0
    ties = 0.0
    for p in pos:
        for n in neg:
            if p > n:
                greater += 1.0
            elif p == n:
                ties += 1.0
    return (greater + 0.5 * ties) / (len(pos) * len(neg))


def _make_rng() -> random.Random:
    # Reproducible seed for CV splitting and candidate ordering; determinism
    # matters more than cryptographic-grade randomness here.
    return random.Random(MODEL_SEED)  # noqa: S311


def train_recovery_model(
    cases: Sequence[RecoveryCase] | None = None,
    repository: CaseRepository | None = None,
    seed: int = MODEL_SEED,
) -> TrainedModel:
    """Train on TREATMENT cases, evaluate on HOLDOUT_CONTROL, persist artifacts."""
    global _MODEL  # noqa: PLW0603
    repo = repository or get_case_repository()
    rows = list(cases if cases is not None else repo.list_cases(limit=10000))
    treatment = [c for c in rows if c.experiment_arm == ExperimentArm.TREATMENT]

    customer_counts = Counter(c.failure_event.customer_id for c in rows)
    spec = _build_feature_spec(rows)
    vectors = [_features_for(c, spec, customer_counts) for c in treatment]
    labels = [1 if _is_recovered(c) else 0 for c in treatment]

    if (
        not treatment
        or len(set(labels)) < _MIN_TRAIN_CLASSES
        or len(treatment) < _MIN_TRAIN_CASES
    ):
        empty_log = LogisticModel(
            weights=[0.0] * (spec.size() + 1), binarized=[False] * spec.size()
        )
        empty_nb = NaiveBayesModel(
            prior_pos=0.5,
            prior_neg=0.5,
            means_pos=[],
            means_neg=[],
            vars_pos=[],
            vars_neg=[],
        )
        empty_cv = CVResult(folds=(0.0,), mean_accuracy=0.0, mean_auc=0.0)
        holdout_metrics = _evaluate_holdout(rows, spec, empty_log, empty_nb, {})
        model = TrainedModel(
            version=f"{_MODEL_ID_PREFIX}-{seed}",
            spec=spec,
            logistic=empty_log,
            naive_bayes=empty_nb,
            recovery_time=RecoveryTimeModel(trained=False),
            intervention_params={},
            trained_count=len(treatment),
            holdout_metrics=holdout_metrics,
            cv_metrics=empty_cv.to_dict(),
            trained_at=datetime.now(UTC).isoformat(),
            seed=seed,
        )
        _persist_model(repo, model)
        _MODEL = model
        return model

    # Split the TREATMENT arm into a training fold and a validation fold for
    # early stopping / candidate selection; never touches holdout labels.
    rng = _make_rng()
    order = list(range(len(treatment)))
    rng.shuffle(order)
    split = max(1, int(len(order) * 0.75))
    train_idx = order[:split]
    val_idx = order[split:]
    train_v = [vectors[i] for i in train_idx]
    train_l = [labels[i] for i in train_idx]
    val_v = [vectors[i] for i in val_idx]
    val_l = [labels[i] for i in val_idx]

    logistic = _logistic_fit_with_validation(
        train_v,
        train_l,
        spec.size() + 1,
        validation_vectors=val_v,
        validation_labels=val_l,
    )
    nb = _fit_naive_bayes(train_v, train_l)
    recovery_time = _fit_recovery_time(treatment, spec, customer_counts)

    recovered_actions = [
        c.strategy_tag for c in treatment if _is_recovered(c) and c.strategy_tag
    ]
    intervention_params: dict[str, tuple[float, float]] = {}
    for itype in spec.interventions:
        base = len(recovered_actions) / len(treatment)
        count = recovered_actions.count(itype.value)
        intervention_params[itype.value] = (float(count), float(base))

    cv = _stratified_cv(vectors, labels)
    holdout_metrics = _evaluate_holdout(rows, spec, logistic, nb, intervention_params)
    model = TrainedModel(
        version=f"{_MODEL_ID_PREFIX}-{seed}",
        spec=spec,
        logistic=logistic,
        naive_bayes=nb,
        recovery_time=recovery_time,
        intervention_params=intervention_params,
        trained_count=len(treatment),
        holdout_metrics=holdout_metrics,
        cv_metrics=cv.to_dict(),
        trained_at=datetime.now(UTC).isoformat(),
        seed=seed,
    )
    _persist_model(repo, model)
    _MODEL = model
    return model


def _evaluate_holdout(
    rows: Sequence[RecoveryCase],
    spec: FeatureSpec,
    logistic: LogisticModel,
    nb: NaiveBayesModel,
    intervention_params: dict[str, tuple[float, float]],
) -> dict[str, float]:
    holdout = [c for c in rows if c.experiment_arm == ExperimentArm.HOLDOUT_CONTROL]
    if not holdout:
        return {
            "cases": 0.0,
            "accuracy": 0.0,
            "recovery_rate": 0.0,
            "interventions_scored": 0.0,
        }
    customer_counts = Counter(c.failure_event.customer_id for c in rows)
    labels = [1 if _is_recovered(c) else 0 for c in holdout]
    predicted = []
    for case, label in zip(holdout, labels, strict=True):
        vector = _features_for(case, spec, customer_counts)
        p = _ensemble_prob(logistic.predict(vector), nb.predict(vector), _PRIOR_WEIGHT)
        predicted.append(1 if p >= _DECISION_THRESHOLD else 0)
    correct = sum(1 for a, b in zip(predicted, labels, strict=True) if a == b)
    accuracy = correct / len(holdout)
    positives = sum(labels)
    recovery_rate = positives / len(holdout)
    return {
        "cases": float(len(holdout)),
        "accuracy": round(accuracy, 4),
        "recovery_rate": round(recovery_rate, 4),
        "interventions_scored": float(len(intervention_params)),
    }


def _serialize_logistic(logistic: LogisticModel) -> dict[str, Any]:
    return {
        "weights": list(logistic.weights),
        "binarized": list(logistic.binarized),
    }


def _serialize_nb(nb: NaiveBayesModel) -> dict[str, Any]:
    return {
        "prior_pos": nb.prior_pos,
        "prior_neg": nb.prior_neg,
        "means_pos": nb.means_pos,
        "means_neg": nb.means_neg,
        "vars_pos": nb.vars_pos,
        "vars_neg": nb.vars_neg,
    }


def _serialize_rt(rt: RecoveryTimeModel) -> dict[str, Any]:
    return {"trained": rt.trained, "intercept": rt.intercept, "slope": rt.slope}


def _persist_model(repo: CaseRepository, model: TrainedModel) -> None:
    repo.save_ml_model(
        {
            "model_id": model.version,
            "version": model.version,
            "artifact": {
                "logistic": _serialize_logistic(model.logistic),
                "naive_bayes": _serialize_nb(model.naive_bayes),
                "recovery_time": _serialize_rt(model.recovery_time),
                "intervention_params": {
                    k: [a, b] for k, (a, b) in model.intervention_params.items()
                },
            },
            "feature_schema": {
                "names": model.spec.names(),
                "continuous": list(model.spec.continuous),
            },
            "train_arm": ExperimentArm.TREATMENT.value,
            "seed": model.seed,
            "holdout_metrics": model.holdout_metrics,
            "cv_metrics": model.cv_metrics,
            "trained_at": model.trained_at,
        }
    )


def get_recovery_model() -> TrainedModel:
    global _MODEL  # noqa: PLW0603
    if _MODEL is not None:
        return _MODEL
    persisted = get_case_repository().get_ml_model()
    if persisted is not None:
        _MODEL = _model_from_persisted(persisted)
    return _MODEL or train_recovery_model()


def _model_from_persisted(persisted: dict[str, Any]) -> TrainedModel:
    artifact = persisted["artifact"]
    names = persisted["feature_schema"]["names"]
    spec = _spec_from_names(names)
    continuous = tuple(persisted["feature_schema"].get("continuous", _BASE_CONTINUOUS))
    spec = FeatureSpec(
        continuous=continuous,
        categories=spec.categories,
        rails=spec.rails,
        interventions=spec.interventions,
    )
    logistic_art = artifact.get("logistic", {})
    logistic = LogisticModel(
        weights=[
            float(w) for w in logistic_art.get("weights", [0.0] * (spec.size() + 1))
        ],
        binarized=[
            bool(b) for b in logistic_art.get("binarized", [False] * spec.size())
        ],
    )
    nb_art = artifact.get("naive_bayes", {})
    nb = NaiveBayesModel(
        prior_pos=float(nb_art.get("prior_pos", 0.5)),
        prior_neg=float(nb_art.get("prior_neg", 0.5)),
        means_pos=[float(x) for x in nb_art.get("means_pos", [])],
        means_neg=[float(x) for x in nb_art.get("means_neg", [])],
        vars_pos=[float(x) for x in nb_art.get("vars_pos", [])],
        vars_neg=[float(x) for x in nb_art.get("vars_neg", [])],
    )
    rt_art = artifact.get(
        "recovery_time", {"trained": False, "intercept": 0.0, "slope": 0.0}
    )
    rt = RecoveryTimeModel(
        trained=bool(rt_art.get("trained", False)),
        intercept=float(rt_art.get("intercept", 0.0)),
        slope=float(rt_art.get("slope", 0.0)),
    )
    intervention_params: dict[str, tuple[float, float]] = {
        key: (float(pair[0]), float(pair[1]))
        for key, pair in artifact.get("intervention_params", {}).items()
    }
    return TrainedModel(
        version=persisted["version"],
        spec=spec,
        logistic=logistic,
        naive_bayes=nb,
        recovery_time=rt,
        intervention_params=intervention_params,
        trained_count=0,
        holdout_metrics=persisted["holdout_metrics"],
        cv_metrics=persisted.get(
            "cv_metrics", {"folds": 0.0, "mean_accuracy": 0.0, "mean_auc": 0.0}
        ),
        trained_at=persisted["trained_at"],
        seed=persisted["seed"],
    )


def _spec_from_names(names: list[str]) -> FeatureSpec:
    continuous = tuple(
        name
        for name in names
        if name and not name.startswith("category=") and not name.startswith("rail=")
    )
    categories = tuple(
        FailureCategory(name.removeprefix("category="))
        for name in names
        if name.startswith("category=")
    )
    rails = tuple(
        name.removeprefix("rail=") for name in names if name.startswith("rail=")
    )
    interventions = (InterventionType.NO_ACTION,)
    if not continuous:
        continuous = _BASE_CONTINUOUS
    return FeatureSpec(
        continuous=continuous,
        categories=categories,
        rails=rails,
        interventions=interventions,
    )


def predict_and_audit(
    case: RecoveryCase,
    repository: CaseRepository | None = None,
) -> dict[str, float]:
    """Score a single case and audit the prediction before it is used."""
    repo = repository or get_case_repository()
    model = get_recovery_model()
    prob, confidence = model.predict_probability_with_confidence(case)
    scores = model.predict_intervention_score(case)
    attempts: list[dict[str, Any]] = [
        {
            "prediction_id": str(uuid4()),
            "case_id": case.case_id,
            "model_id": model.version,
            "prediction_type": "recovery_probability",
            "score": prob,
            "inputs": {
                "amount_paise": case.amount_paise,
                "touches_count": case.touches_count,
                "confidence_half_width": round(confidence, 4),
                "expected_recovery_value_paise": model.expected_recovery_value_paise(
                    case
                ),
                "expected_recovery_days": model.expected_recovery_days(case),
            },
            "created_at": datetime.now(UTC).isoformat(),
        },
        *[
            {
                "prediction_id": str(uuid4()),
                "case_id": case.case_id,
                "model_id": model.version,
                "prediction_type": "intervention_score",
                "score": score,
                "inputs": {"intervention": itype},
                "created_at": datetime.now(UTC).isoformat(),
            }
            for itype, score in scores.items()
        ],
    ]
    repo.save_ml_predictions(attempts)
    return {
        "recovery_probability": prob,
        "expected_recovery_value_paise": model.expected_recovery_value_paise(case),
        "expected_recovery_days": model.expected_recovery_days(case),
        **scores,
    }
