"""Single read path for gateway credentials.

Every consumer must resolve through here rather than reading Settings directly,
or an imported key is honoured by some call sites and ignored by others.
"""

from __future__ import annotations

from pydantic import SecretStr

from app.core.config import get_settings
from app.core.credentials import get_gateway_credential_store


def _secret_text(value: SecretStr | str | None) -> str | None:
    if value is None:
        return None
    text_value = (
        value.get_secret_value() if isinstance(value, SecretStr) else str(value)
    ).strip()
    return text_value or None


def resolve_gateway_credentials() -> tuple[str | None, str | None]:
    """Return the active (key_id, key_secret), preferring imported credentials."""
    stored = get_gateway_credential_store().load()
    if stored:
        return stored.key_id, _secret_text(stored.key_secret)

    settings = get_settings()
    return settings.razorpay_key_id, _secret_text(settings.razorpay_key_secret)


def resolve_webhook_secret() -> str | None:
    """Return the active webhook signing secret, preferring imported credentials."""
    stored = get_gateway_credential_store().load()
    if stored and stored.webhook_secret:
        return _secret_text(stored.webhook_secret)
    return _secret_text(get_settings().razorpay_webhook_secret)
