"""Audit writes for system-wide actions that belong to no single recovery case."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import text

from app.core.constants import GLOBAL_AUDIT_CASE_ID
from app.core.db import get_db_connection
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.core.enums import AuditActor

logger = get_logger(__name__)


def record_global_audit(
    *,
    event_name: str,
    actor: AuditActor,
    reason: str,
    notes: str | None = None,
    decision_inputs: dict[str, Any] | None = None,
    decision_outputs: dict[str, Any] | None = None,
) -> str:
    """Append a system-scoped audit row and return its entry id.

    Pass only non-sensitive values: this is readable in the operator audit trail.
    """
    entry_id = str(uuid4())
    with get_db_connection() as conn:
        conn.execute(
            text(
                """
                INSERT INTO audit (
                    entry_id, case_id, event_name, actor, from_state, to_state,
                    reason, notes, decision_inputs, decision_outputs,
                    cost_incurred_paise, timestamp
                ) VALUES (
                    :entry_id, :case_id, :event_name, :actor, NULL, NULL,
                    :reason, :notes, CAST(:inputs AS jsonb), CAST(:outputs AS jsonb),
                    0, :timestamp
                ) ON CONFLICT (entry_id) DO NOTHING;
                """
            ),
            {
                "entry_id": entry_id,
                "case_id": GLOBAL_AUDIT_CASE_ID,
                "event_name": event_name,
                "actor": actor.value,
                "reason": reason,
                "notes": notes,
                "inputs": json.dumps(decision_inputs or {}),
                "outputs": json.dumps(decision_outputs or {}),
                "timestamp": datetime.now(UTC),
            },
        )
    logger.info("audit.global_recorded", event_name=event_name, actor=actor.value)
    return entry_id
