"""Tests for case listing, inspection, streaming, and operator approval endpoints."""

from fastapi.testclient import TestClient


def test_list_and_get_case_api(client: TestClient) -> None:
    # Ingest a failure to create a case
    fail_payload = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test_cases_api_1",
                    "amount": 350000,
                    "currency": "INR",
                    "status": "failed",
                    "customer_id": "cust_api_1",
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_reason": "mandate_revoked",
                }
            }
        },
    }
    res = client.post("/api/webhooks/razorpay", json=fail_payload)
    case_id = res.json()["case_id"]

    # 1. List cases
    list_res = client.get("/api/cases?limit=10")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1
    assert any(c["case_id"] == case_id for c in list_data["items"])

    # 2. Get case details
    get_res = client.get(f"/api/cases/{case_id}")
    assert get_res.status_code == 200
    case_data = get_res.json()
    assert case_data["case_id"] == case_id
    assert case_data["amount_paise"] == 350000

    # 3. Get case audit trail
    audit_res = client.get(f"/api/cases/{case_id}/audit")
    assert audit_res.status_code == 200
    audit_items = audit_res.json()
    assert len(audit_items) >= 1
    assert audit_items[0]["event_name"] in ("case.created", "case.ingested")


def test_get_nonexistent_case_returns_404(client: TestClient) -> None:
    res = client.get("/api/cases/non_existent_case_id")
    assert res.status_code == 404


def test_cases_stream_endpoint(client: TestClient) -> None:
    res = client.get("/api/cases/stream")
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]
    content = res.text
    assert "event: snapshot" in content
