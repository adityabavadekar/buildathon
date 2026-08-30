"""Strict domain enums for revenue recovery lifecycle, failure taxonomy, and policies.

Every enum is string-backed for serialization safety across APIs and database storage.
"""

from enum import Enum


class RecoveryState(str, Enum):
    """Lifecycle state of an at-risk revenue case."""

    FAILED = "FAILED"
    ANALYSIS_QUEUED = "ANALYSIS_QUEUED"
    IN_DUNNING = "IN_DUNNING"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    OUTREACH_PENDING = "OUTREACH_PENDING"
    P2P_WAITING = "P2P_WAITING"
    P2P_PROMISED = "P2P_PROMISED"
    RECOVERED = "RECOVERED"
    ESCALATED = "ESCALATED"
    ABANDONED = "ABANDONED"
    WRITTEN_OFF = "WRITTEN_OFF"

    @property
    def is_terminal(self) -> bool:
        """Return True if this state is permanently resolved and immutable."""
        return self in {
            RecoveryState.RECOVERED,
            RecoveryState.ESCALATED,
            RecoveryState.ABANDONED,
            RecoveryState.WRITTEN_OFF,
        }

    @property
    def is_active(self) -> bool:
        """Return True if the case is currently progressing through active recovery."""
        return not self.is_terminal


class FailureCategory(str, Enum):
    """Root-cause classification of a payment or checkout failure."""

    TRANSIENT_BANK_WINDOW = "TRANSIENT_BANK_WINDOW"
    LIQUIDITY_CONSTRAINT = "LIQUIDITY_CONSTRAINT"
    STRUCTURAL_MANDATE_FAILURE = "STRUCTURAL_MANDATE_FAILURE"
    CHECKOUT_DROP_OFF = "CHECKOUT_DROP_OFF"
    SYSTEMIC_GATEWAY_FAILURE = "SYSTEMIC_GATEWAY_FAILURE"
    UNCLASSIFIED = "UNCLASSIFIED"


class InterventionType(str, Enum):
    """Action chosen by the agent or policy engine to recover revenue."""

    PASSIVE_RETRY = "PASSIVE_RETRY"
    SMART_RETRY = "SMART_RETRY"
    SMART_PAYMENT_LINK = "SMART_PAYMENT_LINK"
    CUSTOMER_NUDGE = "CUSTOMER_NUDGE"
    INCENTIVIZED_LINK = "INCENTIVIZED_LINK"
    MANUAL_ESCALATION = "MANUAL_ESCALATION"
    NO_ACTION = "NO_ACTION"


class OutreachChannel(str, Enum):
    """Communication channels supported for customer outreach."""

    WHATSAPP = "WHATSAPP"
    SMS = "SMS"
    EMAIL = "EMAIL"
    VOICE_CALL = "VOICE_CALL"


class PolicyCheckResult(str, Enum):
    """Result of deterministic policy guardrail evaluation."""

    APPROVED = "APPROVED"
    BLOCKED_MAX_RETRIES = "BLOCKED_MAX_RETRIES"
    BLOCKED_COOLDOWN = "BLOCKED_COOLDOWN"
    BLOCKED_MARGIN_CAP = "BLOCKED_MARGIN_CAP"
    BLOCKED_OPT_OUT = "BLOCKED_OPT_OUT"
    BLOCKED_LOW_CONFIDENCE = "BLOCKED_LOW_CONFIDENCE"
    ESCALATE_REQUIRED = "ESCALATE_REQUIRED"
    HOLDOUT_CONTROL = "HOLDOUT_CONTROL"


class ExperimentArm(str, Enum):
    """A/B experiment assignment for counterfactual recovery measurement."""

    TREATMENT = "TREATMENT"
    HOLDOUT_CONTROL = "HOLDOUT_CONTROL"


class AuditActor(str, Enum):
    """Initiator or executor of an audit-logged decision or state change."""

    SYSTEM = "SYSTEM"
    AGENT_LLM = "AGENT_LLM"
    POLICY_GATE = "POLICY_GATE"
    HUMAN_OPERATOR = "HUMAN_OPERATOR"
    GATEWAY_WEBHOOK = "GATEWAY_WEBHOOK"


class PaymentRail(str, Enum):
    """Underlying payment instrument or rail."""

    UPI = "UPI"
    UPI_AUTOPAY = "UPI_AUTOPAY"
    ENACH = "ENACH"
    CARD = "CARD"
    NETBANKING = "NETBANKING"
    UNKNOWN = "UNKNOWN"
