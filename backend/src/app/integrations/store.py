"""Singleton OAuth connection row; the engine has no per-merchant routing.

Pending states persist here because the callback may hit a different worker.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import lru_cache

from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import text

from app.core.constants import OAUTH_STATE_TTL_MINUTES
from app.core.db import get_db_connection
from app.core.logging import get_logger

logger = get_logger(__name__)

ACCOUNT_ID_MASK_MIN_LENGTH = 8


class OAuthConnection(BaseModel):
    """Tokens and metadata for one authorized sub-merchant."""

    access_token: SecretStr
    refresh_token: SecretStr
    public_token: str | None = None
    razorpay_account_id: str | None = None
    scope: str = "read_write"
    mode: str = "test"
    token_expires_at: datetime
    refresh_expires_at: datetime
    connected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_by: str = "operator"

    @property
    def is_access_expired(self) -> bool:
        return self.token_expires_at <= datetime.now(UTC)

    @property
    def is_refresh_expired(self) -> bool:
        return self.refresh_expires_at <= datetime.now(UTC)

    def expires_within(self, window: timedelta) -> bool:
        """True when the access token should be refreshed pre-emptively."""
        return self.token_expires_at - datetime.now(UTC) <= window

    def masked_account_id(self) -> str | None:
        """Account id safe to log and display."""
        if not self.razorpay_account_id:
            return None
        if len(self.razorpay_account_id) <= ACCOUNT_ID_MASK_MIN_LENGTH:
            return self.razorpay_account_id
        return f"{self.razorpay_account_id[:6]}...{self.razorpay_account_id[-4:]}"


class OAuthConnectionStore:
    """PostgreSQL-backed singleton store for the OAuth connection."""

    def load(self) -> OAuthConnection | None:
        """Return the stored connection, or None when not connected."""
        try:
            with get_db_connection() as conn:
                row = conn.execute(
                    text(
                        """
                        SELECT access_token, refresh_token, public_token,
                               razorpay_account_id, scope, mode, token_expires_at,
                               refresh_expires_at, connected_at, updated_at,
                               updated_by
                        FROM oauth_connection WHERE id = 1
                        """
                    )
                ).fetchone()
        except Exception as exc:  # noqa: BLE001
            logger.warning("oauth.connection.load_error", error=str(exc))
            return None

        if row is None:
            return None
        return OAuthConnection(
            access_token=SecretStr(row[0]),
            refresh_token=SecretStr(row[1]),
            public_token=row[2],
            razorpay_account_id=row[3],
            scope=row[4],
            mode=row[5],
            token_expires_at=row[6],
            refresh_expires_at=row[7],
            connected_at=row[8],
            updated_at=row[9],
            updated_by=row[10],
        )

    def save(self, connection: OAuthConnection) -> OAuthConnection:
        """Persist the connection, replacing any existing one."""
        with get_db_connection() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO oauth_connection (
                        id, access_token, refresh_token, public_token,
                        razorpay_account_id, scope, mode, token_expires_at,
                        refresh_expires_at, connected_at, updated_at, updated_by
                    ) VALUES (
                        1, :access_token, :refresh_token, :public_token,
                        :account_id, :scope, :mode, :token_expires_at,
                        :refresh_expires_at, :connected_at, :updated_at,
                        :updated_by
                    ) ON CONFLICT (id) DO UPDATE SET
                        access_token = EXCLUDED.access_token,
                        refresh_token = EXCLUDED.refresh_token,
                        public_token = EXCLUDED.public_token,
                        razorpay_account_id = EXCLUDED.razorpay_account_id,
                        scope = EXCLUDED.scope,
                        mode = EXCLUDED.mode,
                        token_expires_at = EXCLUDED.token_expires_at,
                        refresh_expires_at = EXCLUDED.refresh_expires_at,
                        connected_at = EXCLUDED.connected_at,
                        updated_at = EXCLUDED.updated_at,
                        updated_by = EXCLUDED.updated_by;
                    """
                ),
                {
                    "access_token": connection.access_token.get_secret_value(),
                    "refresh_token": connection.refresh_token.get_secret_value(),
                    "public_token": connection.public_token,
                    "account_id": connection.razorpay_account_id,
                    "scope": connection.scope,
                    "mode": connection.mode,
                    "token_expires_at": connection.token_expires_at,
                    "refresh_expires_at": connection.refresh_expires_at,
                    "connected_at": connection.connected_at,
                    "updated_at": connection.updated_at,
                    "updated_by": connection.updated_by,
                },
            )
        # Tokens are never logged: account id and expiry only.
        logger.info(
            "oauth.connection.persisted",
            account_id=connection.masked_account_id(),
            mode=connection.mode,
            scope=connection.scope,
            token_expires_at=connection.token_expires_at.isoformat(),
        )
        return connection

    def clear(self) -> bool:
        """Drop the connection, reverting to key-pair authentication."""
        with get_db_connection() as conn:
            res = conn.execute(text("DELETE FROM oauth_connection WHERE id = 1"))
        removed = res.rowcount > 0
        if removed:
            logger.info("oauth.connection.cleared")
        return removed

    def remember_state(self, state: str, redirect_uri: str) -> None:
        """Record an issued authorization state so the callback can be verified."""
        now = datetime.now(UTC)
        with get_db_connection() as conn:
            # Opportunistic cleanup: states are single-use and short-lived, so this
            # table would otherwise grow with every abandoned authorize attempt.
            conn.execute(
                text("DELETE FROM oauth_auth_state WHERE created_at < :cutoff"),
                {"cutoff": now - timedelta(minutes=OAUTH_STATE_TTL_MINUTES)},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO oauth_auth_state (state, redirect_uri, created_at)
                    VALUES (:state, :redirect_uri, :created_at)
                    ON CONFLICT (state) DO NOTHING;
                    """
                ),
                {"state": state, "redirect_uri": redirect_uri, "created_at": now},
            )

    def consume_state(self, state: str) -> str | None:
        """Verify and single-use an authorization state, returning its redirect_uri.

        Returns None when the state was never issued, already used, or has aged
        out - all of which must fail the callback rather than proceed.
        """
        cutoff = datetime.now(UTC) - timedelta(minutes=OAUTH_STATE_TTL_MINUTES)
        with get_db_connection() as conn:
            row = conn.execute(
                text(
                    """
                    DELETE FROM oauth_auth_state
                    WHERE state = :state AND created_at >= :cutoff
                    RETURNING redirect_uri;
                    """
                ),
                {"state": state, "cutoff": cutoff},
            ).fetchone()
        return str(row[0]) if row else None


@lru_cache(maxsize=1)
def get_oauth_connection_store() -> OAuthConnectionStore:
    """Return the process-wide singleton OAuth connection store."""
    return OAuthConnectionStore()
