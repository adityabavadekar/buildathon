"""Detection and contextual classification domain."""

from app.detection.classifier import FailureClassifier, classify_failure
from app.detection.models import DiagnosisResult, RawFailureEvent

__all__ = [
    "DiagnosisResult",
    "FailureClassifier",
    "RawFailureEvent",
    "classify_failure",
]
