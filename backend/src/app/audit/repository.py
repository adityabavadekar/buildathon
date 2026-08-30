"""In-memory thread-safe case repository with idempotency key tracking.

Provides transactional ACID-style lookups, state persistence, and audit logging
for revenue recovery cases.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.audit.models import RecoveryCase
    from app.core.enums import ExperimentArm, RecoveryState


class CaseRepository:
    """Thread-safe storage for recovery cases and idempotency deduplication."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cases: dict[str, RecoveryCase] = {}
        self._by_payment_id: dict[str, str] = {}
        self._by_idempotency_key: dict[str, str] = {}

    def save(self, case: RecoveryCase, idempotency_key: str | None = None) -> None:
        """Persist or update a recovery case."""
        with self._lock:
            self._cases[case.case_id] = case
            self._by_payment_id[case.failure_event.payment_id] = case.case_id
            if idempotency_key:
                self._by_idempotency_key[idempotency_key] = case.case_id

    def get_by_id(self, case_id: str) -> RecoveryCase | None:
        """Retrieve a case by unique case ID."""
        with self._lock:
            return self._cases.get(case_id)

    def get_by_payment_id(self, payment_id: str) -> RecoveryCase | None:
        """Retrieve a case by the originating gateway payment ID."""
        with self._lock:
            case_id = self._by_payment_id.get(payment_id)
            return self._cases.get(case_id) if case_id else None

    def get_by_idempotency_key(self, idempotency_key: str) -> RecoveryCase | None:
        """Retrieve a case by idempotency key to prevent duplicate processing."""
        with self._lock:
            case_id = self._by_idempotency_key.get(idempotency_key)
            return self._cases.get(case_id) if case_id else None

    def list_cases(
        self,
        *,
        merchant_id: str | None = None,
        state: RecoveryState | None = None,
        experiment_arm: ExperimentArm | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[RecoveryCase]:
        """List cases matching query filters with pagination."""
        with self._lock:
            results = list(self._cases.values())

            if merchant_id:
                results = [c for c in results if c.merchant_id == merchant_id]
            if state:
                results = [c for c in results if c.state == state]
            if experiment_arm:
                results = [c for c in results if c.experiment_arm == experiment_arm]

            # Sort by created_at descending (newest first)
            results.sort(key=lambda c: c.created_at, reverse=True)
            return results[offset : offset + limit]

    def count(
        self,
        *,
        merchant_id: str | None = None,
        state: RecoveryState | None = None,
        experiment_arm: ExperimentArm | None = None,
    ) -> int:
        """Count total cases matching query filters."""
        with self._lock:
            results = list(self._cases.values())
            if merchant_id:
                results = [c for c in results if c.merchant_id == merchant_id]
            if state:
                results = [c for c in results if c.state == state]
            if experiment_arm:
                results = [c for c in results if c.experiment_arm == experiment_arm]
            return len(results)

    def clear(self) -> None:
        """Clear repository contents (useful for test fixtures)."""
        with self._lock:
            self._cases.clear()
            self._by_payment_id.clear()
            self._by_idempotency_key.clear()


# Process-wide repository singleton instance
_GLOBAL_REPOSITORY = CaseRepository()


def get_case_repository() -> CaseRepository:
    """Return the process-wide case repository instance."""
    return _GLOBAL_REPOSITORY
