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
from app.audit.state_machine import InvalidStateTransitionError, transition_case
from app.core.config import get_settings
from app.core.constants import DEFAULT_CURRENCY
from app.core.credential_resolver import resolve_webhook_secret
from app.core.enums import (
    AuditActor,
    EscalationReason,
    JobStatus,
    PaymentRail,
    RecoveryState,
)
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
        "experiment_tag": _identity_value(notes_data, "experiment_tag"),
    }


class WebhookResponse(BaseModel):
    """Standard response for ingested webhook events."""

    status: str
    event: str
    case_id: str | None = None
    action_taken: str | None = None


def _extract_refund_payment_id(event_payload: dict[str, Any]) -> str:
    """Resolve the originating payment ID from a refund webhook payload.

    Razorpay's refund payload nests both a `payment` entity and a `refund`
    entity; the refund entity carries `payment_id` directly, which is the
    field documented at razorpay.com/docs/webhooks/refunds.md.
    """
    payment_entity = event_payload.get("payment", {}).get("entity", {})
    refund_entity = event_payload.get("refund", {}).get("entity", {})
    return str(payment_entity.get("id") or refund_entity.get("payment_id") or "")


def _extract_dispute_payment_id(event_payload: dict[str, Any]) -> str:
    """Resolve the originating payment ID from a dispute webhook payload."""
    payment_entity = event_payload.get("payment", {}).get("entity", {})
    dispute_entity = event_payload.get("dispute", {}).get("entity", {})
    return str(payment_entity.get("id") or dispute_entity.get("payment_id") or "")


def _already_logged_by_id(
    case: RecoveryCase, event_name: str, id_key: str, id_value: str | None
) -> bool:
    """Idempotency guard: has this exact refund/dispute id already produced this audit event."""
    if not id_value:
        return False
    return any(
        entry.event_name == event_name and entry.decision_inputs.get(id_key) == id_value
        for entry in case.audit_trail
    )


def _log_informational(
    case: RecoveryCase,
    *,
    event_name: str,
    notes: str,
    decision_inputs: dict[str, Any],
) -> None:
    """Append an audit entry that does not change case state or amounts."""
    now = datetime.now(UTC)
    case.audit_trail.append(
        AuditEntry(
            case_id=case.case_id,
            from_state=case.state,
            to_state=case.state,
            actor=AuditActor.GATEWAY_WEBHOOK,
            event_name=event_name,
            notes=notes,
            decision_inputs=decision_inputs,
            timestamp=now,
        )
    )


def _reduce_recovered_amount(
    case: RecoveryCase,
    *,
    reduction_paise: int,
    event_name: str,
    notes: str,
    decision_inputs: dict[str, Any],
) -> None:
    """Reduce recovered_amount_paise for a refund or lost dispute, clamped at 0.

    RECOVERED is a terminal state with no legal exit in VALID_TRANSITIONS, so a
    full refund cannot transition the case out of RECOVERED. The audit trail
    and the adjusted recovered_amount_paise / net_recovered_value_paise are the
    only record that the case is no longer truly recovered.
    """
    now = datetime.now(UTC)
    original_amount = case.recovered_amount_paise
    clamped_reduction = min(reduction_paise, original_amount)
    anomalous = reduction_paise > original_amount
    case.recovered_amount_paise = max(0, original_amount - reduction_paise)
    case.recompute_nrv()
    case.updated_at = now

    fully_reversed = case.recovered_amount_paise == 0
    case.audit_trail.append(
        AuditEntry(
            case_id=case.case_id,
            from_state=case.state,
            to_state=case.state,
            actor=AuditActor.GATEWAY_WEBHOOK,
            event_name=event_name,
            notes=notes,
            decision_inputs={
                **decision_inputs,
                "reduction_paise": reduction_paise,
                "clamped_reduction_paise": clamped_reduction,
                "recovered_amount_before_paise": original_amount,
                "recovered_amount_after_paise": case.recovered_amount_paise,
                "net_recovered_value_after_paise": case.net_recovered_value_paise,
                "fully_reversed": fully_reversed,
                "amount_anomaly": anomalous,
            },
            timestamp=now,
        )
    )
    if anomalous:
        logger.warning(
            "webhook.refund_or_dispute_amount_exceeds_recorded",
            case_id=case.case_id,
            reduction_paise=reduction_paise,
            recovered_amount_before_paise=original_amount,
        )


