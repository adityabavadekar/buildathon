"""Tests for Razorpay webhook ingestion HTTP endpoints, HMAC verification, and recovery resolution."""

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import get_settings


def test_webhook_payment_failed_ingestion(client: TestClient) -> None:
    payload = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test_wh_1",
                    "amount": 150000,
                    "currency": "INR",
                    "status": "failed",
                    "method": "upi",
                    "customer_id": "cust_test_wh_1",
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_description": "Payment was declined by customer bank",
                    "error_source": "bank",
                    "error_step": "payment_authorization",
                    "error_reason": "bank_cutoff_in_progress",
                    "acquirer_data": {"auth_code": "XT"},
                }
            }
        },
    }

    response = client.post("/api/webhooks/razorpay", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processed"
    assert data["event"] == "payment.failed"
    assert data["case_id"] is not None
    assert data["action_taken"] == "RETRY_SCHEDULED"


def test_webhook_payment_captured_ingestion(client: TestClient) -> None:
    # First ingest failure
    fail_payload = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test_wh_2",
                    "amount": 200000,
                    "currency": "INR",
                    "status": "failed",
                    "method": "card",
                    "customer_id": "cust_test_wh_2",
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_reason": "mandate_revoked",
                }
            }
        },
    }
    client.post("/api/webhooks/razorpay", json=fail_payload)

    # Then capture payment
    capture_payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test_wh_2",
                    "amount": 200000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        },
    }
    cap_response = client.post("/api/webhooks/razorpay", json=capture_payload)
    assert cap_response.status_code == 200
    cap_data = cap_response.json()
    assert cap_data["action_taken"] == "RECOVERED"


def test_webhook_hmac_signature_validation_accepted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify cryptographic HMAC-SHA256 signature validation accepts genuine webhook requests."""
    test_key = "rzp_webhook_secret_key_123"
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_webhook_secret", SecretStr(test_key))

    payload = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test_hmac_valid",
                    "amount": 100000,
                    "currency": "INR",
                    "status": "failed",
                    "method": "upi",
                    "customer_id": "cust_hmac_1",
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_reason": "payment_timed_out",
                }
            }
        },
    }
    raw_body = json.dumps(payload).encode("utf-8")
    expected_sig = hmac.new(
        test_key.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()

    response = client.post(
        "/api/webhooks/razorpay",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": expected_sig,
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "processed"


def test_webhook_hmac_signature_tampered_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify tampered or forged webhook signatures are rejected with 401 Unauthorized."""
    test_key = "rzp_webhook_secret_key_123"
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_webhook_secret", SecretStr(test_key))

    payload = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test_tampered",
                    "amount": 5000000,
                    "currency": "INR",
                    "status": "failed",
                }
            }
        },
    }
    raw_body = json.dumps(payload).encode("utf-8")
    tampered_sig = "deadbeef1234567890abcdef"

    response = client.post(
        "/api/webhooks/razorpay",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": tampered_sig,
        },
    )
    assert response.status_code == 401
    assert "Invalid webhook signature" in response.json()["detail"]
