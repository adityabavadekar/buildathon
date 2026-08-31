"""Domain models for payment failure ingestion and contextual diagnosis."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.core.constants import DEFAULT_CURRENCY
from app.core.enums import FailureCategory, InterventionType, PaymentRail


class RawFailureEvent(BaseModel):
    """Raw failure event ingested from payment gateways, webhooks, or drop-off trackers."""

    event_id: str
    payment_id: str
    customer_id: str
    amount_paise: int = Field(gt=0, description="Amount in minor units (paise)")
    currency: str = Field(default=DEFAULT_CURRENCY)
    payment_rail: PaymentRail = PaymentRail.UNKNOWN

    error_code: str = Field(
        description="High-level error code e.g. BAD_REQUEST_ERROR, GATEWAY_ERROR"
    )
    error_description: str = Field(default="")
    error_source: str | None = Field(
        default=None, description="Source: bank, gateway, customer, business"
    )
    error_step: str | None = Field(
        default=None, description="Step: payment_authorization, payment_authentication"
    )
    error_reason: str | None = Field(
        default=None, description="Detailed sub-code or reason string"
    )
    npci_response_code: str | None = Field(
        default=None, description="NPCI/e-NACH code e.g. AP15, VA, XT"
    )

    occurred_at: datetime = Field(description="Timezone-aware UTC timestamp of failure")
    invoice_id: str | None = None
    subscription_id: str | None = None
    campaign_id: str | None = None
    user_ref: str | None = None
    reference_id: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    experiment_tag: str | None = None
    model_override: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DiagnosisResult(BaseModel):
    """Structured diagnostic classification and proposed intervention."""

    category: FailureCategory
    confidence: Decimal = Field(ge=Decimal("0.0"), le=Decimal("1.0"))
    recommended_intervention: InterventionType
    recommended_delay_hours: int = Field(ge=0)
    discount_bps_suggested: int = Field(default=0, ge=0, le=10000)
    reasoning: str
    requires_human_approval: bool = False
    signals_evaluated: dict[str, Any] = Field(default_factory=dict)
