"""Tests for batch simulation seeder and system status endpoints."""

from fastapi.testclient import TestClient


def test_seed_and_reset_simulation_api(client: TestClient) -> None:
    # 1. Reset
    res_reset = client.post("/api/simulation/reset")
    assert res_reset.status_code == 200

    # 2. Seed batch of 15
    res_seed = client.post(
        "/api/simulation/seed", json={"count": 15, "simulate_resolutions": True}
    )
    assert res_seed.status_code == 200
    data = res_seed.json()
    assert data["seeded_count"] == 15
    assert len(data["case_ids"]) > 0

    # 3. Check analytics updated dynamically
    res_analytics = client.get("/api/analytics")
    assert res_analytics.status_code == 200
    adata = res_analytics.json()
    assert adata["total_cases"] == 15
    assert adata["total_at_risk_paise"] > 0

    # 4. Check system status API
    res_status = client.get("/api/simulation/status")
    assert res_status.status_code == 200
    sdata = res_status.json()
    assert sdata["system_status"] == "OPERATIONAL"
    assert sdata["database_cases_count"] == 15
    assert sdata["gateway_integration"]["provider"] == "Razorpay"
