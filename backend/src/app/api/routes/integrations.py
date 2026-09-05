"""Razorpay Partner OAuth connect, refresh, and revoke."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.audit.global_log import record_global_audit
from app.core.config import get_settings
from app.core.enums import AuditActor
from app.core.logging import get_logger
from app.integrations.razorpay_oauth import (
    REQUIRED_SCOPE,
    OAuthError,
    build_authorize_url,
    callback_url,
    exchange_code,
    is_configured,
    refresh_connection,
    revoke_connection,
)
from app.integrations.store import get_oauth_connection_store

router = APIRouter(prefix="/integrations", tags=["integrations"])

logger = get_logger("api.integrations")


class OAuthConnectionStatus(BaseModel):
    """Non-sensitive view of the OAuth connection. Never carries a token."""

    configured: bool
    connected: bool
    account_id: str | None
    account_id_masked: str | None
    public_token: str | None
    scope: str | None
    mode: str | None
    token_expires_at: str | None
    refresh_expires_at: str | None
    connected_at: str | None
    access_token_expired: bool
    refresh_token_expired: bool
    redirect_uri: str
    required_scope: str


class AuthorizeUrlResponse(BaseModel):
    """Where to send the sub-merchant to authorize the partner application."""

    authorize_url: str


def _status() -> OAuthConnectionStatus:
    connection = get_oauth_connection_store().load()
    settings = get_settings()
    if connection is None:
        return OAuthConnectionStatus(
            configured=is_configured(),
            connected=False,
            account_id=None,
            account_id_masked=None,
            public_token=None,
            scope=None,
            mode=settings.razorpay_oauth_mode,
            token_expires_at=None,
            refresh_expires_at=None,
            connected_at=None,
            access_token_expired=False,
            refresh_token_expired=False,
            redirect_uri=callback_url(),
            required_scope=REQUIRED_SCOPE,
        )

    return OAuthConnectionStatus(
        configured=is_configured(),
        connected=not connection.is_access_expired,
        account_id=connection.razorpay_account_id,
        account_id_masked=connection.masked_account_id(),
        public_token=connection.public_token,
        scope=connection.scope,
        mode=connection.mode,
        token_expires_at=connection.token_expires_at.isoformat(),
        refresh_expires_at=connection.refresh_expires_at.isoformat(),
        connected_at=connection.connected_at.isoformat(),
        access_token_expired=connection.is_access_expired,
        refresh_token_expired=connection.is_refresh_expired,
        redirect_uri=callback_url(),
        required_scope=REQUIRED_SCOPE,
    )


@router.get(
    "/oauth/status",
    response_model=OAuthConnectionStatus,
    summary="Get Razorpay OAuth Connection Status",
)
async def get_oauth_status() -> OAuthConnectionStatus:
    """Report the OAuth connection without revealing any token."""
    return _status()


@router.post(
    "/oauth/authorize-url",
    response_model=AuthorizeUrlResponse,
    summary="Begin Razorpay OAuth Authorization",
)
async def post_authorize_url() -> AuthorizeUrlResponse:
    """Issue a state and return the Razorpay authorization URL."""
    if not is_configured():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Razorpay OAuth is not configured. Register an application on the "
                "Partner Dashboard, then set RAZORPAY_OAUTH_CLIENT_ID and "
                "RAZORPAY_OAUTH_CLIENT_SECRET."
            ),
        )
    try:
        return AuthorizeUrlResponse(authorize_url=build_authorize_url())
    except OAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


def _redirect_to_dashboard(outcome: str, detail: str | None = None) -> RedirectResponse:
    """Send the browser back to Integrations. The callback lands here because the
    dashboard is one client-rendered page and Next rewrites /api/* wholesale.
    """
    base = get_settings().app_public_base_url.rstrip("/")
    params = {"oauth": outcome}
    if detail:
        params["oauth_detail"] = detail
    return RedirectResponse(
        url=f"{base}/?{urlencode(params)}#settings-integrations",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/oauth/callback", summary="Razorpay OAuth Redirect Callback")
async def oauth_callback(
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
    error_description: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    """Complete the authorization and redirect back to the dashboard.

    Always redirects rather than returning JSON: a browser lands here, so an error
    must be something the operator can read on the Integrations screen.
    """
    if error:
        logger.warning("oauth.callback_denied", error=error)
        record_global_audit(
            event_name="integrations.oauth_authorization_failed",
            actor=AuditActor.HUMAN_OPERATOR,
            reason="Razorpay returned an authorization error.",
            notes=error_description or error,
            decision_inputs={"error": error},
        )
        return _redirect_to_dashboard("error", error_description or error)

    if not code or not state:
        return _redirect_to_dashboard("error", "Callback was missing code or state.")

    try:
        connection = await exchange_code(code=code, state=state)
    except OAuthError as exc:
        logger.warning("oauth.callback_exchange_failed", error=str(exc))
        return _redirect_to_dashboard("error", str(exc))

    record_global_audit(
        event_name="integrations.oauth_connected",
        actor=AuditActor.HUMAN_OPERATOR,
        reason="Sub-merchant authorized the FORTX partner application.",
        notes=f"Connected account {connection.masked_account_id() or 'unknown'}.",
        decision_inputs={
            "account_id_masked": connection.masked_account_id(),
            "scope": connection.scope,
            "mode": connection.mode,
        },
    )
    return _redirect_to_dashboard("connected")


@router.post(
    "/oauth/refresh",
    response_model=OAuthConnectionStatus,
    summary="Refresh The Razorpay OAuth Token",
)
async def post_oauth_refresh() -> OAuthConnectionStatus:
    """Rotate the access token using the stored refresh token."""
    try:
        connection = await refresh_connection()
    except OAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    record_global_audit(
        event_name="integrations.oauth_refreshed",
        actor=AuditActor.HUMAN_OPERATOR,
        reason="Operator refreshed the Razorpay OAuth token.",
        notes=f"Token now valid until {connection.token_expires_at.isoformat()}.",
        decision_inputs={"account_id_masked": connection.masked_account_id()},
    )
    return _status()


@router.delete(
    "/oauth",
    response_model=OAuthConnectionStatus,
    summary="Disconnect The Razorpay OAuth Account",
)
async def delete_oauth_connection() -> OAuthConnectionStatus:
    """Revoke the tokens at Razorpay and drop the local connection."""
    removed = await revoke_connection()
    if removed:
        record_global_audit(
            event_name="integrations.oauth_disconnected",
            actor=AuditActor.HUMAN_OPERATOR,
            reason="Operator disconnected the Razorpay OAuth account.",
            notes="Reverted to API key pair authentication.",
        )
    return _status()
