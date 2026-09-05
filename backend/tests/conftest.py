"""Shared test fixtures."""

import os

# Must be set before any app.* import: get_settings() is cached on first call,
# and without this override tests run against the same database as the dev
# server, wiping its data via the test_isolation fixture's clear().
#
# Each xdist worker gets its own database (fortx_test_gw0, fortx_test_gw1, ...):
# test_isolation's clear() wipes every table before/after every test, and with
# one shared database, concurrent workers wipe each other's fixture data mid-test.
_worker_id = os.environ.get("PYTEST_XDIST_WORKER", "gw0")
os.environ.setdefault(
    "DATABASE_URL",
    f"postgresql://postgres:postgres@127.0.0.1:5432/fortx_test_{_worker_id}",
)

from collections.abc import Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.audit.repository import get_case_repository
from app.core.config import get_settings
from app.core.db import run_migrations
from app.core.operator import OperatorMode, set_operator_mode
from app.main import create_app


def _ensure_database_exists(worker_id: str) -> None:
    db_name = f"fortx_test_{worker_id}"
    conn = psycopg.connect(
        "postgresql://postgres:postgres@127.0.0.1:5432/postgres", autocommit=True
    )
    try:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        conn.close()


@pytest.fixture(scope="session", autouse=True)
def _schema() -> None:
    """Create this worker's database if needed, then bring it up to head."""
    _ensure_database_exists(_worker_id)
    run_migrations()


@pytest.fixture(autouse=True)
def _disable_operator_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """The gate defaults to on in production; tests that don't specifically
    exercise auth (nearly all of them) expect unauthenticated access, matching
    behavior before the default password was introduced.
    test_operator_auth.py overrides this per-test via its own fixture.
    """
    monkeypatch.setattr(get_settings(), "operator_password", SecretStr(""))


@pytest.fixture(autouse=True)
def test_isolation(_schema: None) -> Iterator[None]:
    repo = get_case_repository()
    repo.clear()
    set_operator_mode(OperatorMode.FULL_AUTONOMY, reason="Test isolation setup")
    yield
    repo.clear()
    set_operator_mode(OperatorMode.FULL_AUTONOMY, reason="Test isolation teardown")


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A test client with the application's lifespan run.

    Using the context manager matters: without it, ``lifespan`` never executes and
    startup work (logging configuration) is skipped.
    """
    with TestClient(create_app()) as test_client:
        yield test_client
