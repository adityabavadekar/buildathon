"""State machine engine enforcing valid dunning lifecycle transitions and audit logging."""

from datetime import UTC, datetime
from typing import Any

from app.audit.models import AuditEntry, RecoveryCase
from app.core.enums import AuditActor, RecoveryState


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal lifecycle transition is attempted."""


# Valid state transitions lookup table
VALID_TRANSITIONS: dict[RecoveryState, set[RecoveryState]] = {
    RecoveryState.FAILED: {
        RecoveryState.ANALYSIS_QUEUED,
        RecoveryState.ESCALATED,
        RecoveryState.ABANDONED,
    },
    RecoveryState.ANALYSIS_QUEUED: {
        RecoveryState.IN_DUNNING,
        RecoveryState.RETRY_SCHEDULED,
        RecoveryState.OUTREACH_PENDING,
        RecoveryState.RECOVERED,
        RecoveryState.ESCALATED,
        RecoveryState.ABANDONED,
    },
    RecoveryState.IN_DUNNING: {
        RecoveryState.RETRY_SCHEDULED,
        RecoveryState.OUTREACH_PENDING,
        RecoveryState.P2P_WAITING,
        RecoveryState.P2P_PROMISED,
        RecoveryState.RECOVERED,
        RecoveryState.ESCALATED,
        RecoveryState.ABANDONED,
        RecoveryState.WRITTEN_OFF,
    },
    RecoveryState.RETRY_SCHEDULED: {
        RecoveryState.IN_DUNNING,
        RecoveryState.OUTREACH_PENDING,
        RecoveryState.RECOVERED,
        RecoveryState.ESCALATED,
        RecoveryState.ABANDONED,
    },
    RecoveryState.OUTREACH_PENDING: {
        RecoveryState.IN_DUNNING,
        RecoveryState.P2P_WAITING,
        RecoveryState.P2P_PROMISED,
        RecoveryState.RECOVERED,
        RecoveryState.ESCALATED,
        RecoveryState.ABANDONED,
    },
    RecoveryState.P2P_WAITING: {
        RecoveryState.P2P_PROMISED,
        RecoveryState.IN_DUNNING,
        RecoveryState.RETRY_SCHEDULED,
        RecoveryState.RECOVERED,
        RecoveryState.ESCALATED,
        RecoveryState.ABANDONED,
    },
    RecoveryState.P2P_PROMISED: {
        RecoveryState.IN_DUNNING,
        RecoveryState.RETRY_SCHEDULED,
        RecoveryState.RECOVERED,
        RecoveryState.ESCALATED,
        RecoveryState.ABANDONED,
    },
    # Terminal states have no valid subsequent transitions
    RecoveryState.RECOVERED: set(),
    RecoveryState.ESCALATED: set(),
    RecoveryState.ABANDONED: set(),
    RecoveryState.WRITTEN_OFF: set(),
}


def transition_case(
    case: RecoveryCase,
    to_state: RecoveryState,
    actor: AuditActor,
    reason: str,
    *,
    event_name: str | None = None,
    decision_inputs: dict[str, Any] | None = None,
    decision_outputs: dict[str, Any] | None = None,
    cost_incurred_paise: int = 0,
    model_metadata: dict[str, Any] | None = None,
) -> RecoveryCase:
    """Transition a recovery case to a new state and record an immutable audit entry."""
    current_state = case.state

    # Invariant: Terminal states are strictly immutable
    if current_state.is_terminal:
        msg = f"Cannot transition case {case.case_id} from terminal state {current_state.value} to {to_state.value}"
        raise InvalidStateTransitionError(msg)

    # Invariant: Must follow allowable state paths
    allowed_targets = VALID_TRANSITIONS.get(current_state, set())
    if to_state not in allowed_targets:
        msg = f"Illegal transition for case {case.case_id} from {current_state.value} to {to_state.value}"
        raise InvalidStateTransitionError(msg)

    now = datetime.now(UTC)
    entry = AuditEntry(
        case_id=case.case_id,
        timestamp=now,
        event_name=event_name
        or f"state_transition.{current_state.value.lower()}_to_{to_state.value.lower()}",
        actor=actor,
        from_state=current_state,
        to_state=to_state,
        decision_inputs=decision_inputs or {},
        decision_outputs=decision_outputs or {"reason": reason},
        cost_incurred_paise=cost_incurred_paise,
        model_metadata=model_metadata,
        notes=reason,
    )

    case.state = to_state
    case.updated_at = now
    case.audit_trail.append(entry)
    case.recompute_nrv()

    return case
