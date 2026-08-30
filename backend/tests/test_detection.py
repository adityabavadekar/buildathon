"""Tests for failure classification and diagnostic error mapping."""

from datetime import UTC, datetime
from decimal import Decimal

from app.core.enums import FailureCategory, InterventionType, PaymentRail
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
