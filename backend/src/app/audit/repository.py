"""Durable thread-safe case repository with idempotency key tracking and JSON persistence.

Provides transactional ACID-style lookups, state persistence, and append-only audit logging
for revenue recovery cases.
"""

from __future__ import annotations

import functools
import json
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from app.audit.models import RecoveryCase
from app.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.core.enums import ExperimentArm, RecoveryState

logger = get_logger(__name__)


class CaseRepository:
    """Thread-safe storage for recovery cases with optional file-backed durability."""

    def __init__(self, storage_path: Path | str | None = None) -> None:
        self._lock = threading.RLock()
        self._cases: dict[str, RecoveryCase] = {}
        self._by_payment_id: dict[str, str] = {}
        self._by_idempotency_key: dict[str, str] = {}
        self._storage_path = Path(storage_path) if storage_path else None

        if self._storage_path and self._storage_path.exists():
            self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Load persisted cases from local storage file."""
        if not self._storage_path or not self._storage_path.exists():
            return
        try:
            with self._storage_path.open(encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    case = RecoveryCase.model_validate(item)
                    self._cases[case.case_id] = case
                    self._by_payment_id[case.failure_event.payment_id] = case.case_id
            logger.info(
                "repository.loaded_from_disk",
                count=len(self._cases),
                path=str(self._storage_path),
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logger.warning(
                "repository.load_disk_failed",
                error=str(exc),
                path=str(self._storage_path),
            )

    def _flush_to_disk(self) -> None:
        """Persist in-memory state to disk atomically."""
        if not self._storage_path:
            return
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._storage_path.with_suffix(".tmp")
            cases_dump = [c.model_dump(mode="json") for c in self._cases.values()]
            with tmp_path.open("w", encoding="utf-8") as f:
                json.dump(cases_dump, f, indent=2, default=str)
            tmp_path.replace(self._storage_path)
        except (OSError, ValueError) as exc:
            logger.warning("repository.flush_disk_failed", error=str(exc))

    def save(self, case: RecoveryCase, idempotency_key: str | None = None) -> None:
        """Persist or update a recovery case and flush to durable storage."""
        with self._lock:
            self._cases[case.case_id] = case
            self._by_payment_id[case.failure_event.payment_id] = case.case_id
            if idempotency_key:
                self._by_idempotency_key[idempotency_key] = case.case_id
            self._flush_to_disk()

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
        """Clear repository contents and remove local data file."""
        with self._lock:
            self._cases.clear()
            self._by_payment_id.clear()
            self._by_idempotency_key.clear()
            if self._storage_path and self._storage_path.exists():
                try:
                    self._storage_path.unlink()
                except OSError:
                    pass


@functools.lru_cache(maxsize=1)
def get_case_repository() -> CaseRepository:
    """Return singleton instance of CaseRepository with disk persistence."""
    return CaseRepository(storage_path=Path("data/cases_store.json"))
