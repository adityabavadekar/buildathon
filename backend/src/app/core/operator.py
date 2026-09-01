"""Durable operator autonomy controls and circuit breaker configuration."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.db import get_db_connection
from app.core.logging import get_logger

logger = get_logger(__name__)


class OperatorMode(str, Enum):
    """System-wide operator intervention autonomy mode."""

    FULL_AUTONOMY = "FULL_AUTONOMY"
    HUMAN_IN_THE_LOOP = "HUMAN_IN_THE_LOOP"
    MONITORING_ONLY = "MONITORING_ONLY"


class OperatorModeState(BaseModel):
    """Persisted operator autonomy configuration state."""

    mode: OperatorMode = Field(default=OperatorMode.FULL_AUTONOMY)
    reason: str = Field(default="System initialization")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_by: str = Field(default="system")


def get_operator_mode_state() -> OperatorModeState:
    """Load the current operator autonomy state from PostgreSQL storage."""
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                text(
                    "SELECT mode, updated_at, updated_by FROM operator_mode WHERE id = 1"
                )
            ).fetchone()
            if row:
                return OperatorModeState(
                    mode=OperatorMode(row[0]),
                    reason="Loaded from PostgreSQL store",
                    updated_at=row[1],
                    updated_by=row[2],
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("operator_mode.read_failed", error=str(exc))

    return OperatorModeState()


def get_operator_mode() -> OperatorMode:
    """Get active operator mode directly from storage."""
    return get_operator_mode_state().mode


def set_operator_mode(
    mode: OperatorMode,
    reason: str,
    updated_by: str = "operator",
) -> OperatorModeState:
    """Update operator mode, persist to PostgreSQL storage, and log audit event."""
    from_mode = get_operator_mode()
    now = datetime.now(UTC)

    new_state = OperatorModeState(
        mode=mode,
        reason=reason,
        updated_at=now,
        updated_by=updated_by,
    )

    try:
        with get_db_connection() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO operator_mode (id, mode, updated_at, updated_by)
                    VALUES (1, :mode, :updated_at, :updated_by)
                    ON CONFLICT (id) DO UPDATE SET
                        mode = EXCLUDED.mode,
                        updated_at = EXCLUDED.updated_at,
                        updated_by = EXCLUDED.updated_by;
                    """
                ),
                {
                    "mode": mode.value,
                    "updated_at": now,
                    "updated_by": updated_by,
                },
            )

            actor = "HUMAN_OPERATOR" if "operator" in updated_by.lower() else "SYSTEM"
            entry_id = f"audit_op_{now.timestamp()}"
            conn.execute(
                text(
                    """
                    INSERT INTO audit (
                        entry_id, case_id, event_name, actor, from_state, to_state,
                        reason, notes, decision_inputs, decision_outputs, cost_incurred_paise, timestamp
                    ) VALUES (
                        :entry_id, 'SYSTEM_GLOBAL', 'operator.mode_changed', :actor, NULL, NULL,
                        :reason, :notes, CAST(:inputs AS jsonb), CAST(:outputs AS jsonb), 0, :timestamp
                    ) ON CONFLICT (entry_id) DO NOTHING;
                    """
                ),
                {
                    "entry_id": entry_id,
                    "actor": actor,
                    "reason": reason,
                    "notes": f"Autonomy mode switched from {from_mode.value} to {mode.value}: {reason}",
                    "inputs": json.dumps(
                        {"from_mode": from_mode.value, "to_mode": mode.value}
                    ),
                    "outputs": json.dumps({}),
                    "timestamp": now,
                },
            )
    except Exception as exc:
        logger.error("operator_mode.write_failed", error=str(exc))
        raise

    logger.info(
        "operator.mode_changed",
        from_mode=from_mode.value,
        to_mode=mode.value,
        reason=reason,
        updated_by=updated_by,
    )

    return new_state
