"""Shared PostgreSQL engine and connection pool management."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.pool import QueuePool

from app.core.config import get_settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Generator

logger = get_logger(__name__)

_engine: Engine | None = None


def get_db_engine() -> Engine:
    """Return the process-wide SQLAlchemy Engine for PostgreSQL."""
    global _engine  # noqa: PLW0603
    if _engine is None:
        settings = get_settings()
        url = settings.database_url

        # Ensure postgresql+psycopg:// scheme is used for SQLAlchemy with psycopg3
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg://", 1)
        elif url.startswith("postgresql://") and not url.startswith(
            "postgresql+psycopg://"
        ):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)

        connect_args: dict[str, Any] = {
            "options": f"-c statement_timeout={settings.postgres_statement_timeout_ms}"
        }

        _engine = create_engine(
            url,
            poolclass=QueuePool,
            pool_size=settings.postgres_pool_size,
            max_overflow=settings.postgres_max_overflow,
            pool_timeout=settings.postgres_pool_timeout_seconds,
            pool_recycle=1800,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        logger.info(
            "db.engine_initialized",
            pool_size=settings.postgres_pool_size,
            max_overflow=settings.postgres_max_overflow,
        )
    return _engine


def reset_db_engine() -> None:
    """Dispose and reset the process-wide SQLAlchemy engine (useful for testing)."""
    global _engine  # noqa: PLW0603
    if _engine is not None:
        _engine.dispose()
        _engine = None


@contextmanager
def get_db_connection() -> Generator[Connection]:
    """Check out a connection from the pool and yield it in a transaction."""
    engine = get_db_engine()
    with engine.begin() as conn:
        yield conn


def check_db_health() -> bool:
    """Check if the database is reachable and accepting queries."""
    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("db.health_check_failed", error=str(exc))
        return False


def run_migrations() -> None:
    """Bring the database schema up to head via Alembic.

    Invoked from application start-up and the test fixtures so a fresh database
    is usable without a separate manual migration step.
    """
    from alembic.config import Config  # noqa: PLC0415

    from alembic import command  # noqa: PLC0415

    # alembic.ini lives at the backend root, four parents up from this module.
    ini_path = Path(__file__).resolve().parents[3] / "alembic.ini"
    config = Config(str(ini_path))
    config.set_main_option("script_location", str(ini_path.parent / "alembic"))
    command.upgrade(config, "head")
    logger.info("db.migrations_applied")
