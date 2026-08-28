"""FastAPI application factory and process entry point.

Run locally with ``uv run fastapi dev src/app/main.py``, or ``make dev`` from the
repository root to start this alongside the frontend.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import health
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestIDMiddleware

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start-up and shut-down. ``@app.on_event`` is deprecated; this replaces it."""
    settings: Settings = get_settings()
    configure_logging(settings)
    logger.info(
        "service.startup",
        version=__version__,
        env=settings.env,
        log_level=settings.log_level,
    )
    yield
    logger.info("service.shutdown")


def create_app() -> FastAPI:
    """Build the application.

    A factory rather than a module-level singleton so tests can construct an
    isolated instance with overridden settings.
    """
    settings = get_settings()

    app = FastAPI(
        title="Revenue Recovery",
        description=(
            "Detects at-risk revenue, diagnoses cause, runs bounded interventions, "
            "and proves recovery with an audit trail."
        ),
        version=__version__,
        lifespan=lifespan,
    )

    # Request IDs are bound before anything else so every downstream log line and
    # any later audit record can be traced to the originating request.
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-request-id"],
    )

    app.include_router(health.router)
    return app


app = create_app()
