"""Operator login, logout, and session status."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.audit.global_log import record_global_audit
from app.core.auth import (
    SESSION_COOKIE_NAME,
    auth_enabled,
    get_login_throttle,
    issue_session_token,
    verify_password,
    verify_session_token,
)
from app.core.config import get_settings
from app.core.enums import AuditActor
from app.core.logging import get_logger

router = APIRouter(prefix="/auth", tags=["auth"])

logger = get_logger("api.auth")

MAX_PASSWORD_LENGTH = 256


class LoginRequest(BaseModel):
    """An operator password submission."""

    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class SessionStatus(BaseModel):
    """Whether the gate is on, and whether this caller is through it."""

    auth_enabled: bool
    authenticated: bool
    ttl_hours: int


@router.get("/session", response_model=SessionStatus, summary="Get Session Status")
async def get_session(
    fortx_session: Annotated[str | None, Cookie()] = None,
) -> SessionStatus:
    """Report whether authentication is enabled and the caller is signed in.

    Always reachable: the dashboard has to ask whether a login is needed before
    it can have a session.
    """
    enabled = auth_enabled()
    return SessionStatus(
        auth_enabled=enabled,
        authenticated=(not enabled) or verify_session_token(fortx_session),
        ttl_hours=get_settings().session_ttl_hours,
    )


@router.post("/login", response_model=SessionStatus, summary="Operator Login")
async def login(payload: LoginRequest, response: Response) -> SessionStatus:
    """Exchange the operator password for a signed session cookie."""
    settings = get_settings()
    if not auth_enabled():
        # Nothing to log in to; say so rather than minting a meaningless session.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Operator authentication is not configured on this deployment.",
        )

    throttle = get_login_throttle()
    if throttle.is_locked():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Too many failed attempts. Try again in "
                f"{throttle.seconds_remaining()} seconds."
            ),
        )

    if not verify_password(payload.password):
        throttle.record_failure()
        logger.warning("auth.login_failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password.",
        )

    throttle.reset()
    token = issue_session_token()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        # Cookies are only marked Secure in production: local development is
        # served over plain HTTP and the cookie would never be stored.
        secure=settings.env == "production",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
    record_global_audit(
        event_name="auth.operator_logged_in",
        actor=AuditActor.HUMAN_OPERATOR,
        reason="Operator signed in to the dashboard.",
        notes=f"Session valid for {settings.session_ttl_hours} hours.",
    )
    return SessionStatus(
        auth_enabled=True, authenticated=True, ttl_hours=settings.session_ttl_hours
    )


@router.post("/logout", response_model=SessionStatus, summary="Operator Logout")
async def logout(response: Response) -> SessionStatus:
    """Clear the session cookie."""
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    enabled = auth_enabled()
    return SessionStatus(
        auth_enabled=enabled,
        authenticated=not enabled,
        ttl_hours=get_settings().session_ttl_hours,
    )
