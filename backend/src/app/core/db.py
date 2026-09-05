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
    is usable without a separate manual migration step. Checks the current
    revision before calling Alembic's upgrade machinery: when already at head,
    this skips loading command.upgrade's full config/logging setup entirely,
    which otherwise re-parses every migration script on every call -- a real
    cost when invoked per-test rather than once per process.

    Wrapped in a session-level Postgres advisory lock: two callers racing on a
    fresh database (e.g. concurrent test fixture setup) would otherwise both
    see "not at head" and both run CREATE TABLE, one failing on a duplicate key.
    """
    from alembic.config import Config  # noqa: PLC0415
    from alembic.script import ScriptDirectory  # noqa: PLC0415

    ini_path = Path(__file__).resolve().parents[3] / "alembic.ini"
    config = Config(str(ini_path))
    config.set_main_option("script_location", str(ini_path.parent / "alembic"))

    script = ScriptDirectory.from_config(config)
    head_revision = script.get_current_head()

    # One shared key so every caller contends for the same advisory lock.
    lock_key = 918_273_645

    engine = get_db_engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": lock_key})
        try:
            has_version_table = conn.execute(
                text("SELECT to_regclass('public.alembic_version') IS NOT NULL")
            ).scalar()
            current_revision = (
                conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
                if has_version_table
                else None
            )

            if current_revision == head_revision:
                logger.info("db.migrations_already_current", revision=head_revision)
                return

            from alembic import command  # noqa: PLC0415

            command.upgrade(config, "head")
            logger.info("db.migrations_applied")
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
