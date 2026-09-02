"""Identifier helpers shared across the ingestion and measurement paths."""

from __future__ import annotations

RUN_TAG_SEPARATOR = "__"


def stable_payment_key(payment_id: str) -> str:
    """Return the payment id with any benchmark run suffix removed.

    Replays namespace ids per run to dodge idempotency, but arm assignment must
    stay identical across runs or measured lift is not comparable.
    """
    return payment_id.split(RUN_TAG_SEPARATOR, 1)[0]
