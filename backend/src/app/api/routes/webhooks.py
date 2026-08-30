"""Razorpay webhook ingestion and event dispatch endpoint."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.constants import DEFAULT_CURRENCY
from app.core.enums import PaymentRail
from app.core.logging import get_logger
from app.detection.models import RawFailureEvent
from app.intervention.orchestrator import RecoveryOrchestrator

logger = get_logger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_orchestrator = RecoveryOrchestrator()


class WebhookResponse(BaseModel):
    """Response returned upon webhook processing."""

    status: str
    event: str
    case_id: str | None = None
    action_taken: str | None = None


def _verify_webhook_signature(body_bytes: bytes, signature: str | None, secret: str | None) -> bool:
    """Verify HMAC-SHA256 signature from Razorpay webhook headers."""
    if not secret:
        return True  # Dev mode without secret configured
    if not signature:
        return False
    computed = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, signature)


@router.post("/razorpay", response_model=WebhookResponse, summary="Ingest Razorpay Webhook Event")
async def handle_razorpay_webhook(
    request: Request,
    x_razorpay_signature: Annotated[str | None, Header()] = None,
) -> WebhookResponse:
    """Ingest Razorpay payment.failed, subscription.halted, and payment.captured webhooks."""
    body_bytes = await request.body()
    settings = get_settings()

    # Verify cryptographic signature if secret configured
    webhook_secret = getattr(settings, "razorpay_webhook_secret", None)
    if webhook_secret and not _verify_webhook_signature(
        body_bytes, x_razorpay_signature, webhook_secret.get_secret_value()
    ):
        logger.warning("webhook.signature_verification_failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
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
        error_reason = payment_entity.get("error_reason")
        acquirer_data = payment_entity.get("acquirer_data") or {}
        npci_code = acquirer_data.get("auth_code") or acquirer_data.get("rrn")

        method = payment_entity.get("method", "unknown").upper()
        rail_map = {
            "UPI": PaymentRail.UPI,
            "CARD": PaymentRail.CARD,
            "NETBANKING": PaymentRail.NETBANKING,
            "ENACH": PaymentRail.ENACH,
            "EMANDATE": PaymentRail.ENACH,
        }
        rail = rail_map.get(method, PaymentRail.UNKNOWN)

        event = RawFailureEvent(
            event_id=f"evt_{payment_entity.get('id', 'unknown')}",
            payment_id=payment_entity.get("id", "unknown_pay"),
            customer_id=payment_entity.get("customer_id") or payment_entity.get("contact") or "guest_customer",
            amount_paise=payment_entity.get("amount", 0),
            currency=payment_entity.get("currency", DEFAULT_CURRENCY),
            payment_rail=rail,
            error_code=error_code,
            error_description=error_description,
            error_source=error_source,
            error_step=error_step,
            error_reason=error_reason,
            npci_response_code=npci_code,
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
            status="processed",
            event=event_type,
            case_id=recovered_case.case_id if recovered_case is not None else None,
            action_taken="RECOVERED" if recovered_case is not None else "UNMATCHED",
        )

    # 3. Handle Subscription Halted
    if event_type in {"subscription.halted", "subscription.pending"}:
        sub_entity = event_payload.get("subscription", {}).get("entity", {})
        sub_id = sub_entity.get("id", "unknown_sub")
        customer_id = sub_entity.get("customer_id") or "sub_customer"
        plan_entity = sub_entity.get("plan", {})
        amount = plan_entity.get("amount", 100000)

        event = RawFailureEvent(
            event_id=f"evt_sub_{sub_id}",
            payment_id=f"pay_sub_{sub_id}",
            customer_id=customer_id,
            amount_paise=amount,
            currency=DEFAULT_CURRENCY,
            payment_rail=PaymentRail.UPI_AUTOPAY,
            error_code="SUBSCRIPTION_HALTED",
            error_description="Mandate execution halted due to payment failures",
            error_reason="mandate_inactive",
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

    return WebhookResponse(status="ignored", event=event_type)
