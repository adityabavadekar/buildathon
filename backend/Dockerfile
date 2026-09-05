FROM python:3.13-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# --frozen fails on a stale uv.lock rather than resolving something untested.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.13-slim-bookworm AS runtime

# libpq5 is psycopg's runtime dependency; curl and procps back the healthchecks.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl procps \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 fortx

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production \
    APP_LOG_JSON=true

WORKDIR /app

COPY --from=builder --chown=10001:10001 /app/.venv ./.venv
COPY --from=builder --chown=10001:10001 /app/src ./src
COPY --from=builder --chown=10001:10001 /app/alembic.ini ./
# alembic.ini's script_location resolves to /app/alembic; startup migrations fail without it.
COPY --from=builder --chown=10001:10001 /app/alembic ./alembic

USER 10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# One worker: the login throttle and fleet simulator hold process-local state.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
