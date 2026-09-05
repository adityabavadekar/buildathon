"""Tests for operator password authentication."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.core import auth as auth_module
from app.core.auth import (
    SESSION_COOKIE_NAME,
    auth_enabled,
    get_login_throttle,
    issue_session_token,
    verify_password,
    verify_session_token,
)
from app.core.config import Settings, get_settings
from app.core.constants import DEFAULT_OPERATOR_PASSWORD

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

OPERATOR_PASSWORD = "correct-horse-battery-staple"  # noqa: S105


@pytest.fixture
def _with_password(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enable the gate with a known password and a stable signing key."""
    settings = get_settings()
    monkeypatch.setattr(settings, "operator_password", SecretStr(OPERATOR_PASSWORD))
    monkeypatch.setattr(settings, "session_secret", SecretStr("test-session-secret"))
    get_login_throttle().reset()


def test_auth_is_disabled_with_an_empty_password() -> None:
    """conftest.py's autouse fixture sets this for every test but
    test_operator_auth.py itself; verifies the underlying invariant directly.
    """
    assert auth_enabled() is False


def test_settings_default_password_is_not_empty() -> None:
    """A Settings() built with no APP_OPERATOR_PASSWORD env var must still
    have a real password, or a deployment that forgets to set one is wide
    open. Constructed directly, bypassing conftest.py's test-only override.
    """
    fresh = Settings(_env_file=None)
    assert fresh.operator_password.get_secret_value() == DEFAULT_OPERATOR_PASSWORD


def test_auth_enabled_with_a_password(_with_password: None) -> None:
    assert auth_enabled() is True


def test_password_comparison(_with_password: None) -> None:
    assert verify_password(OPERATOR_PASSWORD) is True
    assert verify_password("wrong") is False
    assert verify_password("") is False


def test_session_token_round_trip(_with_password: None) -> None:
    token = issue_session_token()
    assert verify_session_token(token) is True


@pytest.mark.parametrize(
    "token",
    [None, "", "garbage", "no-dot-separator", "eyJhIjoxfQ.bm90LWEtc2lnbmF0dXJl"],
)
def test_malformed_tokens_are_rejected(_with_password: None, token: str | None) -> None:
    assert verify_session_token(token) is False


def test_tampered_payload_is_rejected(_with_password: None) -> None:
    """The signature must cover the payload, or expiry could be edited freely."""
    token = issue_session_token()
    payload, _, signature = token.partition(".")
    forged = f"{payload}x.{signature}"
    assert verify_session_token(forged) is False


def test_expired_token_is_rejected(
    _with_password: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = issue_session_token()
    later = time.time() + get_settings().session_ttl_hours * 3600 + 60
    monkeypatch.setattr("app.core.auth.time.time", lambda: later)
    assert verify_session_token(token) is False


def test_a_token_from_a_different_key_is_rejected(
    _with_password: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rotating the session secret must invalidate outstanding sessions."""
    token = issue_session_token()
    monkeypatch.setattr(get_settings(), "session_secret", SecretStr("rotated-secret"))
    assert verify_session_token(token) is False


def test_guarded_routes_are_open_when_auth_is_disabled(client: TestClient) -> None:
    assert client.get("/api/cases").status_code == 200


def test_session_endpoint_reports_the_gate_is_off(client: TestClient) -> None:
    body = client.get("/api/auth/session").json()
    assert body["auth_enabled"] is False
    assert body["authenticated"] is True


def test_guarded_routes_401_without_a_session(
    client: TestClient, _with_password: None
) -> None:
    assert client.get("/api/cases").status_code == 401
    assert client.get("/api/analytics").status_code == 401
    assert client.post("/api/integrations/oauth/authorize-url").status_code == 401


def test_open_routes_stay_reachable_with_auth_on(
    client: TestClient, _with_password: None
) -> None:
    """Health, auth, and webhooks must not require a cookie.

    Razorpay cannot present one, and the dashboard needs to ask whether a login is
    required before it can hold a session.
    """
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/auth/session").status_code == 200
    assert (
        client.post(
            "/api/webhooks/razorpay", json={"event": "unknown.event", "payload": {}}
        ).status_code
        != 401
    )


def test_login_then_access(client: TestClient, _with_password: None) -> None:
    assert client.get("/api/cases").status_code == 401

    res = client.post("/api/auth/login", json={"password": OPERATOR_PASSWORD})
    assert res.status_code == 200
    assert res.json()["authenticated"] is True
    assert SESSION_COOKIE_NAME in res.cookies

    assert client.get("/api/cases").status_code == 200


def test_login_rejects_a_wrong_password(
    client: TestClient, _with_password: None
) -> None:
    res = client.post("/api/auth/login", json={"password": "nope"})
    assert res.status_code == 401
    assert client.get("/api/cases").status_code == 401


def test_logout_clears_the_session(client: TestClient, _with_password: None) -> None:
    client.post("/api/auth/login", json={"password": OPERATOR_PASSWORD})
    assert client.get("/api/cases").status_code == 200

    client.post("/api/auth/logout")
    assert client.get("/api/cases").status_code == 401


def test_login_is_rate_limited(client: TestClient, _with_password: None) -> None:
    """A single shared password is brute-forceable without a lockout."""
    for _ in range(auth_module.MAX_FAILED_ATTEMPTS):
        assert client.post(
            "/api/auth/login", json={"password": "wrong"}
        ).status_code in {
            401,
            429,
        }

    locked = client.post("/api/auth/login", json={"password": OPERATOR_PASSWORD})
    assert locked.status_code == 429
    assert "seconds" in locked.json()["detail"]


def test_login_conflicts_when_auth_is_not_configured(client: TestClient) -> None:
    """Do not mint a session that means nothing."""
    res = client.post("/api/auth/login", json={"password": "anything"})
    assert res.status_code == 409


def test_password_is_never_echoed(client: TestClient, _with_password: None) -> None:
    res = client.post("/api/auth/login", json={"password": OPERATOR_PASSWORD})
    assert OPERATOR_PASSWORD not in res.text