def _escalate_case(
    case: RecoveryCase, *, event_name: str, reason: str, decision_inputs: dict[str, Any]
) -> None:
    """Escalate a case for human review, tolerating states with no legal path to ESCALATED."""
    if case.state == RecoveryState.ESCALATED:
        _log_informational(
            case,
            event_name=event_name,
            notes=reason,
            decision_inputs=decision_inputs,
        )
        return
    try:
        transition_case(
            case,
            RecoveryState.ESCALATED,
            AuditActor.GATEWAY_WEBHOOK,
            reason,
            event_name=event_name,
            escalation_reason=EscalationReason.HUMAN_JUDGMENT,
            decision_inputs=decision_inputs,
        )
    except InvalidStateTransitionError:
        # Terminal states (RECOVERED, ABANDONED, WRITTEN_OFF) have no legal
        # exit to ESCALATED. Keep the state as-is; the audit entry still
        # flags the dispute for human attention.
        _log_informational(
            case,
            event_name=event_name,
            notes=reason,
            decision_inputs=decision_inputs,
        )


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

    # 3b. Handle Order Paid (same success signal as payment.captured, but the
    # payload carries both payment and order entities together).
    if event_type == "order.paid":
        payment_entity = event_payload.get("payment", {}).get("entity", {})
        order_entity = event_payload.get("order", {}).get("entity", {})
        payment_id = payment_entity.get("id", "")
        amount = payment_entity.get("amount", 0)
        attempts = order_entity.get("attempts")

        recovered_case = _orchestrator.process_payment_captured(
            payment_id,
            amount,
            gateway_capture_id="order_paid_webhook",
            extra_decision_inputs={"order_attempts": attempts}
            if attempts is not None
            else None,
        )
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
            "UPI_AUTOPAY": PaymentRail.UPI_AUTOPAY,
            "CARD": PaymentRail.CARD,
            "NETBANKING": PaymentRail.NETBANKING,
            "ENACH": PaymentRail.ENACH,
            "EMANDATE": PaymentRail.ENACH,
            "NACH": PaymentRail.ENACH,
            "B2B_INVOICE": PaymentRail.B2B_INVOICE,
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
            experiment_tag=identity["experiment_tag"],
            metadata=payment_entity,
        )

        now = datetime.now(UTC)
        case_id = f"case_wh_{uuid4().hex[:8]}"
        case = RecoveryCase(
            case_id=case_id,
            merchant_id="merchant_live_buildathon",
            state=RecoveryState.ANALYSIS_QUEUED,
            experiment_arm=_orchestrator.assign_experiment_arm(payment_id),
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
            status=JobStatus.QUEUED,
            idempotency_key=f"ingest_{payment_id}",
            payload={
                "event_id": event.event_id,
                "payment_id": payment_id,
            },
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
            experiment_arm=_orchestrator.assign_experiment_arm(payment_id),
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
            status=JobStatus.QUEUED,
            idempotency_key=f"ingest_{payment_id}",
            payload={
                "event_id": event.event_id,
                "payment_id": payment_id,
            },
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

    # 4b. Handle Subscription Charged (Recovery: a previously-halted mandate
    # billed successfully again). Only a subscription with an existing case
    # from the halted path is in scope -- a routine renewal charge has no
    # case and is correctly ignored below.
    if event_type == "subscription.charged":
        sub_entity = event_payload.get("subscription", {}).get("entity", {})
        charge_payment_entity = event_payload.get("payment", {}).get("entity", {})
        sub_id = sub_entity.get("id", "")

        matching_case = None
        if sub_id:
            all_cases = repo.list_cases(limit=100)
            matching_case = next(
                (c for c in all_cases if c.failure_event.subscription_id == sub_id),
                None,
            )

        if matching_case:
            amount_charged = charge_payment_entity.get(
                "amount", matching_case.amount_paise
            )
            recovered_case = _orchestrator.process_payment_captured(
                matching_case.failure_event.payment_id,
                amount_charged,
                gateway_capture_id=charge_payment_entity.get("id", "webhook_capture"),
            )
            response.status_code = status.HTTP_200_OK
            return WebhookResponse(
                status="processed" if recovered_case else "ignored",
                event=event_type,
                case_id=recovered_case.case_id if recovered_case else None,
                action_taken="RECOVERED" if recovered_case else "NOOP",
            )

        response.status_code = status.HTTP_200_OK
        return WebhookResponse(status="ignored", event=event_type, action_taken="NOOP")

    # 4c. Handle Subscription Cancelled (mandate terminated: further retry or
    # outreach on an open case is pointless, so escalate for manual review
    # rather than continuing automated recovery on a dead mandate).
    if event_type == "subscription.cancelled":
        sub_entity = event_payload.get("subscription", {}).get("entity", {})
        sub_id = sub_entity.get("id", "")

        matching_case = None
        if sub_id:
            all_cases = repo.list_cases(limit=100)
            matching_case = next(
                (c for c in all_cases if c.failure_event.subscription_id == sub_id),
                None,
            )

        if matching_case and matching_case.state.is_active:
            transition_case(
                matching_case,
                to_state=RecoveryState.ESCALATED,
                actor=AuditActor.GATEWAY_WEBHOOK,
                reason=(
                    f"Subscription {sub_id} mandate cancelled at gateway; "
                    "automated retry and outreach are no longer viable. "
                    "Escalated for manual review."
                ),
                event_name="subscription.cancelled",
                escalation_reason=EscalationReason.HUMAN_JUDGMENT,
                decision_inputs={"subscription_id": sub_id},
            )
            repo.save(matching_case)
            response.status_code = status.HTTP_200_OK
            return WebhookResponse(
                status="processed",
                event=event_type,
                case_id=matching_case.case_id,
                action_taken="ESCALATED",
            )

        if matching_case:
            response.status_code = status.HTTP_200_OK
            return WebhookResponse(
                status="processed",
                event=event_type,
                case_id=matching_case.case_id,
                action_taken="NOOP",
            )

        response.status_code = status.HTTP_200_OK
        return WebhookResponse(status="ignored", event=event_type, action_taken="NOOP")

    # 4d. Handle Subscription Completed (informational: full billing cycle
    # finished successfully). Never forces a state change -- only logs, and
    # no-ops entirely if the case is already terminal.
    if event_type == "subscription.completed":
        sub_entity = event_payload.get("subscription", {}).get("entity", {})
        sub_id = sub_entity.get("id", "")

        matching_case = None
        if sub_id:
            all_cases = repo.list_cases(limit=100)
            matching_case = next(
                (c for c in all_cases if c.failure_event.subscription_id == sub_id),
                None,
            )

        if matching_case:
            if matching_case.state.is_terminal:
                response.status_code = status.HTTP_200_OK
                return WebhookResponse(
                    status="processed",
                    event=event_type,
                    case_id=matching_case.case_id,
                    action_taken="NOOP",
                )

            already_logged = any(
                entry.event_name == "subscription.completed"
                and entry.decision_inputs.get("subscription_id") == sub_id
                for entry in matching_case.audit_trail
            )
            if already_logged:
                response.status_code = status.HTTP_200_OK
                return WebhookResponse(
                    status="processed",
                    event=event_type,
                    case_id=matching_case.case_id,
                    action_taken="ALREADY_RECORDED",
                )

            now = datetime.now(UTC)
            matching_case.audit_trail.append(
                AuditEntry(
                    case_id=matching_case.case_id,
                    from_state=matching_case.state,
                    to_state=matching_case.state,
                    actor=AuditActor.GATEWAY_WEBHOOK,
                    event_name="subscription.completed",
                    notes=f"Subscription {sub_id} completed its full billing cycle.",
                    decision_inputs={"subscription_id": sub_id},
                    timestamp=now,
                )
            )
            repo.save(matching_case)
            response.status_code = status.HTTP_200_OK
            return WebhookResponse(
                status="processed",
                event=event_type,
                case_id=matching_case.case_id,
                action_taken="COMPLETION_LOGGED",
            )

        response.status_code = status.HTTP_200_OK
        return WebhookResponse(status="ignored", event=event_type, action_taken="NOOP")

    # 5. Handle Smart Collect Virtual Account Credited (Direct Bank Settlement Reconciliation)
    if event_type == "virtual_account.credited":
        payment_entity = event_payload.get("payment", {}).get("entity", {})
        va_entity = event_payload.get("virtual_account", {}).get("entity", {})
        va_id = va_entity.get("id") or payment_entity.get("virtual_account_id") or ""
        notes = payment_entity.get("notes", {}) or va_entity.get("notes", {})
        case_id = notes.get("case_id")

        matching_case = None
        if case_id:
            matching_case = repo.get_by_id(case_id)
        if not matching_case and va_id:
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
                partial_payment_entity = event_payload.get("payment", {}).get(
                    "entity", {}
                )
                partial_payment_id = partial_payment_entity.get("id")
                already_recorded = partial_payment_id is not None and any(
                    entry.decision_inputs.get("partial_payment_id")
                    == partial_payment_id
                    for entry in matching_case.audit_trail
                )
                if already_recorded:
                    response.status_code = status.HTTP_200_OK
                    return WebhookResponse(
                        status="processed",
                        event=event_type,
                        case_id=matching_case.case_id,
                        action_taken="ALREADY_RECORDED",
                    )

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
                            "partial_payment_id": partial_payment_id,
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
                already_logged = any(
                    entry.event_name == "payment_link.expired"
                    and entry.decision_inputs.get("payment_link_id") == link_id
                    for entry in matching_case.audit_trail
                )
                if already_logged:
                    response.status_code = status.HTTP_200_OK
                    return WebhookResponse(
                        status="processed",
                        event=event_type,
                        case_id=matching_case.case_id,
                        action_taken="ALREADY_RECORDED",
                    )

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

    # 7. Handle Invoice Paid / Partially Paid / Expired (B2B receivables chaser)
    if event_type in (
        "invoice.paid",
        "invoice.partially_paid",
        "invoice.expired",
    ):
        invoice_entity = event_payload.get("invoice", {}).get("entity", {})
        invoice_id = invoice_entity.get("id", "")
        notes = invoice_entity.get("notes", {})
        case_id = notes.get("case_id")

        matching_case = repo.get_by_id(case_id) if case_id else None
        if not matching_case and invoice_id:
            all_cases = repo.list_cases(limit=100)
            matching_case = next(
                (
                    c
                    for c in all_cases
                    if (
                        getattr(c, "invoice_id", None)
                        or getattr(c.failure_event, "invoice_id", None)
                    )
                    == invoice_id
                ),
                None,
            )

        if matching_case:
            now = datetime.now(UTC)
            if event_type == "invoice.paid":
                amount_paid = invoice_entity.get(
                    "amount_paid", matching_case.amount_paise
                )
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
                            event_name="invoice.paid_reconciled",
                            notes=f"Reconciled invoice {invoice_id} payment of {amount_paid} paise",
                            decision_inputs={
                                "invoice_id": invoice_id,
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

            if event_type == "invoice.partially_paid":
                partial_payment_entity = event_payload.get("payment", {}).get(
                    "entity", {}
                )
                partial_payment_id = partial_payment_entity.get("id")
                already_recorded = partial_payment_id is not None and any(
                    entry.decision_inputs.get("partial_payment_id")
                    == partial_payment_id
                    for entry in matching_case.audit_trail
                )
                if already_recorded:
                    response.status_code = status.HTTP_200_OK
                    return WebhookResponse(
                        status="processed",
                        event=event_type,
                        case_id=matching_case.case_id,
                        action_taken="ALREADY_RECORDED",
                    )

                amount_paid = invoice_entity.get("amount_paid", 0)
                matching_case.recovered_amount_paise += amount_paid
                matching_case.recompute_nrv()
                matching_case.audit_trail.append(
                    AuditEntry(
                        case_id=matching_case.case_id,
                        from_state=matching_case.state,
                        to_state=matching_case.state,
                        actor=AuditActor.GATEWAY_WEBHOOK,
                        event_name="invoice.partially_paid",
                        notes=f"Recorded partial payment of {amount_paid} paise on invoice {invoice_id}",
                        decision_inputs={
                            "invoice_id": invoice_id,
                            "amount_paise": amount_paid,
                            "partial_payment_id": partial_payment_id,
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

            if event_type == "invoice.expired":
                already_logged = any(
                    entry.event_name == "invoice.expired"
                    and entry.decision_inputs.get("invoice_id") == invoice_id
                    for entry in matching_case.audit_trail
                )
                if already_logged:
                    response.status_code = status.HTTP_200_OK
                    return WebhookResponse(
                        status="processed",
                        event=event_type,
                        case_id=matching_case.case_id,
                        action_taken="ALREADY_RECORDED",
                    )

                matching_case.audit_trail.append(
                    AuditEntry(
                        case_id=matching_case.case_id,
                        from_state=matching_case.state,
                        to_state=matching_case.state,
                        actor=AuditActor.GATEWAY_WEBHOOK,
                        event_name="invoice.expired",
                        notes=f"Invoice {invoice_id} expired without full settlement",
                        decision_inputs={"invoice_id": invoice_id},
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

    # 7. Handle Refund events. A refund always references the original payment,
    # never a case directly, so the lookup is by payment_id (same pattern as
    # payment.captured above).
    if event_type in (
        "refund.created",
        "refund.processed",
        "refund.failed",
        "refund.speed_changed",
    ):
        payment_id = _extract_refund_payment_id(event_payload)
        refund_entity = event_payload.get("refund", {}).get("entity", {})
        refund_id = refund_entity.get("id", "")
        refund_amount = refund_entity.get("amount", 0)
        refund_speed = refund_entity.get("speed_processed") or refund_entity.get(
            "speed_requested"
        )

        matching_case = repo.get_by_payment_id(payment_id) if payment_id else None
        if not matching_case:
            record_global_audit(
                event_name=event_type,
                actor=AuditActor.GATEWAY_WEBHOOK,
                reason=f"Refund event {event_type} for refund {refund_id} has no matching case for payment {payment_id}",
                decision_inputs={
                    "payment_id": payment_id,
                    "refund_id": refund_id,
                    "amount_paise": refund_amount,
                },
            )
            response.status_code = status.HTTP_200_OK
            return WebhookResponse(
                status="processed", event=event_type, action_taken="NO_MATCHING_CASE"
            )

        if event_type == "refund.processed":
            if _already_logged_by_id(
                matching_case, "refund.processed", "refund_id", refund_id
            ):
                response.status_code = status.HTTP_200_OK
                return WebhookResponse(
                    status="processed",
                    event=event_type,
                    case_id=matching_case.case_id,
                    action_taken="ALREADY_RECORDED",
                )

            _reduce_recovered_amount(
                matching_case,
                reduction_paise=refund_amount,
                event_name="refund.processed",
                notes=f"Refund {refund_id} of {refund_amount} paise processed on payment {payment_id}; recovered amount adjusted.",
                decision_inputs={
                    "payment_id": payment_id,
                    "refund_id": refund_id,
                },
            )
            repo.save(matching_case)
            response.status_code = status.HTTP_200_OK
            return WebhookResponse(
                status="processed",
                event=event_type,
                case_id=matching_case.case_id,
                action_taken="RECOVERED_AMOUNT_ADJUSTED",
            )

        if event_type == "refund.failed":
            if _already_logged_by_id(
                matching_case, "refund.failed", "refund_id", refund_id
            ):
                response.status_code = status.HTTP_200_OK
                return WebhookResponse(
                    status="processed",
                    event=event_type,
                    case_id=matching_case.case_id,
                    action_taken="ALREADY_RECORDED",
                )

            _log_informational(
                matching_case,
                event_name="refund.failed",
                notes=f"Refund {refund_id} of {refund_amount} paise failed on payment {payment_id}; no funds moved.",
                decision_inputs={
                    "payment_id": payment_id,
                    "refund_id": refund_id,
                    "amount_paise": refund_amount,
                },
            )
            repo.save(matching_case)
            response.status_code = status.HTTP_200_OK
            return WebhookResponse(
                status="processed",
                event=event_type,
                case_id=matching_case.case_id,
                action_taken="REFUND_FAILURE_LOGGED",
            )

        # refund.created, refund.speed_changed: informational only.
        if _already_logged_by_id(matching_case, event_type, "refund_id", refund_id):
            response.status_code = status.HTTP_200_OK
            return WebhookResponse(
                status="processed",
                event=event_type,
                case_id=matching_case.case_id,
                action_taken="ALREADY_RECORDED",
            )

        _log_informational(
            matching_case,
            event_name=event_type,
            notes=f"Refund {refund_id} on payment {payment_id}: {event_type}"
            + (f" (speed={refund_speed})" if refund_speed else ""),
            decision_inputs={
                "payment_id": payment_id,
                "refund_id": refund_id,
                "amount_paise": refund_amount,
                "speed": refund_speed,
            },
        )
        repo.save(matching_case)
        response.status_code = status.HTTP_200_OK
        return WebhookResponse(
            status="processed",
            event=event_type,
            case_id=matching_case.case_id,
            action_taken="LOGGED",
        )

    # 8. Handle Dispute events. Disputes reference the disputed payment, and a
    # dispute can arrive regardless of whether a case exists or what state it
    # is in.
    if event_type in (
        "payment.dispute.created",
        "payment.dispute.won",
        "payment.dispute.lost",
        "payment.dispute.closed",
        "payment.dispute.under_review",
        "payment.dispute.action_required",
    ):
        payment_id = _extract_dispute_payment_id(event_payload)
        dispute_entity = event_payload.get("dispute", {}).get("entity", {})
        dispute_id = dispute_entity.get("id", "")
        dispute_amount = dispute_entity.get("amount", 0)
        dispute_reason = dispute_entity.get("reason_code") or dispute_entity.get(
            "reason"
        )

        matching_case = repo.get_by_payment_id(payment_id) if payment_id else None
        if not matching_case:
            record_global_audit(
                event_name=event_type,
                actor=AuditActor.GATEWAY_WEBHOOK,
                reason=f"Dispute event {event_type} for dispute {dispute_id} has no matching case for payment {payment_id}",
                decision_inputs={
                    "payment_id": payment_id,
                    "dispute_id": dispute_id,
                    "amount_paise": dispute_amount,
                    "reason": dispute_reason,
                },
            )
            response.status_code = status.HTTP_200_OK
            return WebhookResponse(
                status="processed", event=event_type, action_taken="NO_MATCHING_CASE"
            )

        if _already_logged_by_id(matching_case, event_type, "dispute_id", dispute_id):
            response.status_code = status.HTTP_200_OK
            return WebhookResponse(
                status="processed",
                event=event_type,
                case_id=matching_case.case_id,
                action_taken="ALREADY_RECORDED",
            )

        if event_type in (
            "payment.dispute.created",
            "payment.dispute.under_review",
            "payment.dispute.action_required",
        ):
            _escalate_case(
                matching_case,
                event_name=event_type,
                reason=(
                    f"Dispute {dispute_id} ({event_type}) of {dispute_amount} paise "
                    f"on payment {payment_id}"
                    + (f", reason: {dispute_reason}" if dispute_reason else "")
                    + "; escalated for human review."
                ),
                decision_inputs={
                    "payment_id": payment_id,
                    "dispute_id": dispute_id,
                    "amount_paise": dispute_amount,
                    "reason": dispute_reason,
                },
            )
            repo.save(matching_case)
            response.status_code = status.HTTP_200_OK
            return WebhookResponse(
                status="processed",
                event=event_type,
                case_id=matching_case.case_id,
                action_taken="ESCALATED",
            )

        if event_type == "payment.dispute.won":
            _log_informational(
                matching_case,
                event_name=event_type,
                notes=f"Dispute {dispute_id} of {dispute_amount} paise on payment {payment_id} resolved in merchant's favor; recovered amount unchanged.",
                decision_inputs={
                    "payment_id": payment_id,
                    "dispute_id": dispute_id,
                    "amount_paise": dispute_amount,
                },
            )
            repo.save(matching_case)
            response.status_code = status.HTTP_200_OK
            return WebhookResponse(
                status="processed",
                event=event_type,
                case_id=matching_case.case_id,
                action_taken="DISPUTE_WON_LOGGED",
            )

        if event_type == "payment.dispute.lost":
            _reduce_recovered_amount(
                matching_case,
                reduction_paise=dispute_amount,
                event_name="payment.dispute.lost",
                notes=f"Dispute {dispute_id} of {dispute_amount} paise on payment {payment_id} lost; recovered amount adjusted.",
                decision_inputs={
                    "payment_id": payment_id,
                    "dispute_id": dispute_id,
                },
            )
            repo.save(matching_case)
            response.status_code = status.HTTP_200_OK
            return WebhookResponse(
                status="processed",
                event=event_type,
                case_id=matching_case.case_id,
                action_taken="RECOVERED_AMOUNT_ADJUSTED",
            )

        # payment.dispute.closed: informational only.
        _log_informational(
            matching_case,
            event_name=event_type,
            notes=f"Dispute {dispute_id} on payment {payment_id} closed.",
            decision_inputs={
                "payment_id": payment_id,
                "dispute_id": dispute_id,
                "amount_paise": dispute_amount,
            },
        )
        repo.save(matching_case)
        response.status_code = status.HTTP_200_OK
        return WebhookResponse(
            status="processed",
            event=event_type,
            case_id=matching_case.case_id,
            action_taken="LOGGED",
        )

    response.status_code = status.HTTP_200_OK
    return WebhookResponse(
        status="ignored", event=event_type, action_taken="UNSUPPORTED_EVENT"
    )
