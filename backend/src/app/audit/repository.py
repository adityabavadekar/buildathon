"""Relational case repository: transactional lookups, state persistence, and
append-only audit logging.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any

from app.audit.postgres_store import RelationalCaseStore
from app.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime
    from pathlib import Path

    from app.audit.models import ModelTelemetryEntry, RecoveryCase, ScheduledJob
    from app.core.enums import ExperimentArm, RecoveryState

logger = get_logger(__name__)


class CaseRepository:
    """Thread-safe, transaction-backed repository for recovery cases, audit trails, and scheduled jobs."""

    def __init__(self, storage_path: Path | str | None = None) -> None:
        self._store = RelationalCaseStore(db_path=storage_path)

    def save(self, case: RecoveryCase, idempotency_key: str | None = None) -> None:
        """Persist or update a recovery case and flush to durable storage."""
        self._store.save_case(case, idempotency_key=idempotency_key)

    def get_by_id(self, case_id: str) -> RecoveryCase | None:
        """Retrieve a case by unique case ID."""
        return self._store.get_case(case_id)

    def get_by_payment_id(self, payment_id: str) -> RecoveryCase | None:
        """Retrieve a case by the originating gateway payment ID."""
        return self._store.get_case_by_payment_id(payment_id)

    def get_by_idempotency_key(self, idempotency_key: str) -> RecoveryCase | None:
        """Retrieve a case by idempotency key to prevent duplicate processing."""
        return self._store.get_case_by_idempotency_key(idempotency_key)

    def suggest_search_terms(
        self, prefix: str, *, limit: int = 8
    ) -> list[dict[str, Any]]:
        """Return distinct case identifiers and attributes matching a prefix."""
        return self._store.suggest_search_terms(prefix, limit=limit)

    def list_cases(
        self,
        *,
        merchant_id: str | None = None,
        state: RecoveryState | None = None,
        states: list[str] | None = None,
        experiment_arm: ExperimentArm | None = None,
        experiment_arms: list[str] | None = None,
        payment_rails: list[str] | None = None,
        error_codes: list[str] | None = None,
        error_sources: list[str] | None = None,
        amount_min_paise: int | None = None,
        amount_max_paise: int | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        occurred_after: datetime | None = None,
        occurred_before: datetime | None = None,
        touches_min: int | None = None,
        touches_max: int | None = None,
        recovered: bool | None = None,
        opted_out: bool | None = None,
        has_escalation: bool | None = None,
        customer_id: str | None = None,
        payment_id: str | None = None,
        invoice_id: str | None = None,
        subscription_id: str | None = None,
        campaign_id: str | None = None,
        user_ref: str | None = None,
        reference_id: str | None = None,
        q: str | None = None,
        model_used: str | None = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[RecoveryCase]:
        """List cases matching query filters with server-side pagination."""
        return self._store.list_cases(
            merchant_id=merchant_id,
            state=state,
            states=states,
            experiment_arm=experiment_arm,
            experiment_arms=experiment_arms,
            payment_rails=payment_rails,
            error_codes=error_codes,
            error_sources=error_sources,
            amount_min_paise=amount_min_paise,
            amount_max_paise=amount_max_paise,
            created_after=created_after,
            created_before=created_before,
            occurred_after=occurred_after,
            occurred_before=occurred_before,
            touches_min=touches_min,
            touches_max=touches_max,
            recovered=recovered,
            opted_out=opted_out,
            has_escalation=has_escalation,
            customer_id=customer_id,
            payment_id=payment_id,
            invoice_id=invoice_id,
            subscription_id=subscription_id,
            campaign_id=campaign_id,
            user_ref=user_ref,
            reference_id=reference_id,
            q=q,
            model_used=model_used,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )

    def count(
        self,
        *,
        merchant_id: str | None = None,
        state: RecoveryState | None = None,
        states: list[str] | None = None,
        experiment_arm: ExperimentArm | None = None,
        experiment_arms: list[str] | None = None,
        payment_rails: list[str] | None = None,
        error_codes: list[str] | None = None,
        error_sources: list[str] | None = None,
        amount_min_paise: int | None = None,
        amount_max_paise: int | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        occurred_after: datetime | None = None,
        occurred_before: datetime | None = None,
        touches_min: int | None = None,
        touches_max: int | None = None,
        recovered: bool | None = None,
        opted_out: bool | None = None,
        has_escalation: bool | None = None,
        customer_id: str | None = None,
        payment_id: str | None = None,
        invoice_id: str | None = None,
        subscription_id: str | None = None,
        campaign_id: str | None = None,
        user_ref: str | None = None,
        reference_id: str | None = None,
        q: str | None = None,
        model_used: str | None = None,
    ) -> int:
        """Count total cases matching query filters."""
        return self._store.count_cases(
            merchant_id=merchant_id,
            state=state,
            states=states,
            experiment_arm=experiment_arm,
            experiment_arms=experiment_arms,
            payment_rails=payment_rails,
            error_codes=error_codes,
            error_sources=error_sources,
            amount_min_paise=amount_min_paise,
            amount_max_paise=amount_max_paise,
            created_after=created_after,
            created_before=created_before,
            occurred_after=occurred_after,
            occurred_before=occurred_before,
            touches_min=touches_min,
            touches_max=touches_max,
            recovered=recovered,
            opted_out=opted_out,
            has_escalation=has_escalation,
            customer_id=customer_id,
            payment_id=payment_id,
            invoice_id=invoice_id,
            subscription_id=subscription_id,
            campaign_id=campaign_id,
            user_ref=user_ref,
            reference_id=reference_id,
            q=q,
            model_used=model_used,
        )

    def schedule_job(self, job: ScheduledJob) -> None:
        """Schedule a task for future execution."""
        self._store.schedule_job(job)

    def fetch_due_jobs(self, limit: int = 20) -> list[ScheduledJob]:
        """Fetch pending jobs ready for execution."""
        return self._store.fetch_due_jobs(limit=limit)

    def claim_next_due_job(self, now: datetime | None = None) -> ScheduledJob | None:
        """Atomically claim the next due job for processing."""
        return self._store.claim_next_due_job(now=now)

    def reclaim_stuck_processing_jobs(self, max_processing_seconds: int = 60) -> int:
        """Reclaim orphaned jobs stuck in PROCESSING on boot."""
        return self._store.reclaim_stuck_processing_jobs(
            max_processing_seconds=max_processing_seconds
        )

    def get_pipeline_overview(self) -> dict[str, Any]:
        """Fetch pipeline summary metrics and queue depth."""
        return self._store.get_pipeline_overview()

    def get_pipeline_timeseries(
        self, bucket_minutes: int = 60, hours: int = 24
    ) -> list[dict[str, Any]]:
        """Fetch timeseries of ingested vs processed events."""
        return self._store.get_pipeline_timeseries(
            bucket_minutes=bucket_minutes, hours=hours
        )

    def get_pipeline_heatmap(self) -> list[dict[str, Any]]:
        """Fetch 7x24 event distribution grid."""
        return self._store.get_pipeline_heatmap()

    def fetch_queued_jobs(
        self, limit: int = 50, statuses: list[str] | None = None
    ) -> list[ScheduledJob]:
        """Fetch queue entries with optional filter."""
        return self._store.fetch_queued_jobs(limit=limit, statuses=statuses)

    def update_job_status(
        self, job_id: str, status: str, attempts: int | None = None
    ) -> None:
        """Update status of a scheduled job."""
        self._store.update_job_status(job_id, status=status, attempts=attempts)

    def record_model_telemetry(self, telemetry: ModelTelemetryEntry) -> None:
        """Record model execution telemetry."""
        self._store.record_model_telemetry(telemetry)

    def get_model_telemetry_report(self) -> dict[str, Any]:
        """Aggregate model performance and telemetry from SQLite store."""
        return self._store.get_model_telemetry_report()

    def get_experiments_report(self) -> list[dict[str, Any]]:
        """Fetch A/B model experiment comparison stats."""
        return self._store.get_experiments_report()

    def get_strategy_experiments_report(self) -> list[dict[str, Any]]:
        """Fetch recovery strategy experiments report measuring incremental value."""
        return self._store.get_strategy_experiments_report()

    def get_execution_fidelity(self) -> dict[str, int]:
        """Count executed interventions by whether they reached a live gateway."""
        return self._store.get_execution_fidelity()

    def clear(self) -> None:
        """Clear repository contents (used for test teardown)."""
        self._store.clear()

    def save_pattern_alerts(self, alerts: list[dict[str, Any]]) -> None:
        self._store.save_pattern_alerts(alerts)

    def list_pattern_alerts(self) -> list[dict[str, Any]]:
        return self._store.list_pattern_alerts()

    def save_ml_model(self, model: dict[str, Any]) -> None:
        self._store.save_ml_model(model)

    def get_ml_model(self) -> dict[str, Any] | None:
        return self._store.get_ml_model()

    def save_ml_predictions(self, predictions: list[dict[str, Any]]) -> None:
        self._store.save_ml_predictions(predictions)


@functools.lru_cache(maxsize=1)
def get_case_repository() -> CaseRepository:
    """Return singleton instance of CaseRepository with ACID database storage."""
    return CaseRepository()
