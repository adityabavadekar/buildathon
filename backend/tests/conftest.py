"""Shared test fixtures."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.operator import OperatorMode, set_operator_mode
from app.main import create_app


@pytest.fixture(autouse=True)
def reset_operator_mode() -> Iterator[None]:
    """Ensure tests run under default FULL_AUTONOMY mode and reset after."""
    set_operator_mode(OperatorMode.FULL_AUTONOMY, reason="Test isolation setup")
    yield
    set_operator_mode(OperatorMode.FULL_AUTONOMY, reason="Test isolation teardown")


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A test client with the application's lifespan run.

    Using the context manager matters: without it, ``lifespan`` never executes and
    startup work (logging configuration) is skipped.
    """
    with TestClient(create_app()) as test_client:
        yield test_client
