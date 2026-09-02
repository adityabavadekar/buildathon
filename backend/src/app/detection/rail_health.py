"""Fleet-wide payment rail degradation detection and automated retry circuit breaker."""

from __future__ import annotations

import functools
import threading
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.db import get_db_connection
from app.core.enums import PaymentRail
from app.core.logging import get_logger

logger = get_logger(__name__)


class RailHealthState(StrEnum):
    """Operational health state of a payment rail."""

    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"


class RailHealthMetrics(BaseModel):
    """Statistical health telemetry for a single payment rail across sliding windows."""

    rail: str
    state: RailHealthState = RailHealthState.NORMAL
    current_failure_rate: float = 0.0
    baseline_failure_rate: float = 0.0
    ratio: float = 1.0
    attempts: int = 0
    failures: int = 0
    hold_until: datetime | None = None
    detected_at: datetime | None = None
    last_observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RailHealthRegistry:
    """Thread-safe statistical detector and state registry for fleet-wide payment rail health."""

    def __init__(
        self,
        *,
        min_attempts: int = 10,
        degradation_ratio_threshold: float = 2.5,
        absolute_min_rate: float = 0.05,
        hold_duration_minutes: int = 60,
    ) -> None:
        self._lock = threading.RLock()
        self.min_attempts = min_attempts
        self.degradation_ratio_threshold = degradation_ratio_threshold
        self.absolute_min_rate = absolute_min_rate
        self.hold_duration_minutes = hold_duration_minutes
        self._states: dict[str, RailHealthMetrics] = {}

    def get_rail_metrics(self, rail: str | PaymentRail) -> RailHealthMetrics:
        """Fetch current or evaluated rail health metrics."""
        rail_str = rail.value if isinstance(rail, PaymentRail) else str(rail)
        with self._lock:
            if rail_str not in self._states:
                self.evaluate_rail(rail_str)
            return self._states.get(rail_str, RailHealthMetrics(rail=rail_str))

    def is_rail_degraded(self, rail: str | PaymentRail) -> bool:
        """Return True if the specified payment rail is currently held under degradation."""
        metrics = self.get_rail_metrics(rail)
        if metrics.state != RailHealthState.DEGRADED:
            return False

        if metrics.hold_until and datetime.now(UTC) > metrics.hold_until:
            metrics.state = RailHealthState.NORMAL
            metrics.hold_until = None
            return False

        return True

    def set_degraded_override(
        self,
        rail: str | PaymentRail,
        *,
        ratio: float = 3.5,
        current_rate: float = 0.45,
        baseline_rate: float = 0.10,
        hold_minutes: int = 60,
        reason: str | None = None,
    ) -> RailHealthMetrics:
        """Manually or explicitly trip the degradation circuit breaker for a rail."""
        rail_str = rail.value if isinstance(rail, PaymentRail) else str(rail)
        now = datetime.now(UTC)
        hold_until = now + timedelta(minutes=hold_minutes)

        with self._lock:
            metrics = RailHealthMetrics(
                rail=rail_str,
                state=RailHealthState.DEGRADED,
                current_failure_rate=current_rate,
                baseline_failure_rate=baseline_rate,
                ratio=ratio,
                attempts=self.min_attempts,
                failures=int(self.min_attempts * current_rate),
                hold_until=hold_until,
                detected_at=now,
                last_observed_at=now,
            )
            self._states[rail_str] = metrics

            logger.warning(
                "rail_health.circuit_tripped",
                rail=rail_str,
                hold_until=hold_until.isoformat(),
                ratio=ratio,
                reason=reason or "manual_override",
            )
            return metrics

    def mark_degraded(
        self,
        rail: str | PaymentRail,
        *,
        reason: str | None = None,
        duration_minutes: int | None = None,
    ) -> RailHealthMetrics:
        """Alias for set_degraded_override."""
        return self.set_degraded_override(
            rail=rail,
            hold_minutes=duration_minutes or self.hold_duration_minutes,
            reason=reason,
        )

    def release_rail(self, rail: str | PaymentRail) -> RailHealthMetrics:
        """Clear degradation status for a rail."""
        rail_str = rail.value if isinstance(rail, PaymentRail) else str(rail)
        now = datetime.now(UTC)
        with self._lock:
            metrics = self._states.get(rail_str, RailHealthMetrics(rail=rail_str))
            metrics.state = RailHealthState.NORMAL
            metrics.hold_until = None
            metrics.last_observed_at = now
            self._states[rail_str] = metrics
            logger.info("rail_health.circuit_reset", rail=rail_str)
            return metrics

    def reset_rail(self, rail: str | PaymentRail) -> RailHealthMetrics:
        """Alias for release_rail."""
        return self.release_rail(rail)

    def evaluate_rail(self, rail: str) -> RailHealthMetrics:
        """Compute statistical failure rate over sliding window vs historical baseline."""
        now = datetime.now(UTC)
        recent_cutoff = now - timedelta(hours=1)
        baseline_cutoff = now - timedelta(days=7)

        with self._lock:
            try:
                with get_db_connection() as conn:
                    recent_row = conn.execute(
                        text(
                            """
                            SELECT COUNT(*) as attempts,
                                   SUM(CASE WHEN state NOT IN ('RECOVERED') THEN 1 ELSE 0 END) as failures
                            FROM cases
                            WHERE payment_rail = :rail AND created_at >= :recent_cutoff;
                            """
                        ),
                        {"rail": rail, "recent_cutoff": recent_cutoff},
                    ).fetchone()
                    recent_attempts = (
                        recent_row[0] if recent_row and recent_row[0] else 0
                    )
                    recent_failures = (
                        recent_row[1] if recent_row and recent_row[1] else 0
                    )

                    base_row = conn.execute(
                        text(
                            """
                            SELECT COUNT(*) as attempts,
                                   SUM(CASE WHEN state NOT IN ('RECOVERED') THEN 1 ELSE 0 END) as failures
                            FROM cases
                            WHERE payment_rail = :rail AND created_at >= :baseline_cutoff AND created_at < :recent_cutoff;
                            """
                        ),
                        {
                            "rail": rail,
                            "baseline_cutoff": baseline_cutoff,
                            "recent_cutoff": recent_cutoff,
                        },
                    ).fetchone()
                    base_attempts = base_row[0] if base_row and base_row[0] else 0
                    base_failures = base_row[1] if base_row and base_row[1] else 0

                    current_rate = (
                        (recent_failures / recent_attempts)
                        if recent_attempts > 0
                        else 0.0
                    )
                    baseline_rate = (
                        (base_failures / base_attempts) if base_attempts > 0 else 0.0
                    )
                    ratio = (
                        round(current_rate / baseline_rate, 2)
                        if baseline_rate > 0
                        else (1.0 if current_rate == 0 else 3.0)
                    )

                    is_degraded = (
                        base_attempts >= self.min_attempts
                        and recent_attempts >= self.min_attempts
                        and ratio >= self.degradation_ratio_threshold
                        and current_rate >= self.absolute_min_rate
                    )

                    existing = self._states.get(rail)
                    hold_until = (
                        existing.hold_until
                        if (existing and existing.state == RailHealthState.DEGRADED)
                        else None
                    )
                    detected_at = (
                        existing.detected_at
                        if (existing and existing.state == RailHealthState.DEGRADED)
                        else None
                    )

                    if is_degraded:
                        state = RailHealthState.DEGRADED
                        detected_at = detected_at or now
                        hold_until = now + timedelta(minutes=self.hold_duration_minutes)
                    elif hold_until and hold_until < now:
                        state = RailHealthState.NORMAL
                        hold_until = None
                    else:
                        state = existing.state if existing else RailHealthState.NORMAL

                    metrics = RailHealthMetrics(
                        rail=rail,
                        state=state,
                        current_failure_rate=round(current_rate, 4),
                        baseline_failure_rate=round(baseline_rate, 4),
                        ratio=ratio,
                        attempts=recent_attempts,
                        failures=recent_failures,
                        hold_until=hold_until,
                        detected_at=detected_at,
                        last_observed_at=now,
                    )
                    self._states[rail] = metrics
                    return metrics
            except Exception as exc:  # noqa: BLE001
                logger.warning("rail_health.evaluate_failed", rail=rail, error=str(exc))
                return RailHealthMetrics(rail=rail)

    def get_all_rails_health(self) -> list[RailHealthMetrics]:
        """Return health telemetry for all recognized payment rails."""
        all_rails = [r.value for r in PaymentRail if r != PaymentRail.UNKNOWN]
        metrics_list: list[RailHealthMetrics] = []
        for r in all_rails:
            metrics_list.append(self.get_rail_metrics(r))
        return metrics_list


@functools.lru_cache(maxsize=1)
def get_rail_health_registry() -> RailHealthRegistry:
    """Return process-wide singleton rail health registry."""
    return RailHealthRegistry()
