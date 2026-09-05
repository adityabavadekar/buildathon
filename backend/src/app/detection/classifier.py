"""Maps Razorpay gateway codes, sub-codes, and NPCI responses into root-cause
categories and bounded interventions by domain rule.
"""

from decimal import Decimal
from typing import Any, ClassVar

from app.core.constants import (
    CHECKOUT_DROP_OFF_LINK_VALIDITY_MINUTES,
    ESTABLISHED_CUSTOMER_CASE_COUNT,
    MIN_CONFIDENCE_THRESHOLD,
    RELIABLE_RECOVERY_RATE,
    REPEAT_LIQUIDITY_FAILURE_LIMIT,
)
from app.core.enums import FailureCategory, InterventionType, PaymentRail
from app.core.logging import get_logger
from app.detection.action_params import get_action_params
from app.detection.customer_profile import (
    CustomerProfile,
    get_customer_profile_registry,
)
from app.detection.models import DiagnosisResult, RawFailureEvent

logger = get_logger(__name__)


class FailureClassifier:
    """Classifies raw payment failure events into actionable root cause categories."""

    # Set of NPCI codes indicating transient window
    TRANSIENT_NPCI_CODES: ClassVar[set[str]] = {"XT", "XU", "XY"}
    # Error codes indicating transient bank / PSP timeout (not NPCI codes)
    TRANSIENT_ERROR_CODES: ClassVar[set[str]] = {
        "U30",
        "U31",
        "U32",
        "NB_SESSION_EXPIRED",
    }
    # A timeout never reports whether the authorization succeeded, so the payment
    # may already have gone through. Retrying is how you double-charge.
    INDETERMINATE_ERROR_CODES: ClassVar[set[str]] = {
        "GATEWAY_TIMEOUT",
        "REQUEST_TIMEOUT",
        "NETWORK_ERROR",
        "CONNECTION_RESET",
    }
    # NPCI codes indicating balance or liquidity
    LIQUIDITY_NPCI_CODES: ClassVar[set[str]] = {
        "AP15",
        "AP21",
        "U19",
        "U68",
        "ZM",
        "CARD_LIMIT_EXCEEDED",
        "ENACH_INSUFFICIENT_FUNDS",
    }
    # NPCI codes indicating structural mandate breakdown
    MANDATE_FAIL_NPCI_CODES: ClassVar[set[str]] = {
        "AP09",
        "AP10",
        "AP12",
        "AP24",
        "VA",
        "FL",
        "K1",
        "MD01",
        "MD02",
        "CARD_EXPIRED",
    }
    # Fleet-wide rail outage rather than a single customer's failure.
    SYSTEMIC_ERROR_CODES: ClassVar[set[str]] = {
        "GATEWAY_ERROR",
        "SERVER_ERROR",
        "INTERNAL_SERVER_ERROR",
        "NB_BANK_UNAVAILABLE",
        "UPI_PSP_DOWN",
    }
    CHECKOUT_ABANDON_ERROR_CODES: ClassVar[set[str]] = {
        "OTP_TIMEOUT",
        "UPI_COLLECT_DECLINED",
    }

    # Exact `error_reason` strings from razorpay.com/docs/errors/payments/list,
    # /upi, /cards, and /common, mapped into the existing 9-branch taxonomy.
    # Exact match, not substring: an exhaustive list is only trustworthy if a
    # near-miss reason falls through to UNCLASSIFIED rather than silently
    # matching the wrong category.
    RAZORPAY_INDETERMINATE_REASONS: ClassVar[set[str]] = {
        "payment_timed_out",
        "request_timed_out",
        "verification_failed",
        "invalid_response_from_gateway",
        "demed_transaction",
    }
    RAZORPAY_TRANSIENT_REASONS: ClassVar[set[str]] = {
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
    }
    RAZORPAY_MANDATE_FAILURE_REASONS: ClassVar[set[str]] = {
        "mandate_creation_declined",
        "mandate_creation_expired",
        "mandate_creation_failed",
        "mandate_creation_timeout",
        "funds_blocked_by_mandate",
        "reqauth_mandate_not_acknowledged",
        "recurring_payment_not_enabled",
    }
    RAZORPAY_LIQUIDITY_REASONS: ClassVar[set[str]] = {
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
    }
    RAZORPAY_CHECKOUT_DROPOFF_REASONS: ClassVar[set[str]] = {
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
    }
    # Customer/gateway/issuer-side declines with a known, specific cause but no
    # retry or mandate/liquidity remedy -- routed the same as a 5XX today
    # (PASSIVE_RETRY) since Razorpay's own guidance for nearly all of these is
    # "customer retries with a different card/method", not "wait and retry the
    # same one automatically". A future spec could split this into its own
    # branch; folding into SYSTEMIC_GATEWAY_FAILURE keeps this pass a mapping
    # exercise instead of a taxonomy redesign.
    RAZORPAY_SYSTEMIC_REASONS: ClassVar[set[str]] = {
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
    }

    def _is_indeterminate(self, code: str, reason: str) -> bool:
        """True when the authorization outcome is unknown rather than known-failed.

        A customer-side timeout (OTP abandoned) is a real decline and stays
        retryable; only an unanswered gateway leaves the outcome unknown.
        """
        if code in self.CHECKOUT_ABANDON_ERROR_CODES:
            return False
        if reason in self.RAZORPAY_INDETERMINATE_REASONS:
            return True
        return code in self.INDETERMINATE_ERROR_CODES or any(
            token in reason
            for token in (
                "gateway_timeout",
                "request_timed_out",
                "no_response",
                "network_error",
                "connection_reset",
            )
        )

    def _indeterminate_result(
        self, code: str, amt_inr: int, signals: dict[str, str]
    ) -> DiagnosisResult:
        """Route an unknown-outcome failure to a human instead of retrying it."""
        msg_en = f"Hi, we could not confirm the status of your INR {amt_inr} payment. Our team is verifying it before any further action."
        msg_hi = f"Namaste, INR {amt_inr} ke payment ki status confirm nahi ho payi. Humari team verify kar rahi hai."
        signals["dunning_message_en"] = msg_en
        signals["dunning_message_hi"] = msg_hi
        params = get_action_params(
            FailureCategory.INDETERMINATE_AUTHORIZATION,
            InterventionType.MANUAL_ESCALATION,
        )
        return DiagnosisResult(
            category=FailureCategory.INDETERMINATE_AUTHORIZATION,
            confidence=Decimal("0.90"),
            recommended_intervention=InterventionType.MANUAL_ESCALATION,
            recommended_delay_hours=params.delay_hours,
            discount_bps_suggested=params.discount_bps,
            recommended_channel=params.channel,
            reasoning=(
                f"Timeout or network failure (code: {code}) leaves the authorization "
                "outcome unknown: the payment may already have succeeded. Retrying "
                "risks charging the customer twice, so this is routed for "
                "reconciliation against the gateway before any retry."
            ),
            requires_human_approval=params.requires_human_approval,
            dunning_message_en=msg_en,
            dunning_message_hi=msg_hi,
            signals_evaluated=signals,
        )

    def _liquidity_result(
        self, event: RawFailureEvent, amt_inr: int, signals: dict[str, Any]
    ) -> DiagnosisResult:
        """Diagnose an insufficient-funds decline, weighted by customer history.

        A flat rule treats a first-time failure and a fourth identical one the
        same. Repeat failures against a thin history stop being a timing problem
        and become a solvency one, which a retry cannot fix.
        """
        profile = self._profile(event.customer_id)
        repeat = profile.repeat_failure_count if profile else 0
        history = profile.total_cases if profile else 0
        recovered_rate = profile.recovered_rate if profile else 0.0

        signals["customer_total_cases"] = history
        signals["customer_repeat_failures"] = repeat
        signals["customer_recovered_rate"] = recovered_rate

        established = history >= ESTABLISHED_CUSTOMER_CASE_COUNT
        reliable = recovered_rate >= RELIABLE_RECOVERY_RATE

        if repeat >= REPEAT_LIQUIDITY_FAILURE_LIMIT and not (established and reliable):
            weighting = (
                f"{repeat} prior liquidity failures against {history} case(s) of history "
                f"and a {recovered_rate:.0%} recovery rate: too thin to read this as a "
                "timing problem, so escalating rather than retrying into a decline."
            )
            msg_en = f"Hi, we could not collect INR {amt_inr}. Our team will reach out to arrange an alternative."
            msg_hi = f"Namaste, INR {amt_inr} collect nahi ho paya. Humari team aapse alternative arrange karne ke liye sampark karegi."
            signals["dunning_message_en"] = msg_en
            signals["dunning_message_hi"] = msg_hi
            params = get_action_params(
                FailureCategory.LIQUIDITY_CONSTRAINT, InterventionType.MANUAL_ESCALATION
            )
            return DiagnosisResult(
                category=FailureCategory.LIQUIDITY_CONSTRAINT,
                confidence=Decimal("0.75"),
                recommended_intervention=InterventionType.MANUAL_ESCALATION,
                recommended_delay_hours=params.delay_hours,
                discount_bps_suggested=params.discount_bps,
                recommended_channel=params.channel,
                reasoning=f"Declined due to insufficient liquidity. {weighting}",
                requires_human_approval=params.requires_human_approval,
                dunning_message_en=msg_en,
                dunning_message_hi=msg_hi,
                signals_evaluated=signals,
            )

        if repeat >= REPEAT_LIQUIDITY_FAILURE_LIMIT:
            weighting = (
                f"{repeat} prior liquidity failures, but {history} cases of history at a "
                f"{recovered_rate:.0%} recovery rate outweigh them: this customer pays, "
                "so the decline reads as timing and a spaced retry is still warranted."
            )
        elif history == 0:
            weighting = (
                "No prior history for this customer, so nothing outweighs the decline "
                "itself; treated as a first-occurrence timing failure."
            )
        else:
            weighting = (
                f"{repeat} prior liquidity failure(s) across {history} case(s): "
                "consistent with a timing rather than a solvency problem."
            )

        msg_en = f"Hello, your payment of INR {amt_inr} was declined due to insufficient balance. Auto-retry scheduled in 48h."
        msg_hi = f"Namaste, insufficient balance ki wajah se INR {amt_inr} ka payment decline hua. Auto-retry 48 ghante me hoga."
        signals["dunning_message_en"] = msg_en
        signals["dunning_message_hi"] = msg_hi
        params = get_action_params(
            FailureCategory.LIQUIDITY_CONSTRAINT, InterventionType.SMART_RETRY
        )
        return DiagnosisResult(
            category=FailureCategory.LIQUIDITY_CONSTRAINT,
            confidence=Decimal("0.90"),
            recommended_intervention=InterventionType.SMART_RETRY,
            recommended_delay_hours=params.delay_hours,
            discount_bps_suggested=params.discount_bps,
            recommended_channel=params.channel,
            reasoning=(
                "Declined due to insufficient account liquidity. Retry spaced "
                f"{params.delay_hours}h to align with liquidity windows. "
                f"{weighting}"
            ),
            requires_human_approval=params.requires_human_approval,
            dunning_message_en=msg_en,
            dunning_message_hi=msg_hi,
            signals_evaluated=signals,
        )

    def _profile(self, customer_id: str) -> CustomerProfile | None:
        """Customer history, or None when it cannot be read.

        Diagnosis must still produce a verdict if the profile lookup fails, so a
        failure degrades to the no-history path rather than raising.
        """
        if not customer_id:
            return None
        try:
            return get_customer_profile_registry().get_profile(customer_id)
        except Exception:  # noqa: BLE001
            logger.warning("classifier.profile_lookup_failed", customer_id=customer_id)
            return None

    def classify(self, event: RawFailureEvent) -> DiagnosisResult:  # noqa: PLR0911, PLR0915
        """Classify a failure event using error codes, reason sub-codes, and NPCI codes."""
        reason = (event.error_reason or "").lower()
        code = (event.error_code or "").upper()
        step = (event.error_step or "").lower()
        source = (event.error_source or "").lower()
        npci = (event.npci_response_code or "").upper()

        signals = {
            "error_code": code,
            "error_reason": reason,
            "error_step": step,
            "error_source": source,
            "npci_code": npci,
        }

        amt_inr = event.amount_paise // 100

        # 1. B2B Overdue Receivables
        if (
            "b2b" in reason
            or "invoice_past_due" in reason
            or "overdue" in reason
            or event.payment_rail == PaymentRail.B2B_INVOICE
        ):
            # payment_id is an internal id, not an invoice number a customer
            # recognizes -- prefer the merchant-supplied reference if present.
            invoice_ref = event.invoice_id or event.reference_id or event.payment_id
            msg_en = f"Dear Customer, invoice #{invoice_ref} for INR {amt_inr} is overdue. Please complete settlement securely."
            msg_hi = f"Priy Grahak, invoice #{invoice_ref} (INR {amt_inr}) overdue hai. Kripya diye gaye link se payment karein."
            signals["dunning_message_en"] = msg_en
            signals["dunning_message_hi"] = msg_hi
            params = get_action_params(
                FailureCategory.B2B_RECEIVABLES_OVERDUE,
                InterventionType.B2B_INVOICE_CHASER,
            )
            return DiagnosisResult(
                category=FailureCategory.B2B_RECEIVABLES_OVERDUE,
                confidence=Decimal("0.92"),
                recommended_intervention=InterventionType.B2B_INVOICE_CHASER,
                recommended_delay_hours=params.delay_hours,
                discount_bps_suggested=params.discount_bps,
                recommended_channel=params.channel,
                reasoning=(
                    "B2B net-terms receivable past due date. "
                    "Automated multi-channel reconciliation dunning initiated with single-click payment link."
                ),
                requires_human_approval=params.requires_human_approval,
                dunning_message_en=msg_en,
                dunning_message_hi=msg_hi,
                signals_evaluated=signals,
            )

        # 2. Promise to Pay (P2P) Grace Period
        if (
            "promise_to_pay" in reason
            or "p2p" in reason
            or "customer_promised" in reason
            or "grace_period" in reason
            or code == "P2P_PROMISED"
        ):
            msg_en = f"Hi, this is a reminder regarding your scheduled payment of INR {amt_inr}. Complete it at your convenience."
            msg_hi = f"Namaste, aapke INR {amt_inr} payment ka scheduled reminder. Kripya diye gaye link se payment poora karein."
            signals["dunning_message_en"] = msg_en
            signals["dunning_message_hi"] = msg_hi
            params = get_action_params(
                FailureCategory.PROMISE_TO_PAY_DELAY, InterventionType.P2P_FOLLOWUP
            )
            return DiagnosisResult(
                category=FailureCategory.PROMISE_TO_PAY_DELAY,
                confidence=Decimal("0.90"),
                recommended_intervention=InterventionType.P2P_FOLLOWUP,
                recommended_delay_hours=params.delay_hours,
                discount_bps_suggested=params.discount_bps,
                recommended_channel=params.channel,
                reasoning=(
                    "Customer explicitly committed to pay by scheduled date. "
                    "Aggressive automated retries paused; scheduled gentle verification follow-up."
                ),
                requires_human_approval=params.requires_human_approval,
                dunning_message_en=msg_en,
                dunning_message_hi=msg_hi,
                signals_evaluated=signals,
            )

        # 3. Indeterminate authorization: outcome unknown, so never auto-retry.
        if self._is_indeterminate(code, reason):
            return self._indeterminate_result(code, amt_inr, signals)

        # 4. Transient Banking Window / CBS Cutoff
        if (
            npci in self.TRANSIENT_NPCI_CODES
            or code in self.TRANSIENT_ERROR_CODES
            or reason in self.RAZORPAY_TRANSIENT_REASONS
            or "cutoff" in reason
            or "bank_cutoff" in reason
            or "bank_technical_error" in reason
            or "temporarily_unavailable" in reason
            or (source == "bank" and "down" in reason)
        ):
            msg_en = f"Hi, your payment of INR {amt_inr} was delayed due to temporary bank network lag. We will auto-retry shortly."
            msg_hi = f"Namaste, bank server me temporary issue ke karan INR {amt_inr} ka payment delay hua. Hum jald auto-retry karenge."
            signals["dunning_message_en"] = msg_en
            signals["dunning_message_hi"] = msg_hi
            params = get_action_params(
                FailureCategory.TRANSIENT_BANK_WINDOW, InterventionType.PASSIVE_RETRY
            )
            return DiagnosisResult(
                category=FailureCategory.TRANSIENT_BANK_WINDOW,
                confidence=Decimal("0.95"),
                recommended_intervention=InterventionType.PASSIVE_RETRY,
                recommended_delay_hours=params.delay_hours,
                discount_bps_suggested=params.discount_bps,
                recommended_channel=params.channel,
                reasoning=(
                    "Failure is attributed to transient bank CBS cutoff or temporary network lag. "
                    "Background passive retry scheduled after the standard banking window."
                ),
                requires_human_approval=params.requires_human_approval,
                dunning_message_en=msg_en,
                dunning_message_hi=msg_hi,
                signals_evaluated=signals,
            )

        # 5. Structural Mandate Failure
        if (
            npci in self.MANDATE_FAIL_NPCI_CODES
            or code in self.MANDATE_FAIL_NPCI_CODES
            or reason in self.RAZORPAY_MANDATE_FAILURE_REASONS
            or "mandate_revoked" in reason
            or "mandate_inactive" in reason
            or "mandate_exhausted" in reason
            or "funds_blocked_by_mandate" in reason
            or "account_closed" in reason
            or "invalid_mandate" in reason
            or code == "SUBSCRIPTION_HALTED"
        ):
            msg_en = f"Hello, your auto-debit of INR {amt_inr} was interrupted. Please update your mandate or pay securely here."
            msg_hi = f"Namaste, mandate issue ki wajah se aapka INR {amt_inr} ka auto-debit nahi ho paya. Kripya yahan pay karein."
            signals["dunning_message_en"] = msg_en
            signals["dunning_message_hi"] = msg_hi
            params = get_action_params(
                FailureCategory.STRUCTURAL_MANDATE_FAILURE,
                InterventionType.SMART_PAYMENT_LINK,
            )
            return DiagnosisResult(
                category=FailureCategory.STRUCTURAL_MANDATE_FAILURE,
                confidence=Decimal("0.95"),
                recommended_intervention=InterventionType.SMART_PAYMENT_LINK,
                recommended_delay_hours=params.delay_hours,
                discount_bps_suggested=params.discount_bps,
                recommended_channel=params.channel,
                reasoning=(
                    "Mandate is structurally invalid, revoked, or halted. "
                    "Auto-debit stopped; immediate smart fallback payment link issued to customer."
                ),
                requires_human_approval=params.requires_human_approval,
                dunning_message_en=msg_en,
                dunning_message_hi=msg_hi,
                signals_evaluated=signals,
            )

        # 6. Liquidity Constraint / Insufficient Funds
        if (
            npci in self.LIQUIDITY_NPCI_CODES
            or code in self.LIQUIDITY_NPCI_CODES
            or reason in self.RAZORPAY_LIQUIDITY_REASONS
            or "insufficient_funds" in reason
            or "debit_declined" in reason
            or "credit_limit_exceeded" in reason
            or "balance" in reason
        ):
            return self._liquidity_result(event, amt_inr, signals)

        # 7. Checkout Drop-off / Authentication Failure
        if (
            code in self.CHECKOUT_ABANDON_ERROR_CODES
            or reason in self.RAZORPAY_CHECKOUT_DROPOFF_REASONS
            or "otp_timeout" in reason
            or "authentication_failed" in reason
            or "payment_cancelled" in reason
            or "timed_out" in reason
            or step == "payment_authentication"
            or (source == "customer" and "cancelled" in reason)
        ):
            msg_en = f"Hi, your recent checkout of INR {amt_inr} was interrupted. Complete your payment with an instant 5% discount!"
            msg_hi = f"Namaste, aapka INR {amt_inr} ka checkout poora nahi ho paya. Abhi pay karein aur 5% discount payein!"
            signals["dunning_message_en"] = msg_en
            signals["dunning_message_hi"] = msg_hi
            params = get_action_params(
                FailureCategory.CHECKOUT_DROP_OFF, InterventionType.INCENTIVIZED_LINK
            )
            return DiagnosisResult(
                category=FailureCategory.CHECKOUT_DROP_OFF,
                confidence=Decimal("0.85"),
                recommended_intervention=InterventionType.INCENTIVIZED_LINK,
                recommended_delay_hours=params.delay_hours,
                discount_bps_suggested=params.discount_bps,
                recommended_channel=params.channel,
                reasoning=(
                    "Customer dropped off during checkout or 2FA authentication. "
                    f"Dispatched short-lived ({CHECKOUT_DROP_OFF_LINK_VALIDITY_MINUTES}m) fallback link with time-decay incentive."
                ),
                requires_human_approval=params.requires_human_approval,
                dunning_message_en=msg_en,
                dunning_message_hi=msg_hi,
                signals_evaluated=signals,
            )

        # 8. Systemic Gateway 5XX Error
        if (
            code in self.SYSTEMIC_ERROR_CODES
            or reason in self.RAZORPAY_SYSTEMIC_REASONS
            or source == "gateway"
        ):
            msg_en = f"Hi, your payment of INR {amt_inr} experienced a technical gateway issue. We are automatically retrying."
            msg_hi = f"Namaste, gateway error ke karan INR {amt_inr} ka payment ruk gaya tha. Hum auto-retry kar rahe hain."
            signals["dunning_message_en"] = msg_en
            signals["dunning_message_hi"] = msg_hi
            params = get_action_params(
                FailureCategory.SYSTEMIC_GATEWAY_FAILURE, InterventionType.PASSIVE_RETRY
            )
            return DiagnosisResult(
                category=FailureCategory.SYSTEMIC_GATEWAY_FAILURE,
                confidence=Decimal("0.80"),
                recommended_intervention=InterventionType.PASSIVE_RETRY,
                recommended_delay_hours=params.delay_hours,
                discount_bps_suggested=params.discount_bps,
                recommended_channel=params.channel,
                reasoning=(
                    "Gateway reported internal processing error or 5XX status. "
                    "Passive retry scheduled with 1-hour backoff."
                ),
                requires_human_approval=params.requires_human_approval,
                dunning_message_en=msg_en,
                dunning_message_hi=msg_hi,
                signals_evaluated=signals,
            )

        # 9. Unclassified / Low Confidence -> Escalation
        msg_en = f"Hi, your payment of INR {amt_inr} could not be processed. Our support team is reviewing your transaction."
        msg_hi = f"Namaste, INR {amt_inr} ka payment process nahi ho paya. Humari support team review kar rahi hai."
        signals["dunning_message_en"] = msg_en
        signals["dunning_message_hi"] = msg_hi
        params = get_action_params(
            FailureCategory.UNCLASSIFIED, InterventionType.MANUAL_ESCALATION
        )
        return DiagnosisResult(
            category=FailureCategory.UNCLASSIFIED,
            confidence=MIN_CONFIDENCE_THRESHOLD,
            recommended_intervention=InterventionType.MANUAL_ESCALATION,
            recommended_delay_hours=params.delay_hours,
            discount_bps_suggested=params.discount_bps,
            recommended_channel=params.channel,
            reasoning=(
                f"Unrecognized error pattern (code: {code}, reason: {reason}). "
                "Confidence is low; routing to human operations queue for review."
            ),
            requires_human_approval=params.requires_human_approval,
            dunning_message_en=msg_en,
            dunning_message_hi=msg_hi,
            signals_evaluated=signals,
        )


_default_classifier = FailureClassifier()


def classify_failure(event: RawFailureEvent) -> DiagnosisResult:
    """Classify a raw payment failure event using default taxonomy rules."""
    return _default_classifier.classify(event)
