"""Standalone entrypoint for the Recovery Worker daemon process."""

from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.db import run_migrations
from app.core.logging import configure_logging, get_logger
from app.worker.executor import DueJobExecutor

logger = get_logger(__name__)


async def run_worker() -> None:
    """Initialize logging and run the scheduled job executor."""
    settings = get_settings()
    configure_logging(settings)
    # The worker can start before the API has ever run, so it cannot assume the
    # schema exists. Alembic is idempotent, so applying it here is safe.
    run_migrations()
    logger.info("worker.daemon_started", service="recovery_worker")
    executor = DueJobExecutor()
    await executor.run_forever(poll_interval_seconds=1.0)


def main() -> None:
    """Sync wrapper to run async worker event loop."""
    try:
        asyncio.run(run_worker())
    except (KeyboardInterrupt, SystemExit):
        logger.info("worker.daemon_stopped")


if __name__ == "__main__":
    main()
