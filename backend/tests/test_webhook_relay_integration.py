"""End-to-end integration tests for Webhook Relay round-trip, HMAC verification, and resolution."""

import hashlib
import hmac
import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import get_settings
from app.core.enums import RecoveryState


def test_e2e_webhook_relay_round_trip_and_resolution(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify end-to-end webhook ingress with HMAC verification -> case creation -> recovery capture."""
    webhook_secret = "rzp_wh_relay_secret_key_888"  # noqa: S105
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_webhook_secret", SecretStr(webhook_secret))

    payment_id = "pay_relay_e2e_001"
    customer_id = "cust_relay_e2e_001"
    amount_paise = 450000  # INR 4,500

    # 1. Simulate payment.failed webhook incoming through relay
    fail_event = {
        "event": "payment.failed",
        "created_at": int(datetime.now(UTC).timestamp()),
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "amount": amount_paise,
                    "currency": "INR",
                    "status": "failed",
                    "method": "upi",
                    "customer_id": customer_id,
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_reason": "bank_cutoff_in_progress",
                    "error_source": "bank",
                    "error_step": "payment_authorization",
                    "payment_method": {
                        "upi": {"npci_transaction_id": "XT_WINDOW_CUTOFF"}
                    },
                    "acquirer_data": {"auth_code": "XT"},
                }
            }
        },
    }

    fail_body = json.dumps(fail_event).encode("utf-8")
    fail_signature = hmac.new(
        webhook_secret.encode("utf-8"), fail_body, hashlib.sha256
    ).hexdigest()

    response_fail = client.post(
        "/api/webhooks/razorpay",
        content=fail_body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": fail_signature,
        },
    )
    assert response_fail.status_code == 200
    fail_data = response_fail.json()
    assert fail_data["status"] == "processed"
    case_id = fail_data["case_id"]
    assert case_id is not None

    # 2. Inspect case state
    case_res = client.get(f"/api/cases/{case_id}")
    assert case_res.status_code == 200
    case_data = case_res.json()
    assert case_data["case_id"] == case_id
    assert case_data["amount_paise"] == amount_paise
    assert case_data["state"] in (
        RecoveryState.RETRY_SCHEDULED.value,
        RecoveryState.OUTREACH_PENDING.value,
        RecoveryState.ANALYSIS_QUEUED.value,
        RecoveryState.IN_DUNNING.value,
    )

    # 3. Simulate payment.captured webhook arriving after scheduled intervention
    capture_event = {
        "event": "payment.captured",
        "created_at": int(datetime.now(UTC).timestamp()),
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "amount": amount_paise,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        },
    }

    capture_body = json.dumps(capture_event).encode("utf-8")
    capture_signature = hmac.new(
        webhook_secret.encode("utf-8"), capture_body, hashlib.sha256
    ).hexdigest()

    response_cap = client.post(
        "/api/webhooks/razorpay",
        content=capture_body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": capture_signature,
        },
    )
    assert response_cap.status_code == 200
    cap_data = response_cap.json()
    assert cap_data["status"] == "processed"
    assert cap_data["action_taken"] == "RECOVERED"

    # 4. Verify case is terminal RECOVERED with accurate NRV and immutable audit trail
    resolved_res = client.get(f"/api/cases/{case_id}")
    assert resolved_res.status_code == 200
    resolved_case = resolved_res.json()
    assert resolved_case["state"] == RecoveryState.RECOVERED.value
    assert resolved_case["recovered_amount_paise"] == amount_paise
    assert resolved_case["net_recovered_value_paise"] > 0

    # 5. Check audit trail
    audit_res = client.get(f"/api/cases/{case_id}/audit")
    assert audit_res.status_code == 200
    audit_trail = audit_res.json()
    event_names = [e["event_name"] for e in audit_trail]
    assert any(e in event_names for e in ("case.created", "case.ingested"))
    assert "payment.recovered" in event_names
