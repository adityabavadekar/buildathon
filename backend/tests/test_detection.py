"""Tests for failure classification and diagnostic error mapping."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.audit.models import RecoveryCase
from app.audit.postgres_store import RelationalCaseStore
from app.core.enums import (
    ExperimentArm,
    FailureCategory,
    InterventionType,
    PaymentRail,
    RecoveryState,
)
from app.detection.classifier import FailureClassifier
from app.detection.models import RawFailureEvent


def test_transient_banking_window_classification() -> None:
    classifier = FailureClassifier()
    event = RawFailureEvent(
        event_id="evt_1",
        payment_id="pay_1",
        customer_id="cust_1",
        amount_paise=100000,
        payment_rail=PaymentRail.UPI_AUTOPAY,
        error_code="BAD_REQUEST_ERROR",
        error_reason="bank_cutoff_in_progress",
        npci_response_code="XT",
        occurred_at=datetime.now(UTC),
    )

    diagnosis = classifier.classify(event)
    assert diagnosis.category == FailureCategory.TRANSIENT_BANK_WINDOW
    assert diagnosis.recommended_intervention == InterventionType.PASSIVE_RETRY
    assert diagnosis.recommended_delay_hours == 4
    assert diagnosis.confidence >= Decimal("0.90")
    assert not diagnosis.requires_human_approval


def test_structural_mandate_failure_classification() -> None:
    classifier = FailureClassifier()
    event = RawFailureEvent(
        event_id="evt_2",
        payment_id="pay_2",
        customer_id="cust_2",
        amount_paise=250000,
        payment_rail=PaymentRail.ENACH,
        error_code="BAD_REQUEST_ERROR",
        error_reason="mandate_revoked",
        npci_response_code="VA",
        occurred_at=datetime.now(UTC),
    )

    diagnosis = classifier.classify(event)
    assert diagnosis.category == FailureCategory.STRUCTURAL_MANDATE_FAILURE
    assert diagnosis.recommended_intervention == InterventionType.SMART_PAYMENT_LINK
    assert diagnosis.recommended_delay_hours == 0
    assert not diagnosis.requires_human_approval


def test_liquidity_constraint_classification() -> None:
    classifier = FailureClassifier()
    event = RawFailureEvent(
        event_id="evt_3",
        payment_id="pay_3",
        customer_id="cust_3",
        amount_paise=150000,
        payment_rail=PaymentRail.CARD,
        error_code="BAD_REQUEST_ERROR",
        error_reason="insufficient_funds",
        npci_response_code="AP15",
        occurred_at=datetime.now(UTC),
    )

    diagnosis = classifier.classify(event)
    assert diagnosis.category == FailureCategory.LIQUIDITY_CONSTRAINT
    assert diagnosis.recommended_intervention == InterventionType.SMART_RETRY
    assert diagnosis.recommended_delay_hours == 48


def test_checkout_drop_off_classification() -> None:
    classifier = FailureClassifier()
    event = RawFailureEvent(
        event_id="evt_4",
        payment_id="pay_4",
        customer_id="cust_4",
        amount_paise=49900,
        payment_rail=PaymentRail.UPI,
        error_code="BAD_REQUEST_ERROR",
        error_step="payment_authentication",
        error_reason="otp_timeout",
        occurred_at=datetime.now(UTC),
    )

    diagnosis = classifier.classify(event)
    assert diagnosis.category == FailureCategory.CHECKOUT_DROP_OFF
    assert diagnosis.recommended_intervention == InterventionType.INCENTIVIZED_LINK
    assert diagnosis.discount_bps_suggested == 500


def test_unclassified_fallback_routes_to_human_approval() -> None:
    classifier = FailureClassifier()
    event = RawFailureEvent(
        event_id="evt_5",
        payment_id="pay_5",
        customer_id="cust_5",
        amount_paise=300000,
        error_code="UNKNOWN_ANOMALOUS_ERROR",
        error_reason="foreign_exchange_lock",
        occurred_at=datetime.now(UTC),
    )

    diagnosis = classifier.classify(event)
    assert diagnosis.category == FailureCategory.UNCLASSIFIED
    assert diagnosis.recommended_intervention == InterventionType.MANUAL_ESCALATION
    assert diagnosis.requires_human_approval is True


def _event(code: str, reason: str, customer_id: str = "cust_indet") -> RawFailureEvent:
    return RawFailureEvent(
        event_id=f"evt_{code}",
        payment_id=f"pay_{code}",
        customer_id=customer_id,
        amount_paise=250000,
        payment_rail=PaymentRail.CARD,
        error_code=code,
        error_reason=reason,
        occurred_at=datetime.now(UTC),
    )


def test_gateway_timeout_is_never_auto_retried() -> None:
    """A timeout leaves the authorization unknown, so retrying risks a double charge."""
    diagnosis = FailureClassifier().classify(
        _event("GATEWAY_TIMEOUT", "gateway_timeout waiting for authorization")
    )

    assert diagnosis.category is FailureCategory.INDETERMINATE_AUTHORIZATION
    assert diagnosis.recommended_intervention is InterventionType.MANUAL_ESCALATION
    assert diagnosis.requires_human_approval is True
    assert "twice" in diagnosis.reasoning


def test_network_failure_is_treated_as_indeterminate() -> None:
    diagnosis = FailureClassifier().classify(_event("NETWORK_ERROR", "network_error"))

    assert diagnosis.category is FailureCategory.INDETERMINATE_AUTHORIZATION
    assert diagnosis.recommended_intervention is InterventionType.MANUAL_ESCALATION


def test_customer_side_otp_timeout_stays_retryable() -> None:
    """An abandoned OTP is a known failure, so it must not be misread as unknown."""
    diagnosis = FailureClassifier().classify(
        _event("OTP_TIMEOUT", "otp_timeout, customer did not enter the code")
    )

    assert diagnosis.category is FailureCategory.CHECKOUT_DROP_OFF
    assert diagnosis.recommended_intervention is InterventionType.INCENTIVIZED_LINK


def test_liquidity_diagnosis_explains_how_history_was_weighted() -> None:
    """The reasoning must state the weighting, not just apply a default rule."""
    diagnosis = FailureClassifier().classify(
        _event("AP15", "insufficient_funds", customer_id="cust_no_history")
    )

    assert diagnosis.category is FailureCategory.LIQUIDITY_CONSTRAINT
    assert diagnosis.recommended_intervention is InterventionType.SMART_RETRY
    assert "No prior history" in diagnosis.reasoning
    assert diagnosis.signals_evaluated["customer_total_cases"] == 0


def _history_case(idx: int, customer_id: str, recovered: bool) -> RecoveryCase:
    now = datetime.now(UTC)
    return RecoveryCase(
        case_id=f"case_hist_{customer_id}_{idx}",
        state=RecoveryState.RECOVERED if recovered else RecoveryState.FAILED,
        experiment_arm=ExperimentArm.TREATMENT,
        amount_paise=100000,
        recovered_amount_paise=100000 if recovered else 0,
        currency="INR",
        created_at=now - timedelta(hours=20 + idx),
        updated_at=now - timedelta(hours=10 + idx),
        failure_event=RawFailureEvent(
            event_id=f"evt_hist_{customer_id}_{idx}",
            payment_id=f"pay_hist_{customer_id}_{idx}",
            customer_id=customer_id,
            amount_paise=100000,
            currency="INR",
            payment_rail=PaymentRail.UPI_AUTOPAY,
            error_code="AP15",
            error_reason="insufficient_funds",
            occurred_at=now,
        ),
    )


def test_repeat_liquidity_failure_on_thin_history_escalates() -> None:
    """Repeat declines with a poor record are solvency, not timing; a retry cannot fix that."""
    store = RelationalCaseStore()
    customer_id = "cust_repeat_thin"
    for i in range(4):
        store.save_case(_history_case(i, customer_id, recovered=False))

    diagnosis = FailureClassifier().classify(
        _event("AP15", "insufficient_funds", customer_id=customer_id)
    )

    assert diagnosis.category is FailureCategory.LIQUIDITY_CONSTRAINT
    assert diagnosis.recommended_intervention is InterventionType.MANUAL_ESCALATION
    assert diagnosis.requires_human_approval is True
    assert "too thin" in diagnosis.reasoning
    assert diagnosis.signals_evaluated["customer_repeat_failures"] == 4


def test_long_reliable_history_outweighs_repeat_failures() -> None:
    """A customer who reliably pays keeps the retry: the same code, weighted differently."""
    store = RelationalCaseStore()
    customer_id = "cust_repeat_reliable"
    for i in range(8):
        store.save_case(_history_case(i, customer_id, recovered=i < 7))

    diagnosis = FailureClassifier().classify(
        _event("AP15", "insufficient_funds", customer_id=customer_id)
    )

    assert diagnosis.recommended_intervention is InterventionType.SMART_RETRY
    assert diagnosis.requires_human_approval is False
    assert "outweigh" in diagnosis.reasoning
