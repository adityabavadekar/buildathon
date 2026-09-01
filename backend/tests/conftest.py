"""Shared test fixtures."""

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Isolate durable stores (case DB and merchant policy) into a per-session temp
# directory. Both backends are built from get_settings() on first use, so these
# env vars must be set before any app module imports construct settings. Without
# this, HTTP-level tests share persisted state across runs: a fixed payment_id
# returns ALREADY_QUEUED on re-run and a previously saved policy overrides the
# default assertions.
_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="fortx_test_"))
os.environ["APP_DATABASE_PATH"] = str(_TEST_DATA_DIR / "test_recovery.db")
os.environ["APP_POLICY_CONFIG_PATH"] = str(_TEST_DATA_DIR / "policy_config.json")

from app.audit.repository import get_case_repository
from app.core.operator import OperatorMode, set_operator_mode
from app.main import create_app


@pytest.fixture(autouse=True)
def test_isolation() -> Iterator[None]:
    """Ensure tests run against a clean database under default FULL_AUTONOMY mode."""
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
