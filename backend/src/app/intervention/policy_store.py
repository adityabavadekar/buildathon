"""Durable PostgreSQL-backed persistence for the active MerchantPolicy."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from functools import lru_cache

from sqlalchemy import text

from app.core.db import get_db_connection
from app.core.logging import get_logger
from app.intervention.models import MerchantPolicy

logger = get_logger(__name__)


class PolicyStore:
    """PostgreSQL-backed store for the active merchant policy."""

    def load(self, merchant_id: str | None = None) -> MerchantPolicy | None:
        """Return the persisted policy from PostgreSQL if present, else None."""
        try:
            with get_db_connection() as conn:
                if merchant_id:
                    row = conn.execute(
                        text(
                            "SELECT policy_json FROM merchant_policy WHERE merchant_id = :merchant_id"
                        ),
                        {"merchant_id": merchant_id},
                    ).fetchone()
                else:
                    row = conn.execute(
                        text(
                            "SELECT policy_json FROM merchant_policy ORDER BY updated_at DESC LIMIT 1"
                        )
                    ).fetchone()

                if row and row[0]:
                    data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                    return MerchantPolicy.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("policy.store.load_error", error=str(exc))
            return None
        return None

    def save(self, policy: MerchantPolicy) -> MerchantPolicy:
        """Persist the policy in PostgreSQL and return it."""
        now = datetime.now(UTC)
        policy_json = policy.model_dump(mode="json")
        try:
            with get_db_connection() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO merchant_policy (merchant_id, policy_json, updated_at)
                        VALUES (:merchant_id, CAST(:policy_json AS jsonb), :updated_at)
                        ON CONFLICT (merchant_id) DO UPDATE SET
                            policy_json = EXCLUDED.policy_json,
                            updated_at = EXCLUDED.updated_at;
                        """
                    ),
                    {
                        "merchant_id": policy.merchant_id,
                        "policy_json": json.dumps(policy_json),
                        "updated_at": now,
                    },
                )
            logger.info("policy.store.persisted", merchant_id=policy.merchant_id)
            return policy
        except Exception as exc:
            logger.error("policy.store.save_error", error=str(exc))
            raise


@lru_cache(maxsize=1)
def get_policy_store() -> PolicyStore:
    """Return the process-wide singleton policy store."""
    return PolicyStore()
