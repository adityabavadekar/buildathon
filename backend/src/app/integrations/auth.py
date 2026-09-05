"""Bearer and key-pair auth need different httpx arguments, so callers splat
httpx_kwargs() instead of each branching. OAuth wins, then imported or env keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.core.credential_resolver import resolve_gateway_credentials
from app.core.logging import get_logger
from app.integrations.razorpay_oauth import active_connection

logger = get_logger(__name__)


@dataclass(frozen=True)
class RazorpayAuth:
    """Resolved credentials for one outbound Razorpay call."""

    kind: Literal["oauth", "key_pair"]
    account_id: str | None = None
    bearer_token: str | None = None
    key_pair: tuple[str, str] | None = None

    def httpx_kwargs(self) -> dict[str, Any]:
        """Return the httpx keyword arguments that authenticate the request."""
        if self.kind == "oauth" and self.bearer_token:
            return {"headers": {"Authorization": f"Bearer {self.bearer_token}"}}
        if self.key_pair:
            return {"auth": self.key_pair}
        # Unreachable via the resolver, which never builds an empty instance.
        msg = "RazorpayAuth carries no usable credentials"
        raise ValueError(msg)

    @property
    def display_key(self) -> str:
        """Non-sensitive identifier for logs and audit rows."""
        if self.kind == "oauth":
            return self.account_id or "oauth"
        return self.key_pair[0] if self.key_pair else "unknown"


async def resolve_razorpay_auth() -> RazorpayAuth | None:
    """Return how to authenticate, or None when no credentials are available.

    ``None`` is the same condition the tools previously tested as
    ``not (key_id and key_secret)``, so their simulated fallbacks are unchanged.
    """
    connection = await active_connection()
    if connection:
        return RazorpayAuth(
            kind="oauth",
            account_id=connection.razorpay_account_id,
            bearer_token=connection.access_token.get_secret_value(),
        )

    key_id, key_secret = resolve_gateway_credentials()
    if key_id and key_secret:
        return RazorpayAuth(kind="key_pair", key_pair=(key_id, key_secret))
    return None
