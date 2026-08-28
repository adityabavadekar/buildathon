"""Tests for the health endpoint."""

from fastapi.testclient import TestClient

from app import __version__


def test_health_returns_200(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200


def test_health_reports_status_and_version(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert isinstance(body["llm_providers"], list)


def test_health_echoes_request_id(client: TestClient) -> None:
    """The middleware must preserve a caller-supplied ID, not replace it."""
    response = client.get("/health", headers={"x-request-id": "upstream-abc-123"})
    assert response.headers["x-request-id"] == "upstream-abc-123"


def test_health_generates_request_id_when_absent(client: TestClient) -> None:
    response = client.get("/health")
    assert response.headers.get("x-request-id")


def test_request_id_is_sanitised(client: TestClient) -> None:
    """Incoming IDs are untrusted: unsafe characters are stripped, not echoed."""
    response = client.get("/health", headers={"x-request-id": "bad\tid<script>"})
    returned = response.headers["x-request-id"]
    assert "<" not in returned
    assert "\t" not in returned


def test_health_does_not_leak_secret_values(client: TestClient) -> None:
    """Provider names may be reported; key material must never be."""
    body = client.get("/health").text
    assert "sk-" not in body
    assert "SecretStr" not in body
