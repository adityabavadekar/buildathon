"""Exhaustive coverage of every Razorpay-documented error reason against the
failure classifier's taxonomy, per razorpay.com/docs/errors/payments/list,
/upi, /cards, and /common.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.enums import FailureCategory, PaymentRail
from app.detection.classifier import classify_failure
from app.detection.models import RawFailureEvent

INDETERMINATE_REASONS = [
    "payment_timed_out",
    "request_timed_out",
    "verification_failed",
    "invalid_response_from_gateway",
    "demed_transaction",
]

TRANSIENT_REASONS = [
    "bank_cutoff_in_progress",
    "bank_not_available",
    "bank_technical_error",
    "gateway_technical_error",
    "issuer_technical_error",
    "server_error",
    "psp_app_not_available",
    "psp_not_available",
    "payment_declined_due_to_high_traffic",
    "upi_app_technical_error",
    "duplicate_rrn_found",
]

MANDATE_FAILURE_REASONS = [
    "mandate_creation_declined",
    "mandate_creation_expired",
    "mandate_creation_failed",
    "mandate_creation_timeout",
    "funds_blocked_by_mandate",
    "reqauth_mandate_not_acknowledged",
    "recurring_payment_not_enabled",
    "mandate_exhausted",
]

LIQUIDITY_REASONS = [
    "insufficient_funds",
    "debit_declined",
    "credit_limit_exceeded",
    "credit_limit_expired",
    "credit_limit_inactive",
    "credit_limit_not_approved",
    "credit_not_permitted",
    "credit_failed",
    "transaction_limit_exceeded",
    "transaction_daily_limit_exceeded",
    "transaction_daily_count_exceeded",
    "mc_amount_limit_exceeded",
]

CHECKOUT_DROPOFF_REASONS = [
    "authentication_failed",
    "payment_cancelled",
    "otp_expired",
    "otp_attempts_exceeded",
    "incorrect_otp",
    "incorrect_cvv",
    "incorrect_pin",
    "incorrect_atm_pin",
    "pin_attempts_exceeded",
    "pin_not_set",
    "payment_session_expired",
    "payment_collect_request_expired",
    "incorrect_card_details",
    "incorrect_card_expiry_date",
    "incorrect_cardholder_name",
]

SYSTEMIC_REASONS = [
    "card_declined",
    "payment_declined",
    "payment_failed",
    "payment_risk_check_failed",
    "card_expired",
    "card_not_enrolled",
    "card_disabled_for_online_payments",
    "debit_instrument_blocked",
    "debit_instrument_inactive",
    "bank_account_invalid",
    "invalid_vpa",
    "vpa_resolution_failed",
    "user_not_eligible",
    "card_network_not_enabled",
    "card_type_invalid",
    "card_number_invalid",
    "international_transaction_not_allowed",
    "payment_method_not_enabled",
    "user_not_registered_for_netbanking",
    "beneficiary_account_does_not_exist",
    "beneficiary_account_dormant",
    "psp_not_registered",
    "psp_app_not_supported",
    "transaction_on_vpa_restricted",
    "transaction_frequency_limit_exceeded",
    "authorisation_declined_by_psp",
    "collect_on_mc_blocked",
    "collect_request_pending",
    "payment_amount_tampered",
    "emi_greater_than_max_amount",
    "emi_plan_unavailable",
    "upi_autopay_not_supported_on_psp",
    "upi_collect_not_enabled",
    "upi_intent_not_enabled",
]

# Merchant-side/config errors: no customer-facing recovery action exists for
# these, so they correctly fall through to UNCLASSIFIED -> human review rather
# than being force-fit into a customer-recovery category.
UNCLASSIFIED_REASONS = [
    "bank_not_enabled",
    "merchant_not_activated",
    "live_mode_not_enabled",
    "input_validation_failed",
    "invalid_amount",
    "invalid_currency",
    "invalid_order_id",
    "invalid_request",
    "order_already_paid",
    "order_payment_method_mismatch",
    "order_amount_mismatch",
    "duplicate_request",
    "duplicate_refund_id",
    "refund_limit_crossed",
    "capture_failed",
    "record_not_found",
    "compliance_violation",
    "payment_pending_approval",
    "invalid_device",
    "invalid_email",
    "invalid_mobile_number",
    "invalid_user_details",
    "mismatch_in_transaction_details",
    "bank_account_validation_failed",
]


def _event(
    *, error_reason: str, error_code: str = "BAD_REQUEST_ERROR"
) -> RawFailureEvent:
    return RawFailureEvent(
        event_id=f"evt_{error_reason}",
        payment_id=f"pay_{error_reason}",
        customer_id="cust_taxonomy_test",
        amount_paise=100000,
        payment_rail=PaymentRail.CARD,
        error_code=error_code,
        error_reason=error_reason,
        occurred_at=datetime.now(UTC),
    )


@pytest.mark.parametrize("reason", INDETERMINATE_REASONS)
def test_indeterminate_reasons_escalate_without_retry(reason: str) -> None:
    result = classify_failure(_event(error_reason=reason))
    assert result.category == FailureCategory.INDETERMINATE_AUTHORIZATION
    assert result.requires_human_approval is True


@pytest.mark.parametrize("reason", TRANSIENT_REASONS)
def test_transient_reasons_route_to_passive_retry(reason: str) -> None:
    result = classify_failure(_event(error_reason=reason))
    assert result.category == FailureCategory.TRANSIENT_BANK_WINDOW


@pytest.mark.parametrize("reason", MANDATE_FAILURE_REASONS)
def test_mandate_failure_reasons_route_to_structural_mandate_failure(
    reason: str,
) -> None:
    result = classify_failure(_event(error_reason=reason))
    assert result.category == FailureCategory.STRUCTURAL_MANDATE_FAILURE


@pytest.mark.parametrize("reason", LIQUIDITY_REASONS)
def test_liquidity_reasons_route_to_liquidity_constraint(reason: str) -> None:
    result = classify_failure(_event(error_reason=reason))
    assert result.category == FailureCategory.LIQUIDITY_CONSTRAINT


@pytest.mark.parametrize("reason", CHECKOUT_DROPOFF_REASONS)
def test_checkout_dropoff_reasons_route_to_incentivized_link(reason: str) -> None:
    result = classify_failure(_event(error_reason=reason))
    assert result.category == FailureCategory.CHECKOUT_DROP_OFF


@pytest.mark.parametrize("reason", SYSTEMIC_REASONS)
def test_systemic_reasons_route_to_systemic_gateway_failure(reason: str) -> None:
    result = classify_failure(_event(error_reason=reason))
    assert result.category == FailureCategory.SYSTEMIC_GATEWAY_FAILURE


@pytest.mark.parametrize("reason", UNCLASSIFIED_REASONS)
def test_merchant_side_reasons_escalate_to_human_review(reason: str) -> None:
    result = classify_failure(_event(error_reason=reason))
    assert result.category == FailureCategory.UNCLASSIFIED
    assert result.requires_human_approval is True


def test_subscription_halted_error_code_routes_to_structural_mandate_failure() -> None:
    result = classify_failure(
        _event(error_reason="mandate_exhausted", error_code="SUBSCRIPTION_HALTED")
    )
    assert result.category == FailureCategory.STRUCTURAL_MANDATE_FAILURE


def test_every_documented_reason_is_covered_by_exactly_one_bucket() -> None:
    all_buckets = (
        INDETERMINATE_REASONS
        + TRANSIENT_REASONS
        + MANDATE_FAILURE_REASONS
        + LIQUIDITY_REASONS
        + CHECKOUT_DROPOFF_REASONS
        + SYSTEMIC_REASONS
        + UNCLASSIFIED_REASONS
    )
    assert len(all_buckets) == len(set(all_buckets)), (
        "a reason string appears in more than one bucket in this test file"
    )
