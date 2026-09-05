"""Tests for Razorpay Partner OAuth. Live OAuth cannot be exercised, so every
branch runs through an injected client standing in for auth.razorpay.com.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import parse_qs, urlparse

import pytest
from pydantic import SecretStr

from app.core.config import get_settings
from app.core.credentials import get_gateway_credential_store
from app.integrations.auth import resolve_razorpay_auth
from app.integrations.razorpay_oauth import (
    REQUIRED_SCOPE,
    OAuthError,
    build_authorize_url,
    exchange_code,
    is_configured,
    refresh_connection,
    revoke_connection,
)
from app.integrations.store import OAuthConnection, get_oauth_connection_store

if TYPE_CHECKING:
    import httpx2
    from fastapi.testclient import TestClient

# Synthetic fixture tokens; no real credential appears in this file.
ACCESS_TOKEN = "oauth_access_token_value_aaaa"  # noqa: S105
REFRESH_TOKEN = "oauth_refresh_token_value_bbbb"  # noqa: S105
ACCOUNT_ID = "acc_TestSubMerchant01"
EXPIRES_IN_SECONDS = 7862400


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = "fake"

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    """Records requests so a test can assert on the exchange body. Structural
    stand-in for httpx2.AsyncClient; call sites cast it.
    """

    def __init__(
        self, payload: dict[str, Any] | None = None, status_code: int = 200
    ) -> None:
        self.payload = payload or {
            "token_type": "Bearer",
            "expires_in": EXPIRES_IN_SECONDS,
            "access_token": ACCESS_TOKEN,
            "refresh_token": REFRESH_TOKEN,
            "public_token": "rzp_test_oauth_ABC123",
            "razorpay_account_id": ACCOUNT_ID,
            "scope": REQUIRED_SCOPE,
        }
        self.status_code = status_code
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def post(self, url: str, json: dict[str, Any]) -> _FakeResponse:
        self.calls.append((url, json))
        return _FakeResponse(self.payload, self.status_code)


def _as_client(fake: _FakeClient) -> httpx2.AsyncClient:
    return cast("httpx2.AsyncClient", fake)


@pytest.fixture(autouse=True)
def _oauth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure a partner client and start each test disconnected."""
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_oauth_client_id", "test_client_id_1234")
    monkeypatch.setattr(
        settings,
        "razorpay_oauth_client_secret",
        SecretStr("test_client_secret_value"),
    )
    monkeypatch.setattr(settings, "razorpay_oauth_mode", "test")
    get_oauth_connection_store().clear()


def _stored_connection(**overrides: Any) -> OAuthConnection:
    now = datetime.now(UTC)
    defaults: dict[str, Any] = {
        "access_token": SecretStr(ACCESS_TOKEN),
        "refresh_token": SecretStr(REFRESH_TOKEN),
        "public_token": "rzp_test_oauth_ABC123",
        "razorpay_account_id": ACCOUNT_ID,
        "scope": REQUIRED_SCOPE,
        "mode": "test",
        "token_expires_at": now + timedelta(days=80),
        "refresh_expires_at": now + timedelta(days=170),
    }
    defaults.update(overrides)
    return OAuthConnection(**defaults)


def test_authorize_url_carries_every_mandatory_parameter() -> None:
    parsed = urlparse(build_authorize_url())
    params = parse_qs(parsed.query)

    assert parsed.netloc == "auth.razorpay.com"
    assert parsed.path == "/authorize"
    assert params["response_type"] == ["code"]
    assert params["client_id"] == ["test_client_id_1234"]
    # Scope must use array notation, which is what Razorpay documents.
    assert params["scope[]"] == [REQUIRED_SCOPE]
    assert params["state"][0]
    assert params["redirect_uri"][0].endswith("/api/integrations/oauth/callback")


def test_authorize_url_state_is_single_use() -> None:
    state = parse_qs(urlparse(build_authorize_url()).query)["state"][0]
    store = get_oauth_connection_store()

    assert store.consume_state(state) is not None
    assert store.consume_state(state) is None


def test_is_configured_requires_both_halves(monkeypatch: pytest.MonkeyPatch) -> None:
    assert is_configured() is True
    monkeypatch.setattr(get_settings(), "razorpay_oauth_client_secret", None)
    assert is_configured() is False


@pytest.mark.anyio
async def test_exchange_rejects_an_unknown_state() -> None:
    """A callback whose state was never issued must not be exchanged."""
    with pytest.raises(OAuthError, match="unknown or expired"):
        await exchange_code(
            code="abc", state="never-issued", client=_as_client(_FakeClient())
        )


@pytest.mark.anyio
async def test_exchange_decodes_the_url_encoded_code() -> None:
    """Razorpay delivers the code URL-encoded and rejects it if not decoded."""
    state = parse_qs(urlparse(build_authorize_url()).query)["state"][0]
    client = _FakeClient()

    await exchange_code(code="abc%2Fdef%3D%3D", state=state, client=_as_client(client))

    _, body = client.calls[0]
    assert body["code"] == "abc/def=="
    assert body["grant_type"] == "authorization_code"
    assert body["client_secret"] == "test_client_secret_value"  # noqa: S105


@pytest.mark.anyio
async def test_exchange_persists_tokens_and_expiry() -> None:
    state = parse_qs(urlparse(build_authorize_url()).query)["state"][0]
    before = datetime.now(UTC)

    connection = await exchange_code(
        code="code", state=state, client=_as_client(_FakeClient())
    )

    assert connection.access_token.get_secret_value() == ACCESS_TOKEN
    assert connection.razorpay_account_id == ACCOUNT_ID
    # expires_in seconds must become an absolute instant.
    expected = before + timedelta(seconds=EXPIRES_IN_SECONDS)
    assert abs((connection.token_expires_at - expected).total_seconds()) < 5
    assert connection.refresh_expires_at > connection.token_expires_at

    reloaded = get_oauth_connection_store().load()
    assert reloaded is not None
    assert reloaded.razorpay_account_id == ACCOUNT_ID


