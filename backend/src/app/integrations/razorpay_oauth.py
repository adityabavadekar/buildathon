"""The single seam that talks to auth.razorpay.com.

Never run against live Razorpay; every branch is covered by injected-client tests.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import unquote, urlencode

import httpx2
from pydantic import SecretStr

from app.core.config import get_settings
from app.core.constants import (
    OAUTH_REFRESH_TOKEN_TTL_DAYS,
    OAUTH_REFRESH_WINDOW_DAYS,
    RAZORPAY_AUTH_BASE,
)
from app.core.logging import get_logger
from app.integrations.store import OAuthConnection, get_oauth_connection_store

logger = get_logger(__name__)

REQUIRED_SCOPE = "read_write"
STATE_BYTES = 32
HTTP_TIMEOUT_SECONDS = 15.0


class OAuthError(RuntimeError):
    """Raised when an OAuth step fails. Messages are safe to surface."""


def is_configured() -> bool:
    """True when a partner client id and secret are both present."""
    settings = get_settings()
    secret = settings.razorpay_oauth_client_secret
    return bool(
        settings.razorpay_oauth_client_id
        and secret
        and secret.get_secret_value().strip()
    )


def _client_credentials() -> tuple[str, str]:
    settings = get_settings()
    client_id = settings.razorpay_oauth_client_id
    client_secret = settings.razorpay_oauth_client_secret
    if not client_id or not client_secret:
        msg = (
            "Razorpay OAuth is not configured. Register an application on the "
            "Partner Dashboard and set RAZORPAY_OAUTH_CLIENT_ID and "
            "RAZORPAY_OAUTH_CLIENT_SECRET."
        )
        raise OAuthError(msg)
    return client_id, client_secret.get_secret_value()


def callback_url() -> str:
    """Return the redirect URI, which must be whitelisted on the partner client."""
    base = get_settings().app_public_base_url.rstrip("/")
    return f"{base}/api/integrations/oauth/callback"


def build_authorize_url(*, mode: str | None = None) -> str:
    """Issue a state and return the URL to send the sub-merchant to."""
    client_id, _ = _client_credentials()
    redirect_uri = callback_url()
    state = secrets.token_urlsafe(STATE_BYTES)
    get_oauth_connection_store().remember_state(state, redirect_uri)

    # Scope uses array notation per the docs: scope[]=read_write.
    query = urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope[]": REQUIRED_SCOPE,
            "state": state,
        }
    )
    logger.info(
        "oauth.authorize_url_issued",
        mode=mode or get_settings().razorpay_oauth_mode,
        scope=REQUIRED_SCOPE,
    )
    return f"{RAZORPAY_AUTH_BASE}/authorize?{query}"


async def _post_token(
    body: dict[str, Any], *, client: httpx2.AsyncClient | None = None
) -> dict[str, Any]:
    """POST to the token endpoint and return the parsed payload."""
    url = f"{RAZORPAY_AUTH_BASE}/token"
    try:
        if client:
            resp = await client.post(url, json=body)
        else:
            async with httpx2.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as owned:
                resp = await owned.post(url, json=body)
    except (httpx2.HTTPError, OSError) as exc:
        logger.warning("oauth.token_request_failed", error=str(exc))
        msg = "Could not reach Razorpay to exchange the token."
        raise OAuthError(msg) from exc

    if not resp.is_success:
        # The body can echo request fields, so it is not surfaced to the operator.
        logger.warning("oauth.token_request_rejected", status_code=resp.status_code)
        msg = f"Razorpay rejected the token request (HTTP {resp.status_code})."
        raise OAuthError(msg)

    payload: dict[str, Any] = resp.json()
    if not payload.get("access_token") or not payload.get("refresh_token"):
        msg = "Razorpay returned a token response without the expected tokens."
        raise OAuthError(msg)
    return payload


def _connection_from_payload(
    payload: dict[str, Any],
    *,
    mode: str,
    previous: OAuthConnection | None = None,
) -> OAuthConnection:
    now = datetime.now(UTC)
    expires_in = int(payload.get("expires_in") or 0)
    return OAuthConnection(
        access_token=SecretStr(str(payload["access_token"])),
        refresh_token=SecretStr(str(payload["refresh_token"])),
        public_token=payload.get("public_token")
        or (previous.public_token if previous else None),
        # razorpay_account_id is returned on the initial exchange only, so a
        # refresh must carry the stored value forward rather than blank it.
        razorpay_account_id=payload.get("razorpay_account_id")
        or (previous.razorpay_account_id if previous else None),
        scope=str(payload.get("scope") or REQUIRED_SCOPE),
        mode=mode,
        token_expires_at=now + timedelta(seconds=expires_in),
        refresh_expires_at=now + timedelta(days=OAUTH_REFRESH_TOKEN_TTL_DAYS),
        connected_at=previous.connected_at if previous else now,
        updated_at=now,
    )


async def exchange_code(
    *,
    code: str,
    state: str,
    client: httpx2.AsyncClient | None = None,
) -> OAuthConnection:
    """Exchange an authorization code for tokens and persist the connection."""
    store = get_oauth_connection_store()
    redirect_uri = store.consume_state(state)
    if redirect_uri is None:
        msg = "Authorization state is unknown or expired. Start the connection again."
        raise OAuthError(msg)

    client_id, client_secret = _client_credentials()
    mode = get_settings().razorpay_oauth_mode

    payload = await _post_token(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            # The code arrives URL-encoded on the callback and must be decoded
            # before exchange, per the docs.
            "code": unquote(code),
            "mode": mode,
        },
        client=client,
    )
    return store.save(_connection_from_payload(payload, mode=mode))


async def refresh_connection(
    *, client: httpx2.AsyncClient | None = None
) -> OAuthConnection:
    """Rotate the access token using the stored refresh token."""
    store = get_oauth_connection_store()
    existing = store.load()
    if existing is None:
        msg = "No Razorpay account is connected."
        raise OAuthError(msg)
    if existing.is_refresh_expired:
        msg = "The refresh token has expired. Reconnect the Razorpay account."
        raise OAuthError(msg)

    client_id, client_secret = _client_credentials()
    payload = await _post_token(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": existing.refresh_token.get_secret_value(),
        },
        client=client,
    )
    logger.info("oauth.connection_refreshed", account_id=existing.masked_account_id())
    return store.save(
        _connection_from_payload(payload, mode=existing.mode, previous=existing)
    )


async def revoke_connection(*, client: httpx2.AsyncClient | None = None) -> bool:
    """Revoke both tokens at Razorpay and drop the local connection.

    The local row is cleared even when the remote call fails: leaving a token
    wired in that the operator believes is gone is the worse outcome.
    """
    store = get_oauth_connection_store()
    existing = store.load()
    if existing is None:
        return False

    try:
        client_id, client_secret = _client_credentials()
        url = f"{RAZORPAY_AUTH_BASE}/revoke"
        tokens = (
            ("access_token", existing.access_token.get_secret_value()),
            ("refresh_token", existing.refresh_token.get_secret_value()),
        )
        for hint, token in tokens:
            body = {
                "client_id": client_id,
                "client_secret": client_secret,
                "token_type_hint": hint,
                "token": token,
            }
            if client:
                await client.post(url, json=body)
            else:
                async with httpx2.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as owned:
                    await owned.post(url, json=body)
    except (httpx2.HTTPError, OSError, OAuthError) as exc:
        logger.warning("oauth.revoke_remote_failed", error=str(exc))

    return store.clear()


async def active_connection(
    *, client: httpx2.AsyncClient | None = None
) -> OAuthConnection | None:
    """A usable connection, refreshed on the read path: an expired token would 401
    into the simulated path and report success that never happened.
    """
    connection = get_oauth_connection_store().load()
    if connection is None:
        return None

    needs_refresh = connection.is_access_expired or connection.expires_within(
        timedelta(days=OAUTH_REFRESH_WINDOW_DAYS)
    )
    if needs_refresh and not connection.is_refresh_expired:
        try:
            return await refresh_connection(client=client)
        except OAuthError as exc:
            logger.warning("oauth.proactive_refresh_failed", error=str(exc))

    return None if connection.is_access_expired else connection
