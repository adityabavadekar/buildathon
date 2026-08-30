"""Tests for analytics, policies, settings, and LLM configuration API endpoints."""

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


def test_llm_config_api(client: TestClient) -> None:
    # 1. GET LLM config
    res = client.get("/api/settings/llm-config")
    assert res.status_code == 200
    data = res.json()
    assert "providers" in data
    assert len(data["providers"]) >= 4

    # 2. PUT LLM config update
    providers = data["providers"]
    providers[0]["active_model"] = "anthropic/claude-3.7-sonnet"
    update_payload = {
        "providers": providers,
        "timeout_seconds": 35,
        "temperature": 0.15,
    }
    put_res = client.put("/api/settings/llm-config", json=update_payload)
    assert put_res.status_code == 200
    updated_data = put_res.json()
    assert updated_data["timeout_seconds"] == 35


def test_llm_report_api(client: TestClient) -> None:
    res = client.get("/api/settings/llm-report")
    assert res.status_code == 200
    data = res.json()
    assert "total_calls" in data
    assert "total_cost_usd" in data
    assert "model_breakdown" in data
    assert "average_latency_ms" in data


def test_gateway_probe_api(client: TestClient) -> None:
    res = client.post("/api/settings/test-gateway")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("CONNECTED", "PARTIAL", "SANDBOX_SIM")
    assert data["latency_ms"] > 0
    assert len(data["supported_rails"]) >= 4
