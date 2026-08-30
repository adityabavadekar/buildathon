"""Contextual failure classifier for mapping payment errors into recovery actions.

Maps Razorpay gateway codes, sub-codes, and NPCI response codes into structured
root-cause categories and bounded interventions based on domain rules.
"""

from decimal import Decimal
from typing import ClassVar

from app.core.constants import (
    CHECKOUT_DROP_OFF_LINK_VALIDITY_MINUTES,
    MIN_CONFIDENCE_THRESHOLD,
    SALARY_CYCLE_RETRY_SPACING_HOURS,
    TRANSIENT_BANK_WINDOW_DELAY_HOURS,
)
from app.core.enums import FailureCategory, InterventionType
from app.detection.models import DiagnosisResult, RawFailureEvent


class FailureClassifier:
    """Classifies raw payment failure events into actionable root cause categories."""

    # Set of NPCI codes indicating transient window
    TRANSIENT_NPCI_CODES: ClassVar[set[str]] = {"XT", "XU", "XY"}
    # NPCI codes indicating balance or liquidity
    LIQUIDITY_NPCI_CODES: ClassVar[set[str]] = {"AP15", "AP21", "U19", "U68", "ZM"}
    # NPCI codes indicating structural mandate breakdown
    MANDATE_FAIL_NPCI_CODES: ClassVar[set[str]] = {
        "AP09",
        "AP10",
        "AP24",
        "VA",
        "FL",
        "K1",
        "MD01",
        "MD02",
    }

    def classify(self, event: RawFailureEvent) -> DiagnosisResult:
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

        # 1. Transient Banking Window / CBS Cutoff
        if (
            npci in self.TRANSIENT_NPCI_CODES
            or "cutoff" in reason
            or "bank_cutoff" in reason
            or "bank_technical_error" in reason
            or "temporarily_unavailable" in reason
            or (source == "bank" and "down" in reason)
        ):
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
                signals_evaluated=signals,
            )

        # 2. Structural Mandate Failure
        if (
            npci in self.MANDATE_FAIL_NPCI_CODES
            or "mandate_revoked" in reason
            or "mandate_inactive" in reason
            or "funds_blocked_by_mandate" in reason
            or "account_closed" in reason
            or "invalid_mandate" in reason
        ):
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
                signals_evaluated=signals,
            )

        # 3. Liquidity Constraint / Insufficient Funds
        if (
            npci in self.LIQUIDITY_NPCI_CODES
            or "insufficient_funds" in reason
            or "debit_declined" in reason
            or "credit_limit_exceeded" in reason
            or "balance" in reason
        ):
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
                signals_evaluated=signals,
            )

        # 4. Checkout Drop-off / Authentication Failure
        if (
            "otp_timeout" in reason
            or "authentication_failed" in reason
            or "payment_cancelled" in reason
            or "timed_out" in reason
            or step == "payment_authentication"
            or (source == "customer" and "cancelled" in reason)
        ):
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
                signals_evaluated=signals,
            )

        # 5. Systemic Gateway 5XX Error
        if (
            code in {"GATEWAY_ERROR", "SERVER_ERROR", "INTERNAL_SERVER_ERROR"}
            or source == "gateway"
        ):
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
                signals_evaluated=signals,
            )

        # 6. Unclassified / Low Confidence -> Escalation
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
            signals_evaluated=signals,
        )
