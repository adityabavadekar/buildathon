"""FastAPI application factory and process entry point.

Run locally with ``uv run fastapi dev src/app/main.py``, or ``make dev`` from the
repository root to start this alongside the frontend.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import (
    analytics,
    auth,
    benchmark,
    cases,
    customers,
    experiments,
    health,
    integrations,
    operator,
    pipeline,
    policies,
    rail_health,
    simulation,
    webhooks,
    workflows,
)
from app.api.routes import settings as settings_router
from app.core.auth import require_operator
from app.core.config import Settings, get_settings
from app.core.db import run_migrations
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
    run_migrations()
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
    origins = settings.cors_origins or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=r"https?://.*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    # Health check is available at both /health and /api/health
    app.include_router(health.router)
    app.include_router(health.router, prefix="/api")

    # Unauthenticated by necessity: the dashboard must ask whether a login is
    # required before it has a session, and webhooks authenticate by HMAC.
    app.include_router(auth.router, prefix="/api")
    app.include_router(webhooks.router, prefix="/api")

    # Gated by default, so a route added later is protected without opting in.
    # require_operator is a no-op when no operator password is configured.
    guarded = [Depends(require_operator)]
    app.include_router(cases.router, prefix="/api", dependencies=guarded)
    app.include_router(customers.router, prefix="/api", dependencies=guarded)
    app.include_router(analytics.router, prefix="/api", dependencies=guarded)
    app.include_router(policies.router, prefix="/api", dependencies=guarded)
    app.include_router(rail_health.router, prefix="/api", dependencies=guarded)
    app.include_router(simulation.router, prefix="/api", dependencies=guarded)
    app.include_router(pipeline.router, prefix="/api", dependencies=guarded)
    app.include_router(operator.router, prefix="/api", dependencies=guarded)
    app.include_router(experiments.router, prefix="/api", dependencies=guarded)
    app.include_router(settings_router.router, prefix="/api", dependencies=guarded)
    app.include_router(workflows.router, prefix="/api", dependencies=guarded)
    app.include_router(benchmark.router, prefix="/api", dependencies=guarded)
    app.include_router(integrations.router, prefix="/api", dependencies=guarded)
    return app


app = create_app()
