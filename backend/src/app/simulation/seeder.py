"""Synthetic cohort generator and recovery simulation harness.

Seeds realistic transaction failures across all major Indian payment rails
(UPI, e-Mandates, Cards, Invoices) and simulates recovery outcomes against
a 10% unassisted holdout control arm.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.audit.repository import get_case_repository
from app.core.enums import (
    ExperimentArm,
    FailureCategory,
    PaymentRail,
    RecoveryState,
)
from app.detection.models import RawFailureEvent
from app.intervention.orchestrator import get_recovery_orchestrator

HOLDOUT_NATURAL_RECOVERY_RATE = 0.12
TRANSIENT_RECOVERY_RATE = 0.72
CHECKOUT_DROP_OFF_RECOVERY_RATE = 0.44
LIQUIDITY_RECOVERY_RATE = 0.38
DEFAULT_RECOVERY_RATE = 0.25

FAILURE_TEMPLATES: list[dict[str, Any]] = [
    {
        "rail": PaymentRail.UPI,
        "category": FailureCategory.TRANSIENT_BANK_WINDOW,
        "error_code": "XT",
        "error_reason": "Bank system downtime / switch cutoff window",
        "amounts": [19900, 49900, 99900, 149900],
    },
    {
        "rail": PaymentRail.UPI,
        "category": FailureCategory.TRANSIENT_BANK_WINDOW,
        "error_code": "U30",
        "error_reason": "PSP bank timeout during collect request",
        "amounts": [29900, 79900, 129900, 249900],
    },
    {
        "rail": PaymentRail.UPI_AUTOPAY,
        "category": FailureCategory.LIQUIDITY_CONSTRAINT,
        "error_code": "AP15",
        "error_reason": "Insufficient balance in account for debit mandate",
        "amounts": [99900, 199900, 499900, 999900],
    },
    {
        "rail": PaymentRail.ENACH,
        "category": FailureCategory.STRUCTURAL_MANDATE_FAILURE,
        "error_code": "AP09",
        "error_reason": "Mandate revoked or account frozen at sponsor bank",
        "amounts": [149900, 299900, 599900],
    },
    {
        "rail": PaymentRail.CARD,
        "category": FailureCategory.CHECKOUT_DROP_OFF,
        "error_code": "OTP_TIMEOUT",
        "error_reason": "Customer abandoned checkout at 3DS OTP verification",
        "amounts": [249900, 499900, 899900, 1500000],
    },
    {
        "rail": PaymentRail.CARD,
        "category": FailureCategory.TRANSIENT_BANK_WINDOW,
        "error_code": "GATEWAY_TIMEOUT",
        "error_reason": "Issuing bank network timed out during authorization",
        "amounts": [39900, 89900, 189900],
    },
    {
        "rail": PaymentRail.B2B_INVOICE,
        "category": FailureCategory.B2B_RECEIVABLES_OVERDUE,
        "error_code": "OVERDUE_RECEIVABLE",
        "error_reason": "Net-30 B2B invoice past due date; automated dunning chaser",
        "amounts": [5000000, 12000000, 25000000, 75000000],
    },
    {
        "rail": PaymentRail.UPI,
        "category": FailureCategory.PROMISE_TO_PAY_DELAY,
        "error_code": "P2P_PROMISED",
        "error_reason": "Customer committed to pay by promised salary credit date",
        "amounts": [49900, 149900, 299900],
    },
]

CUSTOMER_NAMES: list[tuple[str, str, str]] = [
    ("cust_rahul_sharma", "+919876500001", "rahul.s@example.com"),
    ("cust_priya_patel", "+919876500002", "priya.p@example.com"),
    ("cust_amit_verma", "+919876500003", "amit.v@example.com"),
    ("cust_deepa_nair", "+919876500004", "deepa.n@example.com"),
    ("cust_vikram_singh", "+919876500005", "vikram.s@example.com"),
    ("cust_sneha_reddy", "+919876500006", "sneha.r@example.com"),
    ("cust_rohit_gupta", "+919876500007", "rohit.g@example.com"),
    ("cust_ananya_das", "+919876500008", "ananya.d@example.com"),
]


def _pseudo_random_float() -> float:
    """Generate uniform random float in [0, 1) using secrets."""
    return secrets.randbelow(10000) / 10000.0


async def seed_simulation_batch(
    count: int = 50,
    simulate_resolutions: bool = True,
) -> dict[str, Any]:
    """Generate N realistic failure events and simulate recovery outcomes."""
    orchestrator = get_recovery_orchestrator()
    seeded_cases: list[str] = []
    recovered_count = 0
    now = datetime.now(UTC)

    for _ in range(count):
        template = secrets.choice(FAILURE_TEMPLATES)
        cust = secrets.choice(CUSTOMER_NAMES)
        amount = secrets.choice(template["amounts"])

        # Stagger occurrence times over past 48 hours (10 to 2880 mins)
        minutes_ago = 10 + secrets.randbelow(2870)
        occurred_at = now - timedelta(minutes=minutes_ago)

        event = RawFailureEvent(
            event_id=f"evt_sim_{uuid4().hex[:12]}",
            payment_id=f"pay_sim_{uuid4().hex[:14]}",
            customer_id=cust[0],
            amount_paise=amount,
            currency="INR",
            payment_rail=template["rail"],
            error_code=template["error_code"],
            error_description=template["error_reason"],
            error_reason=template["error_reason"],
            npci_response_code=template["error_code"]
            if "AP" in template["error_code"] or template["error_code"] == "XT"
            else None,
            occurred_at=occurred_at,
            metadata={"source": "simulation"},
        )

        case = await orchestrator.process_failure(event)
        seeded_cases.append(case.case_id)

        # Simulate natural or intervention-assisted resolution
        if simulate_resolutions:
            rand_val = _pseudo_random_float()
            if case.experiment_arm == ExperimentArm.HOLDOUT_CONTROL:
                should_recover = rand_val < HOLDOUT_NATURAL_RECOVERY_RATE
            elif template["category"] == FailureCategory.TRANSIENT_BANK_WINDOW:
                should_recover = rand_val < TRANSIENT_RECOVERY_RATE
            elif template["category"] == FailureCategory.CHECKOUT_DROP_OFF:
                should_recover = rand_val < CHECKOUT_DROP_OFF_RECOVERY_RATE
            elif template["category"] == FailureCategory.LIQUIDITY_CONSTRAINT:
                should_recover = rand_val < LIQUIDITY_RECOVERY_RATE
            else:
                should_recover = rand_val < DEFAULT_RECOVERY_RATE

            if should_recover and case.state != RecoveryState.ESCALATED:
                capture_id = f"pay_cap_{uuid4().hex[:12]}"
                rec_amount = case.amount_paise
                orchestrator.process_payment_captured(
                    payment_id=case.failure_event.payment_id,
                    amount_paise=rec_amount,
                    gateway_capture_id=capture_id,
                )
                recovered_count += 1

    return {
        "seeded_count": len(seeded_cases),
        "recovered_count": recovered_count,
        "case_ids": seeded_cases[:10],
    }


def reset_simulation_data() -> dict[str, str]:
    """Clear all cases and reset the in-memory repository."""
    repo = get_case_repository()
    repo.clear()
    return {"status": "cleared", "message": "Simulation data reset successfully"}
