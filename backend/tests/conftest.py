"""Shared test fixtures."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.audit.repository import get_case_repository
from app.core.db import run_migrations
from app.core.operator import OperatorMode, set_operator_mode
from app.main import create_app


@pytest.fixture(scope="session", autouse=True)
def _schema() -> None:
    """Bring the test database up to head before any test opens a connection."""
    run_migrations()


@pytest.fixture(autouse=True)
def test_isolation(_schema: None) -> Iterator[None]:
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
