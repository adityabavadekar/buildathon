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
        RecoveryState.RECOVERED,
    },
    RecoveryState.ANALYSIS_QUEUED: {
        RecoveryState.IN_DUNNING,
        RecoveryState.RETRY_SCHEDULED,
        RecoveryState.OUTREACH_PENDING,
        RecoveryState.RECOVERED,
        RecoveryState.ESCALATED,
        RecoveryState.ABANDONED,
        RecoveryState.FAILED,
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
        RecoveryState.FAILED,
    },
    RecoveryState.RETRY_SCHEDULED: {
        RecoveryState.IN_DUNNING,
        RecoveryState.OUTREACH_PENDING,
        RecoveryState.RECOVERED,
        RecoveryState.ESCALATED,
        RecoveryState.ABANDONED,
        RecoveryState.FAILED,
    },
    RecoveryState.OUTREACH_PENDING: {
        RecoveryState.IN_DUNNING,
        RecoveryState.P2P_WAITING,
        RecoveryState.P2P_PROMISED,
        RecoveryState.RECOVERED,
        RecoveryState.ESCALATED,
        RecoveryState.ABANDONED,
        RecoveryState.FAILED,
    },
    RecoveryState.P2P_WAITING: {
        RecoveryState.P2P_PROMISED,
        RecoveryState.IN_DUNNING,
        RecoveryState.RETRY_SCHEDULED,
        RecoveryState.RECOVERED,
        RecoveryState.ESCALATED,
        RecoveryState.ABANDONED,
        RecoveryState.FAILED,
    },
    RecoveryState.P2P_PROMISED: {
        RecoveryState.RECOVERED,
        RecoveryState.IN_DUNNING,
        RecoveryState.RETRY_SCHEDULED,
        RecoveryState.OUTREACH_PENDING,
        RecoveryState.ESCALATED,
        RecoveryState.ABANDONED,
        RecoveryState.FAILED,
    },
    # Terminal states
    RecoveryState.RECOVERED: set(),
    RecoveryState.ABANDONED: set(),
    RecoveryState.WRITTEN_OFF: set(),
    RecoveryState.ESCALATED: {
        RecoveryState.OUTREACH_PENDING,
        RecoveryState.RETRY_SCHEDULED,
        RecoveryState.IN_DUNNING,
        RecoveryState.ABANDONED,
        RecoveryState.WRITTEN_OFF,
        RecoveryState.RECOVERED,
        RecoveryState.FAILED,
    },
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

    case.state = to_state
    case.updated_at = datetime.now(UTC)
    case.recompute_nrv()

    # Record immutable audit entry
    entry = AuditEntry(
        case_id=case.case_id,
        from_state=current_state,
        to_state=to_state,
        actor=actor,
        event_name=event_name or f"state_transition.{to_state.value.lower()}",
        notes=reason,
        cost_incurred_paise=cost_incurred_paise,
        decision_inputs=decision_inputs or {},
        decision_outputs=decision_outputs or {},
        model_metadata=model_metadata,
    )
    case.audit_trail.append(entry)
    return case
