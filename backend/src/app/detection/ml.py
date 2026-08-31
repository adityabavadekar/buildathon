"""Small deterministic recovery probability model using treatment cases only."""

from __future__ import annotations

import math
from collections.abc import Sequence  # noqa: TC003
from dataclasses import dataclass

from app.audit.models import RecoveryCase  # noqa: TC001
from app.audit.repository import get_case_repository
from app.core.enums import ExperimentArm, RecoveryState


@dataclass(frozen=True)
class RecoveryModel:
    version: str
    intercept: float
    weight_amount: float
    weight_touches: float
    trained_count: int

    def predict(self, case: RecoveryCase) -> float:
        score = self.intercept + self.weight_amount * min(case.amount_paise / 1_000_000, 10.0)
        score += self.weight_touches * case.touches_count
        return 1.0 / (1.0 + math.exp(-max(-20.0, min(20.0, score))))


_MODEL: RecoveryModel | None = None


def train_recovery_model(cases: Sequence[RecoveryCase] | None = None) -> RecoveryModel:
    global _MODEL  # noqa: PLW0603
    rows = list(cases or get_case_repository().list_cases(limit=10000))
    treatment = [case for case in rows if case.experiment_arm == ExperimentArm.TREATMENT]
    if not treatment:
        _MODEL = RecoveryModel("recovery-logistic-v1", -2.0, 0.0, 0.0, 0)
        return _MODEL
    positives = sum(case.state == RecoveryState.RECOVERED or case.recovered_amount_paise > 0 for case in treatment)
    rate = (positives + 1) / (len(treatment) + 2)
    _MODEL = RecoveryModel("recovery-logistic-v1", math.log(rate / (1 - rate)), 0.0, 0.0, len(treatment))
    return _MODEL


def get_recovery_model() -> RecoveryModel:
    return _MODEL or train_recovery_model()
