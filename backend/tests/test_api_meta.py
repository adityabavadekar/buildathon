"""Tests for analytics, policies, settings, and LLM configuration API endpoints."""

from fastapi.testclient import TestClient


def test_get_policies_api(client: TestClient) -> None:
    res = client.get("/api/policies")
    assert res.status_code == 200
    data = res.json()
    assert data["max_attempts"] == 3
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


def test_mandatory_rule_provider_cannot_be_disabled(client: TestClient) -> None:
    """The deterministic taxonomy classifier always runs regardless of its
    enabled flag (llm/client.py excludes it from active_providers by name),
    so persisting it as disabled would show a false affordance in Settings.
    """
    res = client.get("/api/settings/llm-config")
    providers = res.json()["providers"]
    for provider in providers:
        if provider["name"] == "deterministic_rules":
            provider["enabled"] = False

    put_res = client.put(
        "/api/settings/llm-config",
        json={"providers": providers, "timeout_seconds": 30, "temperature": 0.2},
    )
    assert put_res.status_code == 200
    saved_providers = put_res.json()["providers"]
    mandatory = next(p for p in saved_providers if p["name"] == "deterministic_rules")
    assert mandatory["enabled"] is True

    reread = client.get("/api/settings/llm-config").json()["providers"]
    mandatory_reread = next(p for p in reread if p["name"] == "deterministic_rules")
    assert mandatory_reread["enabled"] is True


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
