"""Durable store for merchant-supplied Razorpay gateway credentials.

A persisted row wins over the environment so keys can be rotated without a
redeploy.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache

from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import text

from app.core.db import get_db_connection
from app.core.logging import get_logger

logger = get_logger(__name__)

MIN_KEY_ID_LENGTH = 8
MIN_SECRET_LENGTH = 12


def mask_key_id(key_id: str) -> str:
    """Elide the middle of a Razorpay key id."""
    if len(key_id) <= MIN_KEY_ID_LENGTH:
        return key_id
    return f"{key_id[:8]}...{key_id[-4:]}"


class GatewayCredentials(BaseModel):
    """A Razorpay API key pair with the optional webhook signing secret."""

    key_id: str = Field(min_length=MIN_KEY_ID_LENGTH)
    key_secret: SecretStr
    webhook_secret: SecretStr | None = None
    source: str = "manual"
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_by: str = "operator"

    def masked_key_id(self) -> str:
        """Return the key id with its middle elided, safe to log and display."""
        return mask_key_id(self.key_id)


class GatewayCredentialStore:
    """PostgreSQL-backed singleton store for gateway credentials."""

    def load(self) -> GatewayCredentials | None:
        """Return the persisted credentials, or None when none were imported."""
        try:
            with get_db_connection() as conn:
                row = conn.execute(
                    text(
                        """
                        SELECT key_id, key_secret, webhook_secret, source,
                               updated_at, updated_by
                        FROM gateway_credentials WHERE id = 1
                        """
                    )
                ).fetchone()
        except Exception as exc:  # noqa: BLE001
            logger.warning("gateway_credentials.load_error", error=str(exc))
            return None

        if row is None:
            return None
        return GatewayCredentials(
            key_id=row[0],
            key_secret=SecretStr(row[1]),
            webhook_secret=SecretStr(row[2]) if row[2] else None,
            source=row[3],
            updated_at=row[4],
            updated_by=row[5],
        )

    def save(self, creds: GatewayCredentials) -> GatewayCredentials:
        """Persist credentials, replacing any already stored."""
        with get_db_connection() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO gateway_credentials (
                        id, key_id, key_secret, webhook_secret, source,
                        updated_at, updated_by
                    ) VALUES (
                        1, :key_id, :key_secret, :webhook_secret, :source,
                        :updated_at, :updated_by
                    ) ON CONFLICT (id) DO UPDATE SET
                        key_id = EXCLUDED.key_id,
                        key_secret = EXCLUDED.key_secret,
                        webhook_secret = EXCLUDED.webhook_secret,
                        source = EXCLUDED.source,
                        updated_at = EXCLUDED.updated_at,
                        updated_by = EXCLUDED.updated_by;
                    """
                ),
                {
                    "key_id": creds.key_id,
                    "key_secret": creds.key_secret.get_secret_value(),
                    "webhook_secret": creds.webhook_secret.get_secret_value()
                    if creds.webhook_secret
                    else None,
                    "source": creds.source,
                    "updated_at": creds.updated_at,
                    "updated_by": creds.updated_by,
                },
            )
        # Never log the secret: masked id and provenance only.
        logger.info(
            "gateway_credentials.persisted",
            key_id=creds.masked_key_id(),
            source=creds.source,
            has_webhook_secret=creds.webhook_secret is not None,
        )
        return creds

    def clear(self) -> bool:
        """Delete stored credentials, reverting to the environment values."""
        with get_db_connection() as conn:
            res = conn.execute(text("DELETE FROM gateway_credentials WHERE id = 1"))
        removed = res.rowcount > 0
        if removed:
            logger.info("gateway_credentials.cleared")
        return removed


@lru_cache(maxsize=1)
def get_gateway_credential_store() -> GatewayCredentialStore:
    """Return the process-wide singleton credential store."""
    return GatewayCredentialStore()
