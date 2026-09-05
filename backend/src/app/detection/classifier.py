"""Maps Razorpay gateway codes, sub-codes, and NPCI responses into root-cause
categories and bounded interventions by domain rule.
"""

from decimal import Decimal
from typing import ClassVar

from app.core.constants import (
    CHECKOUT_DROP_OFF_LINK_VALIDITY_MINUTES,
    MIN_CONFIDENCE_THRESHOLD,
    SALARY_CYCLE_RETRY_SPACING_HOURS,
    TRANSIENT_BANK_WINDOW_DELAY_HOURS,
)
from app.core.enums import FailureCategory, InterventionType, PaymentRail
from app.detection.models import DiagnosisResult, RawFailureEvent


class FailureClassifier:
    """Classifies raw payment failure events into actionable root cause categories."""

    # Set of NPCI codes indicating transient window
    TRANSIENT_NPCI_CODES: ClassVar[set[str]] = {"XT", "XU", "XY"}
    # Error codes indicating transient bank / PSP timeout (not NPCI codes)
    TRANSIENT_ERROR_CODES: ClassVar[set[str]] = {
        "U30",
        "U31",
        "U32",
        "GATEWAY_TIMEOUT",
        "NB_SESSION_EXPIRED",
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

    def classify(self, event: RawFailureEvent) -> DiagnosisResult:  # noqa: PLR0911
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
            msg_en = f"Dear Customer, invoice #{event.payment_id} for INR {amt_inr} is overdue. Please complete settlement securely."
            msg_hi = f"Priy Grahak, invoice #{event.payment_id} (INR {amt_inr}) overdue hai. Kripya diye gaye link se payment karein."
            signals["dunning_message_en"] = msg_en
            signals["dunning_message_hi"] = msg_hi
            return DiagnosisResult(
                category=FailureCategory.B2B_RECEIVABLES_OVERDUE,
                confidence=Decimal("0.92"),
                recommended_intervention=InterventionType.B2B_INVOICE_CHASER,
                recommended_delay_hours=24,
                discount_bps_suggested=0,
                reasoning=(
                    "B2B net-terms receivable past due date. "
                    "Automated multi-channel reconciliation dunning initiated with single-click payment link."
                ),
                requires_human_approval=False,
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
            return DiagnosisResult(
                category=FailureCategory.PROMISE_TO_PAY_DELAY,
                confidence=Decimal("0.90"),
                recommended_intervention=InterventionType.P2P_FOLLOWUP,
                recommended_delay_hours=72,
                discount_bps_suggested=0,
                reasoning=(
                    "Customer explicitly committed to pay by scheduled date. "
                    "Aggressive automated retries paused; scheduled gentle verification follow-up."
                ),
                requires_human_approval=False,
                dunning_message_en=msg_en,
                dunning_message_hi=msg_hi,
                signals_evaluated=signals,
            )

        # 3. Transient Banking Window / CBS Cutoff
        if (
            npci in self.TRANSIENT_NPCI_CODES
            or code in self.TRANSIENT_ERROR_CODES
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
            return DiagnosisResult(
                category=FailureCategory.TRANSIENT_BANK_WINDOW,
                confidence=Decimal("0.95"),
                recommended_intervention=InterventionType.PASSIVE_RETRY,
                recommended_delay_hours=TRANSIENT_BANK_WINDOW_DELAY_HOURS,
                discount_bps_suggested=0,
                reasoning=(
                    "Failure is attributed to transient bank CBS cutoff or temporary network lag. "
                    "Background passive retry scheduled after the standard banking window."
                ),
                requires_human_approval=False,
                dunning_message_en=msg_en,
                dunning_message_hi=msg_hi,
                signals_evaluated=signals,
            )

        # 4. Structural Mandate Failure
        if (
            npci in self.MANDATE_FAIL_NPCI_CODES
            or code in self.MANDATE_FAIL_NPCI_CODES
            or "mandate_revoked" in reason
            or "mandate_inactive" in reason
            or "funds_blocked_by_mandate" in reason
            or "account_closed" in reason
            or "invalid_mandate" in reason
        ):
            msg_en = f"Hello, your auto-debit of INR {amt_inr} was interrupted. Please update your mandate or pay securely here."
            msg_hi = f"Namaste, mandate issue ki wajah se aapka INR {amt_inr} ka auto-debit nahi ho paya. Kripya yahan pay karein."
            signals["dunning_message_en"] = msg_en
            signals["dunning_message_hi"] = msg_hi
            return DiagnosisResult(
                category=FailureCategory.STRUCTURAL_MANDATE_FAILURE,
                confidence=Decimal("0.95"),
                recommended_intervention=InterventionType.SMART_PAYMENT_LINK,
                recommended_delay_hours=0,
                discount_bps_suggested=0,
                reasoning=(
                    "Mandate is structurally invalid, revoked, or halted. "
                    "Auto-debit stopped; immediate smart fallback payment link issued to customer."
                ),
                requires_human_approval=False,
                dunning_message_en=msg_en,
                dunning_message_hi=msg_hi,
                signals_evaluated=signals,
            )

        # 5. Liquidity Constraint / Insufficient Funds
        if (
            npci in self.LIQUIDITY_NPCI_CODES
            or code in self.LIQUIDITY_NPCI_CODES
            or "insufficient_funds" in reason
            or "debit_declined" in reason
            or "credit_limit_exceeded" in reason
            or "balance" in reason
        ):
            msg_en = f"Hello, your payment of INR {amt_inr} was declined due to insufficient balance. Auto-retry scheduled in 48h."
            msg_hi = f"Namaste, insufficient balance ki wajah se INR {amt_inr} ka payment decline hua. Auto-retry 48 ghante me hoga."
            signals["dunning_message_en"] = msg_en
            signals["dunning_message_hi"] = msg_hi
            return DiagnosisResult(
                category=FailureCategory.LIQUIDITY_CONSTRAINT,
                confidence=Decimal("0.90"),
                recommended_intervention=InterventionType.SMART_RETRY,
                recommended_delay_hours=SALARY_CYCLE_RETRY_SPACING_HOURS,
                discount_bps_suggested=0,
                reasoning=(
                    "Declined due to insufficient account liquidity. "
                    "Scheduled retry with minimum 48h spacing aligned with liquidity windows."
                ),
                requires_human_approval=False,
                dunning_message_en=msg_en,
                dunning_message_hi=msg_hi,
                signals_evaluated=signals,
            )

        # 6. Checkout Drop-off / Authentication Failure
        if (
            code in self.CHECKOUT_ABANDON_ERROR_CODES
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
            return DiagnosisResult(
                category=FailureCategory.CHECKOUT_DROP_OFF,
                confidence=Decimal("0.85"),
                recommended_intervention=InterventionType.INCENTIVIZED_LINK,
                recommended_delay_hours=0,
                discount_bps_suggested=500,  # 5.00% discount
                reasoning=(
                    "Customer dropped off during checkout or 2FA authentication. "
                    f"Dispatched short-lived ({CHECKOUT_DROP_OFF_LINK_VALIDITY_MINUTES}m) fallback link with time-decay incentive."
                ),
                requires_human_approval=False,
                dunning_message_en=msg_en,
                dunning_message_hi=msg_hi,
                signals_evaluated=signals,
            )

        # 7. Systemic Gateway 5XX Error
        if code in self.SYSTEMIC_ERROR_CODES or source == "gateway":
            msg_en = f"Hi, your payment of INR {amt_inr} experienced a technical gateway issue. We are automatically retrying."
            msg_hi = f"Namaste, gateway error ke karan INR {amt_inr} ka payment ruk gaya tha. Hum auto-retry kar rahe hain."
            signals["dunning_message_en"] = msg_en
            signals["dunning_message_hi"] = msg_hi
            return DiagnosisResult(
                category=FailureCategory.SYSTEMIC_GATEWAY_FAILURE,
                confidence=Decimal("0.80"),
                recommended_intervention=InterventionType.PASSIVE_RETRY,
                recommended_delay_hours=1,
                discount_bps_suggested=0,
                reasoning=(
                    "Gateway reported internal processing error or 5XX status. "
                    "Passive retry scheduled with 1-hour backoff."
                ),
                requires_human_approval=False,
                dunning_message_en=msg_en,
                dunning_message_hi=msg_hi,
                signals_evaluated=signals,
            )

        # 8. Unclassified / Low Confidence -> Escalation
        msg_en = f"Hi, your payment of INR {amt_inr} could not be processed. Our support team is reviewing your transaction."
        msg_hi = f"Namaste, INR {amt_inr} ka payment process nahi ho paya. Humari support team review kar rahi hai."
        signals["dunning_message_en"] = msg_en
        signals["dunning_message_hi"] = msg_hi
        return DiagnosisResult(
            category=FailureCategory.UNCLASSIFIED,
            confidence=MIN_CONFIDENCE_THRESHOLD,
            recommended_intervention=InterventionType.MANUAL_ESCALATION,
            recommended_delay_hours=0,
            discount_bps_suggested=0,
            reasoning=(
                f"Unrecognized error pattern (code: {code}, reason: {reason}). "
                "Confidence is low; routing to human operations queue for review."
            ),
            requires_human_approval=True,
            dunning_message_en=msg_en,
            dunning_message_hi=msg_hi,
            signals_evaluated=signals,
        )


_default_classifier = FailureClassifier()


def classify_failure(event: RawFailureEvent) -> DiagnosisResult:
    """Classify a raw payment failure event using default taxonomy rules."""
    return _default_classifier.classify(event)
