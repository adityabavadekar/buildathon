"""Parser for the Razorpay API key CSV offered at key creation.

Header casing and column order have varied across dashboard revisions, so
columns are matched by normalised name rather than position.
"""

from __future__ import annotations

import csv
import io

from pydantic import SecretStr

from app.core.credentials import (
    MIN_KEY_ID_LENGTH,
    MIN_SECRET_LENGTH,
    GatewayCredentials,
)

KEY_ID_HEADERS = frozenset(
    {"key_id", "keyid", "key", "apikey", "api_key", "api_key_id", "username"}
)
KEY_SECRET_HEADERS = frozenset(
    {"key_secret", "keysecret", "secret", "apisecret", "api_secret", "password"}
)
WEBHOOK_SECRET_HEADERS = frozenset(
    {"webhook_secret", "webhooksecret", "webhook_signing_secret"}
)

MAX_CSV_BYTES = 64 * 1024
EXPECTED_PAIR_COLUMNS = 2


class CredentialCsvError(ValueError):
    """Raised when the uploaded CSV cannot be read as a Razorpay key export."""


def _normalise(header: str) -> str:
    return header.strip().lower().replace(" ", "_").replace("-", "_")


def _clean(value: str | None) -> str:
    # Dashboard exports sometimes quote values or pad them with stray whitespace.
    return (value or "").strip().strip('"').strip("'")


def _decode(raw: bytes) -> str:
    if not raw:
        raise CredentialCsvError("The uploaded file is empty.")
    if len(raw) > MAX_CSV_BYTES:
        raise CredentialCsvError(
            f"File is larger than {MAX_CSV_BYTES // 1024}KB; that is not a key export."
        )
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CredentialCsvError(
            "File is not UTF-8 text. Upload the CSV exactly as downloaded."
        ) from exc


def _extract_from_header(
    header: list[str], rows: list[list[str]]
) -> tuple[str, str, str]:
    if len(rows) < EXPECTED_PAIR_COLUMNS:
        raise CredentialCsvError("The CSV has a header row but no credential row.")

    key_id = key_secret = webhook_secret = ""
    for row in rows[1:]:
        for name, value in zip(header, row, strict=False):
            if name in KEY_ID_HEADERS and not key_id:
                key_id = _clean(value)
            elif name in KEY_SECRET_HEADERS and not key_secret:
                key_secret = _clean(value)
            elif name in WEBHOOK_SECRET_HEADERS and not webhook_secret:
                webhook_secret = _clean(value)
        if key_id and key_secret:
            break
    return key_id, key_secret, webhook_secret


def _extract_headerless(first: list[str]) -> tuple[str, str, str]:
    if len(first) < EXPECTED_PAIR_COLUMNS:
        raise CredentialCsvError(
            "Could not find key id and secret columns. Expected a Razorpay key CSV."
        )
    webhook = _clean(first[2]) if len(first) > EXPECTED_PAIR_COLUMNS else ""
    return _clean(first[0]), _clean(first[1]), webhook


def parse_credential_csv(
    raw: bytes, *, updated_by: str = "operator"
) -> GatewayCredentials:
    """Parse a Razorpay key CSV into credentials.

    Raises CredentialCsvError with a reason safe to surface: the message never
    embeds a parsed secret.
    """
    rows = [
        row
        for row in csv.reader(io.StringIO(_decode(raw)))
        if any(c.strip() for c in row)
    ]
    if not rows:
        raise CredentialCsvError("No rows found in the CSV.")

    header = [_normalise(c) for c in rows[0]]
    has_known_columns = bool(
        (set(header) & KEY_ID_HEADERS) and (set(header) & KEY_SECRET_HEADERS)
    )
    key_id, key_secret, webhook_secret = (
        _extract_from_header(header, rows)
        if has_known_columns
        else _extract_headerless(rows[0])
    )

    if not key_id or not key_secret:
        raise CredentialCsvError(
            "Could not find both a key id and a key secret in the CSV."
        )
    if len(key_id) < MIN_KEY_ID_LENGTH:
        raise CredentialCsvError("The key id in the CSV is too short to be valid.")
    if len(key_secret) < MIN_SECRET_LENGTH:
        raise CredentialCsvError("The key secret in the CSV is too short to be valid.")

    return GatewayCredentials(
        key_id=key_id,
        key_secret=SecretStr(key_secret),
        webhook_secret=SecretStr(webhook_secret) if webhook_secret else None,
        source="csv_import",
        updated_by=updated_by,
    )
