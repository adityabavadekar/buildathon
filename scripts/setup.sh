#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib-log.sh
source "${ROOT_DIR}/scripts/lib-log.sh"

log "Syncing backend dependencies"
cd "${ROOT_DIR}/backend"
uv sync --all-groups
ok "Backend .venv ready"

DB_PORT="${DB_PORT:-5432}"

if ! docker compose version >/dev/null 2>&1; then
  err "docker compose is required to start the database"
  exit 1
fi

DOCKER="docker"
if ! docker info >/dev/null 2>&1; then
  if sudo -n docker info >/dev/null 2>&1; then
    DOCKER="sudo docker"
    warn "Using sudo for docker. Add yourself to the docker group to avoid this."
  else
    err "Cannot reach the docker daemon. Start it, or add yourself to the docker group."
    exit 1
  fi
fi

log "Starting the database"
cd "${ROOT_DIR}"
${DOCKER} compose -f docker-compose.dev.yml up -d --wait
ok "Database ready on port ${DB_PORT}"

log "Installing frontend dependencies"
cd "${ROOT_DIR}/frontend"
pnpm install
ok "Frontend dependencies installed"
