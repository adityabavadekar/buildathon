"""Core constants for financial calculations, dunning policies, and recovery bounds.

All monetary constants are defined in minor units (paise) to prevent float inaccuracies.
"""

from decimal import Decimal

# Currency
DEFAULT_CURRENCY = "INR"

# Operator authentication. A merchant deployment that never sets
# APP_OPERATOR_PASSWORD must still be gated -- an unauthenticated payments
# dashboard is not an acceptable default. This value is public (it is in this
# source file); every operator must change it before going live.
DEFAULT_OPERATOR_PASSWORD: str = "admin"  # noqa: S105

# Economics and Costs (Paise)
GATEWAY_RETRY_COST_PAISE: int = 250  # INR 2.50 per failed or retried payment attempt
OUTREACH_WHATSAPP_COST_PAISE: int = 50  # INR 0.50 per WhatsApp Business notification
OUTREACH_SMS_COST_PAISE: int = 20  # INR 0.20 per SMS message
OUTREACH_EMAIL_COST_PAISE: int = 5  # INR 0.05 per transactional email
OUTREACH_VOICE_COST_PAISE: int = 150  # INR 1.50 per automated voice recovery call

# Policy Invariants and Guardrails
DEFAULT_MAX_DUNNING_ATTEMPTS: int = 3
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

# Escalating mandate-retry backoff, indexed by attempt number. NPCI/bank
# practice retries soon then backs off; last value repeats past list length.
DEFAULT_MANDATE_RETRY_BACKOFF_HOURS: list[int] = [4, 24, 72]

# eNACH clears via bank batch cycles, not a live rail, so it gets more room.
DEFAULT_ENACH_RETRY_BACKOFF_HOURS: list[int] = [24, 72, 120]

# Canonical value; every consumer reads it from Settings, never its own literal.
DEFAULT_AGENTIC_MODEL: str = "meta-llama/llama-4-scout-17b-16e-instruct"

DEFAULT_ANTHROPIC_MODEL: str = "claude-opus-5"

# Synthetic case id for audit rows describing system-wide actions rather than a
# single recovery case. Deliberately not a foreign key into cases.
GLOBAL_AUDIT_CASE_ID: str = "SYSTEM_GLOBAL"

# Razorpay API hosts. Four call sites previously built these independently.
RAZORPAY_API_BASE: str = "https://api.razorpay.com"
RAZORPAY_AUTH_BASE: str = "https://auth.razorpay.com"

# Twilio Voice REST API host. The account SID is path-scoped per Twilio's API
# shape, so callers still interpolate it into the endpoint.
TWILIO_API_BASE: str = "https://api.twilio.com/2010-04-01"

# Twilio's <Say> voice attribute for Hindi text-to-speech, per Twilio's
# supported TTS language list. Hinglish copy (mixed Hindi/English script)
# renders acceptably under this voice; there is no dedicated "Hinglish" code.
TWILIO_VOICE_LANGUAGE_HI: str = "hi-IN"

# Meta WhatsApp Business Cloud API. Pinned to a specific version rather than
# "latest" per the never-pin-to-latest rule, and re-verified against
# developers.facebook.com/docs/whatsapp/cloud-api before bumping.
WHATSAPP_GRAPH_API_BASE: str = "https://graph.facebook.com/v20.0"

# The template's approved locale code (Meta requires en_US, not a bare "en").
WHATSAPP_TEMPLATE_LANGUAGE_CODE: str = "en_US"

# Sarvam AI TTS. Pinned to a specific API version path, re-verified against
# docs.sarvam.ai before bumping.
SARVAM_API_BASE: str = "https://api.sarvam.ai"

# bulbul:v3 is Sarvam's current TTS model and explicitly supports code-mixed
# Hindi/English text, unlike Twilio's <Say>, which assumes one language per
# call. This is the reason to use Sarvam at all here.
SARVAM_TTS_MODEL: str = "bulbul:v3"

