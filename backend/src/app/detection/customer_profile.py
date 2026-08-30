"""Per-customer payment behavior profiles and deterministic risk tier computation."""

from __future__ import annotations

import functools
import sqlite3
import threading
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

from app.core.logging import get_logger

logger = get_logger(__name__)


class CustomerRiskTier(StrEnum):
    """Deterministic risk classification based on payment and dunning behavior."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class CustomerProfile(BaseModel):
    """Aggregated payment behavior profile for an individual merchant customer."""

    customer_id: str
    total_cases: int = 0
    recovered_cases: int = 0
    recovered_rate: float = 0.0
    avg_payment_delay_hours: float = 0.0
    preferred_rail: str = "UPI"
    outstanding_paise: int = 0
    repeat_failure_count: int = 0
    risk_tier: CustomerRiskTier = CustomerRiskTier.LOW
    last_activity_at: datetime | None = None


class CustomerProfileRegistry:
    """Thread-safe on-demand aggregator for customer payment behavior profiles."""

    def __init__(self, db_path: Path | str = "data/recovery_engine.db") -> None:
        self._db_path = Path(db_path)
        self._lock = threading.RLock()

    def get_profile(self, customer_id: str) -> CustomerProfile:
        """Compute and return customer profile from relational case history."""
        if not self._db_path.exists():
            return CustomerProfile(customer_id=customer_id)

        with self._lock:
            conn = sqlite3.connect(str(self._db_path), timeout=10.0)
            conn.row_factory = sqlite3.Row
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT case_id, payment_rail, state, amount_paise,
                           created_at, updated_at
                    FROM cases
                    WHERE customer_id = ?
                    ORDER BY created_at DESC;
                    """,
                    (customer_id,),
                )
                rows = cur.fetchall()
                if not rows:
                    return CustomerProfile(customer_id=customer_id)

                total_cases = len(rows)
                recovered_rows = [r for r in rows if r["state"] == "RECOVERED"]
                recovered_cases = len(recovered_rows)
                recovered_rate = (
                    round(recovered_cases / total_cases, 4) if total_cases > 0 else 0.0
                )

                # Compute average delay hours for recovered cases
                delay_hours_list: list[float] = []
                for r in recovered_rows:
                    try:
                        c_at = datetime.fromisoformat(r["created_at"])
                        u_at = datetime.fromisoformat(r["updated_at"])
                        diff_hours = max(0.0, (u_at - c_at).total_seconds() / 3600)
                        delay_hours_list.append(diff_hours)
                    except (ValueError, TypeError, KeyError):
                        continue
                avg_delay = (
                    round(sum(delay_hours_list) / len(delay_hours_list), 2)
                    if delay_hours_list
                    else 0.0
                )

                # Preferred rail: rail with most recovered or most total cases
                rail_counts: dict[str, int] = {}
                for r in recovered_rows if recovered_rows else rows:
                    rail = r["payment_rail"] or "UPI"
                    rail_counts[rail] = rail_counts.get(rail, 0) + 1
                preferred_rail = (
                    max(rail_counts.items(), key=lambda x: x[1])[0]
                    if rail_counts
                    else "UPI"
                )

                # Outstanding amount over non-terminal cases
                outstanding_paise = sum(
                    r["amount_paise"]
                    for r in rows
                    if r["state"] not in ("RECOVERED", "ABANDONED", "WRITTEN_OFF")
                )

                repeat_failure_count = total_cases
                last_activity = (
                    datetime.fromisoformat(rows[0]["created_at"]) if rows else None
                )

                # Derive deterministic risk tier
                low_risk_threshold = 0.70
                high_risk_threshold = 0.25
                min_cases_for_tier = 2
                if (
                    recovered_rate >= low_risk_threshold
                    and total_cases >= min_cases_for_tier
                ):
                    tier = CustomerRiskTier.LOW
                elif (
                    recovered_rate <= high_risk_threshold
                    and total_cases > min_cases_for_tier
                ):
                    tier = CustomerRiskTier.HIGH
                else:
                    tier = CustomerRiskTier.MEDIUM

                return CustomerProfile(
                    customer_id=customer_id,
                    total_cases=total_cases,
                    recovered_cases=recovered_cases,
                    recovered_rate=recovered_rate,
                    avg_payment_delay_hours=avg_delay,
                    preferred_rail=preferred_rail,
                    outstanding_paise=outstanding_paise,
                    repeat_failure_count=repeat_failure_count,
                    risk_tier=tier,
                    last_activity_at=last_activity,
                )
            finally:
                conn.close()

    def list_profiles(self, limit: int = 50) -> list[CustomerProfile]:
        """List customer profiles across unique customers in the cases table."""
        if not self._db_path.exists():
            return []

        with self._lock:
            conn = sqlite3.connect(str(self._db_path), timeout=10.0)
            conn.row_factory = sqlite3.Row
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT DISTINCT customer_id
                    FROM cases
                    WHERE customer_id IS NOT NULL AND customer_id != ''
                    LIMIT ?;
                    """,
                    (limit,),
                )
                cust_ids = [r["customer_id"] for r in cur.fetchall()]
                return [self.get_profile(cid) for cid in cust_ids]
            finally:
                conn.close()


@functools.lru_cache(maxsize=1)
def get_customer_profile_registry() -> CustomerProfileRegistry:
    """Return process-wide singleton customer profile registry."""
    return CustomerProfileRegistry()
