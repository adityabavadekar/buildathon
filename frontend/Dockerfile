FROM node:22-bookworm-slim AS builder

RUN corepack enable && corepack prepare pnpm@11.15.1 --activate

WORKDIR /app

ENV NEXT_TELEMETRY_DISABLED=1

# Copied before the sources so an edit to a component does not reinstall.
# --frozen-lockfile fails on a stale lockfile rather than resolving new versions.
COPY package.json pnpm-lock.yaml ./
RUN --mount=type=cache,target=/pnpm-store \
    pnpm config set store-dir /pnpm-store && pnpm install --frozen-lockfile

# Baked into routes-manifest.json by next.config.ts, so it must be a build arg.
ARG BACKEND_HOST=backend
ARG BACKEND_PORT=8000
ENV BACKEND_HOST=${BACKEND_HOST} \
    BACKEND_PORT=${BACKEND_PORT}

COPY . .
RUN pnpm build


FROM node:22-bookworm-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10002 fortx

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

WORKDIR /app

# The standalone server does not serve static assets from .next/ itself; they
# must sit at exactly these paths.
COPY --from=builder --chown=10002:10002 /app/.next/standalone ./
COPY --from=builder --chown=10002:10002 /app/.next/static ./.next/static
COPY --from=builder --chown=10002:10002 /app/public ./public

USER 10002

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:3000/ || exit 1

CMD ["node", "server.js"]