# BCP-47 code for Hindi, matching Sarvam's language_code field. Sarvam's own
# code-mixing support means the same code is used whether the drafted message
# is pure Hindi or Hinglish -- there is no separate "Hinglish" code.
SARVAM_TTS_LANGUAGE_CODE_HI: str = "hi-IN"

# mp3 keeps the pre-generated file consistent with the audio/mpeg content
# type voice_audio.py serves back to Twilio's <Play>.
SARVAM_TTS_AUDIO_CODEC: str = "mp3"

# How long a pre-generated call recording stays servable at its one-time URL.
# Twilio fetches it within seconds of the call being placed; this only needs
# to outlive that fetch, not the call itself.
VOICE_AUDIO_CACHE_TTL_SECONDS: float = 300.0
VOICE_AUDIO_CACHE_MAX_ENTRIES: int = 200

# OAuth access tokens live 90 days and refresh tokens 180; refresh this many days
# before expiry so a recovery call never fails on a token we could have renewed.
OAUTH_REFRESH_WINDOW_DAYS: int = 7
OAUTH_REFRESH_TOKEN_TTL_DAYS: int = 180
OAUTH_STATE_TTL_MINUTES: int = 15

# Time Windows (Hours / Minutes)
TRANSIENT_BANK_WINDOW_DELAY_HOURS: int = 4
SALARY_CYCLE_RETRY_SPACING_HOURS: int = 48
CHECKOUT_DROP_OFF_LINK_VALIDITY_MINUTES: int = 15
MAX_DUNNING_LIFECYCLE_DAYS: int = 7
MAX_FLEET_EVENTS_PER_MINUTE: int = 500

# Fleet's post-failure recovery simulation: how many still-open payments to
# hold in memory for a possible later "payment.captured" webhook, and the
# per-tick odds of checking one rather than emitting a new failure. Checking
# every tick would starve new-failure generation once the pending set fills.
FLEET_MAX_PENDING_RECOVERIES: int = 200
FLEET_RECOVERY_CHECK_PROBABILITY: float = 0.3


# Promise-to-Pay follow-up. The classifier has no date extraction from customer
# text, so every promise defaults to this fixed grace window rather than a
# fabricated parsed date.
P2P_DEFAULT_FOLLOWUP_HOURS: int = 72
# One reminder before escalating, bounded by the same attempts cap as every
# other intervention so a missed promise cannot loop forever.
P2P_MAX_REMINDER_ATTEMPTS: int = 1

# Thresholds for weighting an insufficient-funds decline against customer history.
# Repeat failures on a thin record read as solvency, not timing; a long reliable
# record outweighs them.
REPEAT_LIQUIDITY_FAILURE_LIMIT: int = 3
ESTABLISHED_CUSTOMER_CASE_COUNT: int = 6
RELIABLE_RECOVERY_RATE: float = 0.7

# Voice calls are expensive and intrusive, so escalation to VOICE_CALL is
# scoped narrowly: a liquidity-constrained customer who has already ignored
# at least one text-based outreach attempt on a case above this amount.
VOICE_CALL_MIN_AMOUNT_PAISE: int = 500_00  # INR 500
VOICE_CALL_MIN_PRIOR_OUTREACH_ATTEMPTS: int = 1

# Pagination and Batch limits
DEFAULT_BATCH_PAGE_SIZE: int = 50
MAX_BATCH_EVALUATION_SIZE: int = 500

# Amount bands for the LLM diagnosis cache key. Mirrors ml.py's _amount_band
# so the cache and the recovery model bucket amounts the same way.
LLM_DIAGNOSIS_CACHE_AMOUNT_BANDS_PAISE: tuple[int, ...] = (
    5_000,
    20_000,
    50_000,
    200_000,
    1_000_000,
)

# Bounds the in-process diagnosis cache dict so a long-running worker process
# cannot grow it unboundedly across a large batch of distinct failure patterns.
LLM_DIAGNOSIS_CACHE_MAX_ENTRIES: int = 2048
