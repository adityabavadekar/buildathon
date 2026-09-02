"""Tests for Razorpay key CSV credential import."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.core.credential_csv import CredentialCsvError, parse_credential_csv
from app.core.credential_resolver import resolve_gateway_credentials
from app.core.credentials import get_gateway_credential_store

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

# Synthetic fixture value, long enough to clear the parser's length floor.
REAL_SECRET = "supersecretvalue123"  # noqa: S105


def test_parses_headered_export() -> None:
    raw = f"key_id,key_secret\nrzp_test_abc123456,{REAL_SECRET}\n".encode()
    creds = parse_credential_csv(raw)
    assert creds.key_id == "rzp_test_abc123456"
    assert creds.key_secret.get_secret_value() == REAL_SECRET
    assert creds.source == "csv_import"


def test_parses_alternate_header_names_and_webhook_secret() -> None:
    raw = (
        f"API Key,API Secret,Webhook Secret\nrzp_live_xyz98765,{REAL_SECRET},whsec_9876543\n"
    ).encode()
    creds = parse_credential_csv(raw)
    assert creds.key_id == "rzp_live_xyz98765"
    assert creds.webhook_secret is not None
    assert creds.webhook_secret.get_secret_value() == "whsec_9876543"


def test_parses_headerless_pair() -> None:
    creds = parse_credential_csv(f"rzp_test_abc123456,{REAL_SECRET}\n".encode())
    assert creds.key_id == "rzp_test_abc123456"


def test_masked_key_id_never_exposes_middle() -> None:
    creds = parse_credential_csv(
        f"key_id,key_secret\nrzp_test_abc123456,{REAL_SECRET}\n".encode()
    )
    masked = creds.masked_key_id()
    assert masked.startswith("rzp_test")
    assert "..." in masked
    assert REAL_SECRET not in masked


@pytest.mark.parametrize(
    ("raw", "fragment"),
    [
        (b"", "empty"),
        (b"nothing_useful\njust_one_column\n", "key id and secret"),
        (b"key_id,key_secret\n", "no credential row"),
        (b"key_id,key_secret\nshort,alsotooshortvalue\n", "key id"),
        (b"key_id,key_secret\nrzp_test_abc123456,tiny\n", "key secret"),
    ],
)
def test_rejects_malformed_input(raw: bytes, fragment: str) -> None:
    with pytest.raises(CredentialCsvError, match=fragment):
        parse_credential_csv(raw)


def test_error_messages_never_contain_the_secret() -> None:
    raw = f"key_id,key_secret\nbad,{REAL_SECRET}\n".encode()
    with pytest.raises(CredentialCsvError) as excinfo:
        parse_credential_csv(raw)
    assert REAL_SECRET not in str(excinfo.value)


def test_stored_credentials_take_precedence_over_environment() -> None:
    store = get_gateway_credential_store()
    store.clear()
    try:
        creds = parse_credential_csv(
            f"key_id,key_secret\nrzp_test_stored9999,{REAL_SECRET}\n".encode()
        )
        store.save(creds)
        key_id, key_secret = resolve_gateway_credentials()
        assert key_id == "rzp_test_stored9999"
        assert key_secret == REAL_SECRET
    finally:
        store.clear()


def test_import_endpoint_masks_secret_in_response(client: TestClient) -> None:
    store = get_gateway_credential_store()
    store.clear()
    try:
        body = f"key_id,key_secret\nrzp_test_upload777,{REAL_SECRET}\n".encode()
        res = client.post(
            "/api/settings/gateway-credentials/import",
            files={"file": ("keys.csv", body, "text/csv")},
        )
        assert res.status_code == 200
        payload = res.json()
        assert payload["configured"] is True
        assert payload["source"] == "csv_import"
        assert REAL_SECRET not in res.text
        assert payload["key_id_masked"] is not None
        assert REAL_SECRET not in payload["key_id_masked"]
    finally:
        store.clear()


def test_import_endpoint_rejects_junk(client: TestClient) -> None:
    res = client.post(
        "/api/settings/gateway-credentials/import",
        files={"file": ("notes.csv", b"hello world\n", "text/csv")},
    )
    assert res.status_code == 400
