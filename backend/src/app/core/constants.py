"""Core constants for financial calculations, dunning policies, and recovery bounds.

All monetary constants are defined in minor units (paise) to prevent float inaccuracies.
"""

from decimal import Decimal

# Currency
DEFAULT_CURRENCY = "INR"

# Economics and Costs (Paise)
GATEWAY_RETRY_COST_PAISE: int = 250  # INR 2.50 per failed or retried payment attempt
OUTREACH_WHATSAPP_COST_PAISE: int = 50  # INR 0.50 per WhatsApp Business notification
OUTREACH_SMS_COST_PAISE: int = 20  # INR 0.20 per SMS message
OUTREACH_EMAIL_COST_PAISE: int = 5  # INR 0.05 per transactional email
OUTREACH_VOICE_COST_PAISE: int = 150  # INR 1.50 per automated voice recovery call

# Policy Invariants and Guardrails
DEFAULT_MAX_DUNNING_TOUCHES: int = 3
DEFAULT_MIN_COOLDOWN_HOURS: int = 24
DEFAULT_MAX_DISCOUNT_BPS: int = (
    1000  # 10.00% maximum incentive discount (1000 basis points)
)
DEFAULT_HOLDOUT_PERCENTAGE: int = (
    10  # 10% held-out control group for counterfactual baseline
)
MIN_CONFIDENCE_THRESHOLD: Decimal = Decimal(
    "0.60"
)  # Minimum AI confidence before escalation

# Default model served on Groq and used for agentic recovery simulation. This is
# the single canonical value; every consumer reads it from Settings, never from
# its own literal.
DEFAULT_AGENTIC_MODEL: str = "meta-llama/llama-4-scout-17b-16e-instruct"

DEFAULT_ANTHROPIC_MODEL: str = "claude-opus-5"

# Synthetic case id for audit rows describing system-wide actions rather than a
# single recovery case. Deliberately not a foreign key into cases.
GLOBAL_AUDIT_CASE_ID: str = "SYSTEM_GLOBAL"

# Time Windows (Hours / Minutes)
TRANSIENT_BANK_WINDOW_DELAY_HOURS: int = 4
SALARY_CYCLE_RETRY_SPACING_HOURS: int = 48
CHECKOUT_DROP_OFF_LINK_VALIDITY_MINUTES: int = 15
MAX_DUNNING_LIFECYCLE_DAYS: int = 7

# Pagination and Batch limits
DEFAULT_BATCH_PAGE_SIZE: int = 50
MAX_BATCH_EVALUATION_SIZE: int = 500
