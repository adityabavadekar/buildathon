"""Tests for analytics, policies, and settings API endpoints."""

from fastapi.testclient import TestClient


def test_get_policies_api(client: TestClient) -> None:
    res = client.get("/api/policies")
    assert res.status_code == 200
    data = res.json()
    assert data["max_touches"] == 3
    assert data["min_cooldown_hours"] == 24
    assert data["max_discount_bps"] == 1000
    assert len(data["rules"]) >= 4


def test_get_settings_api(client: TestClient) -> None:
    res = client.get("/api/settings")
    assert res.status_code == 200
    data = res.json()
    assert "/api/webhooks/razorpay" in data["webhook_ingress_url"]
    assert data["deterministic_fallback_active"] is True


def test_get_analytics_api(client: TestClient) -> None:
    res = client.get("/api/analytics")
    assert res.status_code == 200
    data = res.json()
    assert "total_at_risk_paise" in data
    assert "attributable_lift_pct" in data
    assert "category_distribution" in data
    assert "intervention_performance" in data