@pytest.mark.anyio
async def test_exchange_surfaces_a_rejection_without_leaking_the_body() -> None:
    state = parse_qs(urlparse(build_authorize_url()).query)["state"][0]
    client = _FakeClient(payload={"error": "invalid_grant"}, status_code=400)

    with pytest.raises(OAuthError) as excinfo:
        await exchange_code(code="code", state=state, client=_as_client(client))
    assert "invalid_grant" not in str(excinfo.value)


@pytest.mark.anyio
async def test_refresh_preserves_the_account_id() -> None:
    """razorpay_account_id is absent on refresh and must not be blanked."""
    get_oauth_connection_store().save(_stored_connection())
    refresh_payload = {
        "token_type": "Bearer",
        "expires_in": EXPIRES_IN_SECONDS,
        "access_token": "rotated_access_token_value",
        "refresh_token": "rotated_refresh_token_value",
    }

    refreshed = await refresh_connection(
        client=_as_client(_FakeClient(payload=refresh_payload))
    )

    assert refreshed.razorpay_account_id == ACCOUNT_ID
    assert refreshed.public_token == "rzp_test_oauth_ABC123"  # noqa: S105
    assert refreshed.access_token.get_secret_value() == "rotated_access_token_value"


@pytest.mark.anyio
async def test_refresh_refuses_when_the_refresh_token_has_expired() -> None:
    now = datetime.now(UTC)
    get_oauth_connection_store().save(
        _stored_connection(
            token_expires_at=now - timedelta(days=1),
            refresh_expires_at=now - timedelta(hours=1),
        )
    )
    with pytest.raises(OAuthError, match="Reconnect"):
        await refresh_connection(client=_as_client(_FakeClient()))


@pytest.mark.anyio
async def test_revoke_clears_locally_even_when_the_remote_call_fails() -> None:
    """A token the operator believes is gone must not stay wired in."""
    get_oauth_connection_store().save(_stored_connection())
    failing = _FakeClient(payload={"error": "server_error"}, status_code=500)

    assert await revoke_connection(client=_as_client(failing)) is True
    assert get_oauth_connection_store().load() is None


@pytest.mark.anyio
async def test_revoke_sends_both_token_hints() -> None:
    get_oauth_connection_store().save(_stored_connection())
    client = _FakeClient(payload={"message": "Token Revoked"})

    await revoke_connection(client=_as_client(client))

    hints = [body["token_type_hint"] for _, body in client.calls]
    assert hints == ["access_token", "refresh_token"]


@pytest.mark.anyio
async def test_oauth_wins_over_the_key_pair() -> None:
    get_oauth_connection_store().save(_stored_connection())

    auth = await resolve_razorpay_auth()

    assert auth is not None
    assert auth.kind == "oauth"
    kwargs = auth.httpx_kwargs()
    assert kwargs["headers"]["Authorization"] == f"Bearer {ACCESS_TOKEN}"
    assert "auth" not in kwargs


@pytest.mark.anyio
async def test_key_pair_used_when_not_connected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_keypair01")
    monkeypatch.setattr(settings, "razorpay_key_secret", SecretStr("keypairsecret123"))

    auth = await resolve_razorpay_auth()

    assert auth is not None
    assert auth.kind == "key_pair"
    assert auth.httpx_kwargs() == {"auth": ("rzp_test_keypair01", "keypairsecret123")}


@pytest.mark.anyio
async def test_no_credentials_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """None is what makes the tools take their existing simulated path."""
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_key_id", None)
    monkeypatch.setattr(settings, "razorpay_key_secret", None)
    get_gateway_credential_store().clear()

    assert await resolve_razorpay_auth() is None


@pytest.mark.anyio
async def test_expired_access_token_is_not_offered_for_use() -> None:
    """An expired token would 401 every call and silently fall back to simulation."""
    now = datetime.now(UTC)
    get_oauth_connection_store().save(
        _stored_connection(
            token_expires_at=now - timedelta(days=1),
            refresh_expires_at=now - timedelta(hours=1),
        )
    )
    assert await resolve_razorpay_auth() is None


def test_status_endpoint_never_returns_a_token(client: TestClient) -> None:
    get_oauth_connection_store().save(_stored_connection())
    try:
        res = client.get("/api/integrations/oauth/status")
        assert res.status_code == 200
        assert ACCESS_TOKEN not in res.text
        assert REFRESH_TOKEN not in res.text
        body = res.json()
        assert body["connected"] is True
        assert body["account_id_masked"] is not None
    finally:
        get_oauth_connection_store().clear()


def test_authorize_url_endpoint_explains_when_unconfigured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "razorpay_oauth_client_id", None)
    res = client.post("/api/integrations/oauth/authorize-url")
    assert res.status_code == 409
    assert "Partner Dashboard" in res.json()["detail"]


def test_callback_redirects_on_denial(client: TestClient) -> None:
    res = client.get(
        "/api/integrations/oauth/callback",
        params={"error": "access_denied", "error_description": "Merchant declined"},
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert "oauth=error" in res.headers["location"]


def test_webhook_revocation_clears_the_connection(client: TestClient) -> None:
    get_oauth_connection_store().save(_stored_connection())
    res = client.post(
        "/api/webhooks/razorpay",
        json={"event": "account.app.authorization_revoked", "payload": {}},
    )
    assert res.status_code == 200
    assert res.json()["action_taken"] == "OAUTH_DISCONNECTED"
    assert get_oauth_connection_store().load() is None
