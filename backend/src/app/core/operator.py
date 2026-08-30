"""Durable operator autonomy controls and circuit breaker configuration."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from app.audit.models import AuditEntry
from app.audit.repository import get_case_repository
from app.core.enums import AuditActor
from app.core.logging import get_logger

logger = get_logger(__name__)

OPERATOR_CONFIG_PATH = Path("data/operator_config.json")


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
    """Load the current operator autonomy state from durable storage."""
    if OPERATOR_CONFIG_PATH.exists():
        try:
            with OPERATOR_CONFIG_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return OperatorModeState.model_validate(data)
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
    """Update operator mode, persist to storage, and log audit event."""
    from_mode = get_operator_mode()
    now = datetime.now(UTC)

    new_state = OperatorModeState(
        mode=mode,
        reason=reason,
        updated_at=now,
        updated_by=updated_by,
    )

    OPERATOR_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OPERATOR_CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(new_state.model_dump(mode="json"), f, indent=2)

    logger.info(
        "operator.mode_changed",
        from_mode=from_mode.value,
        to_mode=mode.value,
        reason=reason,
        updated_by=updated_by,
    )

    # Record system-wide audit entry in database
    try:
        repo = get_case_repository()
        entry = AuditEntry(
            case_id="SYSTEM_GLOBAL",
            from_state=None,
            to_state=None,
            actor=AuditActor.HUMAN_OPERATOR
            if "operator" in updated_by.lower()
            else AuditActor.SYSTEM,
            event_name="operator.mode_changed",
            notes=f"Autonomy mode switched from {from_mode.value} to {mode.value}: {reason}",
            cost_incurred_paise=0,
            decision_inputs={
                "from_mode": from_mode.value,
                "to_mode": mode.value,
                "reason": reason,
                "updated_by": updated_by,
            },
            timestamp=now,
        )
        repo._store._lock.acquire()
        try:
            cur = repo._store._conn.cursor()
            cur.execute(
                """
                INSERT OR IGNORE INTO audit (
                    entry_id, case_id, event_name, actor, from_state, to_state,
                    reason, notes, decision_inputs, decision_outputs, model_metadata,
                    cost_incurred_paise, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    entry.entry_id,
                    entry.case_id,
                    entry.event_name,
                    entry.actor.value,
                    None,
                    None,
                    reason,
                    entry.notes,
                    json.dumps(entry.decision_inputs),
                    json.dumps({}),
                    None,
                    0,
                    now.isoformat(),
                ),
            )
            repo._store._conn.commit()
        finally:
            repo._store._lock.release()
    except Exception as exc:  # noqa: BLE001
        logger.warning("operator.mode_audit_failed", error=str(exc))

    return new_state
