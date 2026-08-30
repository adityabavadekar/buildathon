"""Tests for Razorpay webhook ingestion HTTP endpoints."""

from fastapi.testclient import TestClient


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
