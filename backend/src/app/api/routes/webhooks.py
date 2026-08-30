"""Razorpay webhook ingestion endpoint.

Receives, verifies, and processes payment.failed, payment.captured,
and subscription.halted events from Razorpay payment gateway.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, SecretStr

from app.core.config import get_settings
from app.core.constants import DEFAULT_CURRENCY
from app.core.enums import PaymentRail
from app.core.logging import get_logger
from app.detection.models import RawFailureEvent
from app.intervention.orchestrator import get_orchestrator

logger = get_logger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])
_orchestrator = get_orchestrator()


def _extract_secret(val: SecretStr | str | None) -> str | None:
    if val is None:
        return None
    if isinstance(val, SecretStr):
        return val.get_secret_value().strip()
    return str(val).strip()


class WebhookResponse(BaseModel):
    """Standard response for ingested webhook events."""

    status: str
    event: str
    case_id: str | None = None
    action_taken: str | None = None


def _verify_webhook_signature(
    body_bytes: bytes, signature: str | None, secret: str | None
) -> bool:
    """Verify HMAC-SHA256 signature from Razorpay webhook headers."""
    if not secret:
        return True  # Dev mode without secret configured
    if not signature:
        return False
    computed = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, signature)


@router.post(
    "/razorpay", response_model=WebhookResponse, summary="Ingest Razorpay Webhook Event"
)
async def handle_razorpay_webhook(
    request: Request,
    x_razorpay_signature: Annotated[str | None, Header()] = None,
) -> WebhookResponse:
    """Ingest Razorpay payment.failed, subscription.halted, and payment.captured webhooks."""
    body_bytes = await request.body()
    settings = get_settings()

    # Verify cryptographic signature if secret configured
    secret_val = _extract_secret(settings.razorpay_webhook_secret)
    if secret_val:
        if x_razorpay_signature is not None:
            if not _verify_webhook_signature(
                body_bytes, x_razorpay_signature, secret_val
            ):
                logger.warning("webhook.signature_verification_failed")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid webhook signature",
                )
        elif settings.env == "production":
            logger.warning("webhook.missing_signature_in_production")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing x-razorpay-signature header",
            )

    try:
        payload: dict[str, Any] = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON payload: {exc}",
        ) from exc

    event_type = payload.get("event", "")
    event_payload = payload.get("payload", {})

    logger.info("webhook.received", event_type=event_type)

    # 1. Handle Payment Failed
    if event_type == "payment.failed":
        payment_entity = event_payload.get("payment", {}).get("entity", {})
        error_code = payment_entity.get("error_code") or "GATEWAY_ERROR"
        error_description = payment_entity.get("error_description") or ""
        error_source = payment_entity.get("error_source")
        error_step = payment_entity.get("error_step")
        error_reason = (
            payment_entity.get("error_reason") or error_description or error_code
        )
        acquirer_data = payment_entity.get("acquirer_data") or {}
        payment_method_data = payment_entity.get("payment_method") or {}
        upi_method_data = (
            payment_method_data.get("upi")
            if isinstance(payment_method_data, dict)
            else {}
        )

        # Look in acquirer data error code, upi npci transaction id, auth code, or error reason
        npci_code = (
            acquirer_data.get("error_code")
            or acquirer_data.get("npci_response_code")
            or acquirer_data.get("auth_code")
            or (
                upi_method_data.get("npci_transaction_id")
                if isinstance(upi_method_data, dict)
                else None
            )
            or acquirer_data.get("npci_transaction_id")
            or payment_entity.get("error_code")
            or acquirer_data.get("rrn")
        )

        method = str(payment_entity.get("method", "unknown")).upper()
        rail_map = {
            "UPI": PaymentRail.UPI,
            "CARD": PaymentRail.CARD,
            "NETBANKING": PaymentRail.NETBANKING,
            "ENACH": PaymentRail.ENACH,
            "EMANDATE": PaymentRail.ENACH,
            "NACH": PaymentRail.ENACH,
        }
        rail = rail_map.get(method, PaymentRail.UNKNOWN)

        event = RawFailureEvent(
            event_id=f"evt_{payment_entity.get('id', 'unknown')}",
            payment_id=payment_entity.get("id", "unknown_pay"),
            customer_id=payment_entity.get("customer_id")
            or payment_entity.get("contact")
            or "guest_customer",
            amount_paise=payment_entity.get("amount", 0),
            currency=payment_entity.get("currency", DEFAULT_CURRENCY),
            payment_rail=rail,
            error_code=error_code,
            error_description=error_description,
            error_source=error_source,
            error_step=error_step,
            error_reason=error_reason,
            npci_response_code=str(npci_code) if npci_code else None,
            occurred_at=datetime.now(UTC),
            invoice_id=payment_entity.get("invoice_id"),
            subscription_id=payment_entity.get("subscription_id"),
            metadata=payment_entity,
        )

        case = await _orchestrator.process_failure_event(event)
        return WebhookResponse(
            status="processed",
            event=event_type,
            case_id=case.case_id,
            action_taken=case.state.value,
        )

    # 2. Handle Payment Captured (Recovery Resolution)
    if event_type == "payment.captured":
        payment_entity = event_payload.get("payment", {}).get("entity", {})
        payment_id = payment_entity.get("id", "")
        amount = payment_entity.get("amount", 0)

        recovered_case = _orchestrator.process_payment_captured(payment_id, amount)
        return WebhookResponse(
            status="processed" if recovered_case else "ignored",
            event=event_type,
            case_id=recovered_case.case_id if recovered_case else None,
            action_taken="RECOVERED" if recovered_case else "NOOP",
        )

    # 3. Handle Subscription Halted
    if event_type == "subscription.halted":
        sub_entity = event_payload.get("subscription", {}).get("entity", {})
        sub_id = sub_entity.get("id", "sub_unknown")

        event = RawFailureEvent(
            event_id=f"evt_{sub_id}",
            payment_id=f"pay_halted_{sub_id}",
            customer_id=sub_entity.get("customer_id", "guest_sub"),
            amount_paise=sub_entity.get("plan", {}).get("amount", 0)
            or sub_entity.get("current_cycle", {}).get("amount", 0),
            currency=sub_entity.get("currency", DEFAULT_CURRENCY),
            payment_rail=PaymentRail.ENACH,
            error_code="SUBSCRIPTION_HALTED",
            error_description="Customer mandate exhausted consecutive retries",
            error_reason="mandate_exhausted",
            occurred_at=datetime.now(UTC),
            subscription_id=sub_id,
            metadata=sub_entity,
        )

        case = await _orchestrator.process_failure_event(event)
        return WebhookResponse(
            status="processed",
            event=event_type,
            case_id=case.case_id,
            action_taken=case.state.value,
        )

    return WebhookResponse(
        status="ignored", event=event_type, action_taken="UNSUPPORTED_EVENT"
    )
