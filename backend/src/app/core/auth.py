"""Operator login and signed session cookies, stdlib-only for one shared password.

No configured password disables the gate; GET /auth/session reports that honestly.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Cookie, HTTPException, status

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

SESSION_COOKIE_NAME = "fortx_session"
PBKDF2_ITERATIONS = 240_000
PBKDF2_SALT = b"fortx-operator-session-v1"
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 300


def auth_enabled() -> bool:
    """True when an operator password is configured."""
    password = get_settings().operator_password
    return bool(password and password.get_secret_value().strip())


def _password_digest(password: str) -> bytes:
    """Derive a slow hash so a leaked config is not instantly reversible."""
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), PBKDF2_SALT, PBKDF2_ITERATIONS
    )


def verify_password(candidate: str) -> bool:
    """Compare a submitted password in constant time."""
    configured = get_settings().operator_password
    if not configured:
        return False
    expected = configured.get_secret_value().strip()
    if not expected:
        return False
    return hmac.compare_digest(_password_digest(candidate), _password_digest(expected))


def _signing_key() -> bytes:
    """Session signing key. Unconfigured, a per-process random key logs everyone
    out on restart, which beats a predictable default anyone could mint against.
    """
    configured = get_settings().session_secret
    if configured and configured.get_secret_value().strip():
        return configured.get_secret_value().strip().encode("utf-8")
    return _EPHEMERAL_KEY


_EPHEMERAL_KEY = secrets.token_bytes(32)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def issue_session_token() -> str:
    """Mint a signed, expiring session token."""
    ttl_seconds = get_settings().session_ttl_hours * 3600
    payload = json.dumps(
        {"sub": "operator", "exp": int(time.time()) + ttl_seconds},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    signature = hmac.new(_signing_key(), payload, hashlib.sha256).digest()
    return f"{_b64(payload)}.{_b64(signature)}"


def verify_session_token(token: str | None) -> bool:
    """Return True when the token is well-formed, correctly signed, and unexpired."""
    if not token or "." not in token:
        return False
    encoded_payload, _, encoded_signature = token.partition(".")
    try:
        payload = _unb64(encoded_payload)
        signature = _unb64(encoded_signature)
    except (ValueError, TypeError):
        return False

    expected = hmac.new(_signing_key(), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        return False

    try:
        claims = json.loads(payload)
    except json.JSONDecodeError:
        return False
    expiry = claims.get("exp")
    return isinstance(expiry, int) and expiry > int(time.time())


@dataclass
class LoginThrottle:
    """Failed-attempt counter; one shared password is brute-forceable without it.

    Process-local: a multi-instance deployment would need a shared counter.
    """

    failures: int = 0
    locked_until: float = field(default=0.0)

    def is_locked(self) -> bool:
        return time.monotonic() < self.locked_until

    def seconds_remaining(self) -> int:
        return max(0, int(self.locked_until - time.monotonic()))

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= MAX_FAILED_ATTEMPTS:
            self.locked_until = time.monotonic() + LOCKOUT_SECONDS
            self.failures = 0
            logger.warning("auth.login_locked_out", lockout_seconds=LOCKOUT_SECONDS)

    def reset(self) -> None:
        self.failures = 0
        self.locked_until = 0.0


_THROTTLE = LoginThrottle()


def get_login_throttle() -> LoginThrottle:
    """Return the process-wide login throttle."""
    return _THROTTLE


async def require_operator(
    fortx_session: Annotated[str | None, Cookie()] = None,
) -> None:
    """Reject the request unless a valid session cookie is present. A no-op when
    no password is configured.
    """
    if not auth_enabled():
        return
    if not verify_session_token(fortx_session):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Operator authentication required.",
        )
