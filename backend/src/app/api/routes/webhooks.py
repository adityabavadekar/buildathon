"""Razorpay webhook ingestion endpoint with fast 202 non-blocking queue ingestion."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, SecretStr

from app.audit.global_log import record_global_audit
from app.audit.models import AuditEntry, RecoveryCase, ScheduledJob
from app.audit.repository import get_case_repository
from app.core.config import get_settings
from app.core.constants import DEFAULT_CURRENCY
from app.core.credential_resolver import resolve_webhook_secret
from app.core.enums import AuditActor, ExperimentArm, PaymentRail, RecoveryState
from app.core.logging import get_logger
from app.detection.models import RawFailureEvent
from app.integrations.store import get_oauth_connection_store
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


def _identity_value(values: dict[str, Any], *keys: str) -> str | None:
    """Return the first non-empty merchant-provided identity value."""
    for key in keys:
        value = values.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


def _extract_payment_identity(payment_entity: dict[str, Any]) -> dict[str, str | None]:
    """Extract merchant identity from notes and entity without changing the raw webhook payload."""
    notes = payment_entity.get("notes")
    notes_data = notes if isinstance(notes, dict) else {}
    metadata = payment_entity.get("metadata")
    metadata_data = metadata if isinstance(metadata, dict) else {}
    return {
        "campaign_id": _identity_value(
            notes_data, "recovery_campaign", "campaign_id", "utm_campaign", "campaign"
        )
        or _identity_value(
            metadata_data, "recovery_campaign", "campaign_id", "campaign"
        ),
        "user_ref": _identity_value(
            notes_data,
            "user_id",
            "customer_ref",
            "reference_id",
            "order_id",
            "user_ref",
        ),
        "reference_id": _identity_value(notes_data, "reference_id", "order_id"),
        "subscription_id": _identity_value(notes_data, "subscription_id")
        or _identity_value(payment_entity, "subscription_id"),
        "invoice_id": _identity_value(notes_data, "invoice_id")
        or _identity_value(payment_entity, "invoice_id"),
        "contact_email": _identity_value(payment_entity, "email"),
        "contact_phone": _identity_value(payment_entity, "contact"),
    }


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
    "/razorpay",
    response_model=WebhookResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest Razorpay Webhook Event",
)
async def handle_razorpay_webhook(  # noqa: PLR0911, PLR0912, PLR0915
    request: Request,
    response: Response,
    x_razorpay_signature: Annotated[str | None, Header()] = None,
) -> WebhookResponse:
    """Ingest Razorpay payment.failed, subscription.halted, and payment.captured webhooks."""
    body_bytes = await request.body()
    settings = get_settings()

    # 1. Verify cryptographic signature if secret configured
    secret_val = resolve_webhook_secret()
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
    repo = get_case_repository()

    logger.info("webhook.received", event_type=event_type)

    # A revoked app's tokens are already dead at Razorpay, so keeping the row
    # would leave the engine authenticating with a credential that cannot work.
    if event_type == "account.app.authorization_revoked":
        removed = get_oauth_connection_store().clear()
        if removed:
            record_global_audit(
                event_name="integrations.oauth_revoked_by_merchant",
                actor=AuditActor.GATEWAY_WEBHOOK,
                reason="Sub-merchant revoked the FORTX partner application.",
                notes="OAuth connection cleared; reverted to API key pair.",
            )
        response.status_code = status.HTTP_200_OK
        return WebhookResponse(
            status="processed" if removed else "ignored",
            event=event_type,
            action_taken="OAUTH_DISCONNECTED" if removed else "NOOP",
        )

    # 3. Handle Payment Captured (Immediate recovery resolution)
    if event_type == "payment.captured":
        payment_entity = event_payload.get("payment", {}).get("entity", {})
        payment_id = payment_entity.get("id", "")
        amount = payment_entity.get("amount", 0)

        recovered_case = _orchestrator.process_payment_captured(payment_id, amount)
        response.status_code = status.HTTP_200_OK
        return WebhookResponse(
            status="processed" if recovered_case else "ignored",
            event=event_type,
            case_id=recovered_case.case_id if recovered_case else None,
            action_taken="RECOVERED" if recovered_case else "NOOP",
        )

    # 4. Handle Payment Failed (Fast 202 Non-Blocking Enqueue)
    if event_type == "payment.failed":
        payment_entity = event_payload.get("payment", {}).get("entity", {})
        payment_id = payment_entity.get("id", f"pay_webhook_{uuid4().hex[:8]}")

        # Deduplication check at inbox
        existing_case = repo.get_by_payment_id(payment_id)
        if existing_case:
            response.status_code = status.HTTP_202_ACCEPTED
            return WebhookResponse(
                status="queued",
                event=event_type,
                case_id=existing_case.case_id,
                action_taken="ALREADY_QUEUED",
            )

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
        identity = _extract_payment_identity(payment_entity)

        event = RawFailureEvent(
            event_id=f"evt_{payment_id}",
            payment_id=payment_id,
            customer_id=payment_entity.get("customer_id")
            or payment_entity.get("contact")
            or "guest_customer",
            amount_paise=payment_entity.get("amount", 10000),
            currency=payment_entity.get("currency", DEFAULT_CURRENCY),
            payment_rail=rail,
            error_code=error_code,
            error_description=error_description,
            error_source=error_source,
            error_step=error_step,
            error_reason=error_reason,
            npci_response_code=str(npci_code) if npci_code else None,
            occurred_at=datetime.now(UTC),
            invoice_id=identity["invoice_id"] or payment_entity.get("invoice_id"),
            subscription_id=identity["subscription_id"]
            or payment_entity.get("subscription_id"),
            campaign_id=identity["campaign_id"],
            user_ref=identity["user_ref"],
            reference_id=identity["reference_id"],
            contact_email=identity["contact_email"],
            contact_phone=identity["contact_phone"],
            metadata=payment_entity,
        )

        now = datetime.now(UTC)
        case_id = f"case_wh_{uuid4().hex[:8]}"
        case = RecoveryCase(
            case_id=case_id,
            merchant_id="merchant_live_buildathon",
            state=RecoveryState.ANALYSIS_QUEUED,
            experiment_arm=ExperimentArm.TREATMENT,
            amount_paise=event.amount_paise,
            currency=event.currency,
            failure_event=event,
            campaign_id=event.campaign_id,
            user_ref=event.user_ref,
            reference_id=event.reference_id,
            contact_email=event.contact_email,
            contact_phone=event.contact_phone,
            created_at=now,
            updated_at=now,
        )
        case.audit_trail.append(
            AuditEntry(
                case_id=case_id,
                from_state=None,
                to_state=RecoveryState.ANALYSIS_QUEUED,
                actor=AuditActor.GATEWAY_WEBHOOK,
                event_name="case.ingested",
                notes=f"Ingested payment failure {payment_id} via webhook into queue",
                cost_incurred_paise=0,
                decision_inputs={
                    "payment_id": payment_id,
                    "amount_paise": event.amount_paise,
                    "rail": rail.value,
                },
                timestamp=now,
            )
        )
        case.recompute_nrv()
        repo.save(case)

        job = ScheduledJob(
            case_id=case_id,
            job_type="INGESTION_DIAGNOSIS",
            due_at=now,
            status="QUEUED",
            idempotency_key=f"ingest_{payment_id}",
            payload={"event_id": event.event_id, "payment_id": payment_id},
            created_at=now,
            updated_at=now,
        )
        repo.schedule_job(job)

        response.status_code = status.HTTP_202_ACCEPTED
        return WebhookResponse(
            status="queued",
            event=event_type,
            case_id=case_id,
            action_taken="QUEUED",
        )

    # 4. Handle Subscription Halted
    if event_type == "subscription.halted":
        sub_entity = event_payload.get("subscription", {}).get("entity", {})
        sub_id = sub_entity.get("id", f"sub_{uuid4().hex[:8]}")
        payment_id = f"pay_halted_{sub_id}"

        existing_case = repo.get_by_payment_id(payment_id)
        if existing_case:
            response.status_code = status.HTTP_202_ACCEPTED
            return WebhookResponse(
                status="queued",
                event=event_type,
                case_id=existing_case.case_id,
                action_taken="ALREADY_QUEUED",
            )

        event = RawFailureEvent(
            event_id=f"evt_{sub_id}",
            payment_id=payment_id,
            customer_id=sub_entity.get("customer_id", "guest_sub"),
            amount_paise=sub_entity.get("plan", {}).get("amount", 0)
            or sub_entity.get("current_cycle", {}).get("amount", 0)
            or 149900,
            currency=sub_entity.get("currency", DEFAULT_CURRENCY),
            payment_rail=PaymentRail.ENACH,
            error_code="SUBSCRIPTION_HALTED",
            error_description="Customer mandate exhausted consecutive retries",
            error_reason="mandate_exhausted",
            occurred_at=datetime.now(UTC),
            subscription_id=sub_id,
            metadata=sub_entity,
        )

        now = datetime.now(UTC)
        case_id = f"case_sub_{uuid4().hex[:8]}"
        case = RecoveryCase(
            case_id=case_id,
            merchant_id="merchant_live_buildathon",
            state=RecoveryState.ANALYSIS_QUEUED,
            experiment_arm=ExperimentArm.TREATMENT,
            amount_paise=event.amount_paise,
            currency=event.currency,
            failure_event=event,
            created_at=now,
            updated_at=now,
        )
        case.audit_trail.append(
            AuditEntry(
                case_id=case_id,
                from_state=None,
                to_state=RecoveryState.ANALYSIS_QUEUED,
                actor=AuditActor.GATEWAY_WEBHOOK,
                event_name="case.ingested",
                notes=f"Ingested subscription halt {sub_id} via webhook into queue",
                cost_incurred_paise=0,
                decision_inputs={
                    "subscription_id": sub_id,
                    "payment_id": payment_id,
                    "amount_paise": event.amount_paise,
                },
                timestamp=now,
            )
        )
        case.recompute_nrv()
        repo.save(case)

        job = ScheduledJob(
            case_id=case_id,
            job_type="INGESTION_DIAGNOSIS",
            due_at=now,
            status="QUEUED",
            idempotency_key=f"ingest_{payment_id}",
            payload={"event_id": event.event_id, "payment_id": payment_id},
            created_at=now,
            updated_at=now,
        )
        repo.schedule_job(job)

        response.status_code = status.HTTP_202_ACCEPTED
        return WebhookResponse(
            status="queued",
            event=event_type,
            case_id=case_id,
            action_taken="QUEUED",
        )

    # 5. Handle Smart Collect Virtual Account Credited (Direct Bank Settlement Reconciliation)
    if event_type == "virtual_account.credited":
        payment_entity = event_payload.get("payment", {}).get("entity", {})
        va_entity = event_payload.get("virtual_account", {}).get("entity", {})
        va_id = va_entity.get("id") or payment_entity.get("virtual_account_id") or ""
        notes = payment_entity.get("notes", {}) or va_entity.get("notes", {})
        case_id = notes.get("case_id")

        matching_case: RecoveryCase | None = None
        if case_id:
            matching_case = repo.get_by_id(case_id)
        if not matching_case and va_id:
            # Fallback search by virtual_account_id
            all_cases = repo.list_cases(limit=100)
            matching_case = next(
                (c for c in all_cases if c.virtual_account_id == va_id), None
            )

        if matching_case:
            amount_credited = payment_entity.get("amount", matching_case.amount_paise)
            mode = payment_entity.get("method", "BANK_TRANSFER").upper()
            now = datetime.now(UTC)

            if matching_case.state != RecoveryState.RECOVERED:
                matching_case.state = RecoveryState.RECOVERED
                matching_case.recovered_amount_paise = amount_credited
                matching_case.collected_amount_paise = amount_credited
                matching_case.collection_mode = mode
                matching_case.collected_at = now
                matching_case.bank_transfer_id = payment_entity.get("id")
                matching_case.recompute_nrv()

                matching_case.audit_trail.append(
                    AuditEntry(
                        case_id=matching_case.case_id,
                        from_state=RecoveryState.P2P_WAITING,
                        to_state=RecoveryState.RECOVERED,
                        actor=AuditActor.GATEWAY_WEBHOOK,
                        event_name="smart_collect.reconciled",
                        notes=f"Reconciled Smart Collect credit of {amount_credited} paise via {mode}",
                        cost_incurred_paise=0,
                        decision_inputs={
                            "virtual_account_id": va_id,
                            "mode": mode,
                            "amount_paise": amount_credited,
                        },
                        timestamp=now,
                    )
                )
                repo.save(matching_case)

            response.status_code = status.HTTP_200_OK
            return WebhookResponse(
                status="processed",
                event=event_type,
                case_id=matching_case.case_id,
                action_taken="RECOVERED",
            )

    # 6. Handle Payment Link Paid / Partially Paid / Expired
    if event_type in (
        "payment_link.paid",
        "payment_link.partially_paid",
        "payment_link.expired",
    ):
        link_entity = event_payload.get("payment_link", {}).get("entity", {})
        link_id = link_entity.get("id", "")
        notes = link_entity.get("notes", {})
        case_id = notes.get("case_id")

        matching_case = repo.get_by_id(case_id) if case_id else None
        if not matching_case and link_id:
            all_cases = repo.list_cases(limit=100)
            matching_case = next(
                (c for c in all_cases if c.payment_link_id == link_id), None
            )

        if matching_case:
            now = datetime.now(UTC)
            if event_type == "payment_link.paid":
                amount_paid = link_entity.get("amount_paid", matching_case.amount_paise)
                if matching_case.state != RecoveryState.RECOVERED:
                    matching_case.state = RecoveryState.RECOVERED
                    matching_case.recovered_amount_paise = amount_paid
                    matching_case.recompute_nrv()
                    matching_case.audit_trail.append(
                        AuditEntry(
                            case_id=matching_case.case_id,
                            from_state=RecoveryState.OUTREACH_PENDING,
                            to_state=RecoveryState.RECOVERED,
                            actor=AuditActor.GATEWAY_WEBHOOK,
                            event_name="payment_link.paid_reconciled",
                            notes=f"Reconciled payment link {link_id} payment of {amount_paid} paise",
                            decision_inputs={
                                "payment_link_id": link_id,
                                "amount_paise": amount_paid,
                            },
                            timestamp=now,
                        )
                    )
                    repo.save(matching_case)
                response.status_code = status.HTTP_200_OK
                return WebhookResponse(
                    status="processed",
                    event=event_type,
                    case_id=matching_case.case_id,
                    action_taken="RECOVERED",
                )

            if event_type == "payment_link.partially_paid":
                amount_paid = link_entity.get("amount_paid", 0)
                matching_case.recovered_amount_paise += amount_paid
                matching_case.recompute_nrv()
                matching_case.audit_trail.append(
                    AuditEntry(
                        case_id=matching_case.case_id,
                        from_state=matching_case.state,
                        to_state=matching_case.state,
                        actor=AuditActor.GATEWAY_WEBHOOK,
                        event_name="payment_link.partially_paid",
                        notes=f"Recorded partial payment of {amount_paid} paise on link {link_id}",
                        decision_inputs={
                            "payment_link_id": link_id,
                            "amount_paise": amount_paid,
                        },
                        timestamp=now,
                    )
                )
                repo.save(matching_case)
                response.status_code = status.HTTP_200_OK
                return WebhookResponse(
                    status="processed",
                    event=event_type,
                    case_id=matching_case.case_id,
                    action_taken="PARTIAL_PAYMENT_RECORDED",
                )

            if event_type == "payment_link.expired":
                matching_case.audit_trail.append(
                    AuditEntry(
                        case_id=matching_case.case_id,
                        from_state=matching_case.state,
                        to_state=matching_case.state,
                        actor=AuditActor.GATEWAY_WEBHOOK,
                        event_name="payment_link.expired",
                        notes=f"Payment link {link_id} expired without full settlement",
                        decision_inputs={"payment_link_id": link_id},
                        timestamp=now,
                    )
                )
                repo.save(matching_case)
                response.status_code = status.HTTP_200_OK
                return WebhookResponse(
                    status="processed",
                    event=event_type,
                    case_id=matching_case.case_id,
                    action_taken="EXPIRY_LOGGED",
                )

    response.status_code = status.HTTP_200_OK
    return WebhookResponse(
        status="ignored", event=event_type, action_taken="UNSUPPORTED_EVENT"
    )
