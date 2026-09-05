#!/usr/bin/env bash
set -euo pipefail

# Bash logging standard conforming to AGENTS.md
log() {
  printf '[ INFO ] %s\n' "$*"
}
ok() {
  printf '[  OK  ] %s\n' "$*"
}
warn() {
  printf '[ WARN ] %s\n' "$*"
}
err() {
  printf '[ ERR  ] %s\n' "$*"
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
FRONTEND_DIR="${ROOT_DIR}/frontend"

BACKEND_PORT=8000
FRONTEND_PORT=5173

# Detect primary laptop/host IP address
LAPTOP_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || ip route get 1.1.1.1 2>/dev/null | awk '{print $7}' || echo '127.0.0.1')"

BACKEND_PID=""
FRONTEND_PID=""
WORKER_PID=""

cleanup() {
  warn "Received stop signal. Terminating development servers..."

  # Disable trap so we don't loop on exit
  trap - INT TERM EXIT

  if [ -n "${BACKEND_PID}" ] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
    log "Stopping backend service (PID: ${BACKEND_PID})..."
    kill -TERM "${BACKEND_PID}" 2>/dev/null || true
  fi

  if [ -n "${FRONTEND_PID}" ] && kill -0 "${FRONTEND_PID}" 2>/dev/null; then
    log "Stopping frontend service (PID: ${FRONTEND_PID})..."
    kill -TERM "${FRONTEND_PID}" 2>/dev/null || true
  fi

  if [ -n "${WORKER_PID}" ] && kill -0 "${WORKER_PID}" 2>/dev/null; then
    log "Stopping recovery worker (PID: ${WORKER_PID})..."
    kill -TERM "${WORKER_PID}" 2>/dev/null || true
  fi

  # Wait for both processes to terminate
  if [ -n "${BACKEND_PID}" ]; then
    wait "${BACKEND_PID}" 2>/dev/null || true
  fi
  if [ -n "${FRONTEND_PID}" ]; then
    wait "${FRONTEND_PID}" 2>/dev/null || true
  fi
  if [ -n "${WORKER_PID}" ]; then
    wait "${WORKER_PID}" 2>/dev/null || true
  fi

  # Force kill any lingering processes on the ports if still listening
  fuser -k "${BACKEND_PORT}/tcp" 2>/dev/null || true
  fuser -k "${FRONTEND_PORT}/tcp" 2>/dev/null || true

  ok "All development services terminated cleanly."
  exit 0
}

trap cleanup INT TERM

log "Starting Revenue Recovery Development Environment..."
log "Detected Laptop Host IP: ${LAPTOP_IP}"
log "Backend directory: ${BACKEND_DIR}"
log "Frontend directory: ${FRONTEND_DIR}"

export BACKEND_HOST="${LAPTOP_IP}"
export BACKEND_PORT="${BACKEND_PORT}"
export NEXT_PUBLIC_API_BASE_URL="http://${LAPTOP_IP}:${BACKEND_PORT}/api"

# Start Backend listening on all interfaces
log "Launching backend service on ${LAPTOP_IP}:${BACKEND_PORT}..."
(
  cd "${BACKEND_DIR}"
  exec uv run fastapi dev src/app/main.py --host 0.0.0.0 --port "${BACKEND_PORT}"
) &
BACKEND_PID=$!

# Start Frontend Next.js listening on all interfaces
log "Launching frontend Next.js service on ${LAPTOP_IP}:${FRONTEND_PORT}..."
(
  cd "${FRONTEND_DIR}"
  exec pnpm dev --hostname 0.0.0.0 --port "${FRONTEND_PORT}"
) &
FRONTEND_PID=$!

ok "Backend API running on http://${LAPTOP_IP}:${BACKEND_PORT}"
ok "Frontend UI running on http://${LAPTOP_IP}:${FRONTEND_PORT}"
ok "Base URL configured: http://${LAPTOP_IP}:${FRONTEND_PORT} -> http://${LAPTOP_IP}:${BACKEND_PORT}/api"

# Drains the durable queue. Without it, jobs stay QUEUED forever and the queue
# count grows even with the fleet stopped.
log "Launching recovery worker daemon..."
(
  cd "${BACKEND_DIR}"
  exec uv run python -m app.worker.main
) &
WORKER_PID=$!
ok "Recovery worker running (PID: ${WORKER_PID})"

log "Press Ctrl+C to stop both services."

# Wait for both servers
wait "${BACKEND_PID}" "${FRONTEND_PID}" "${WORKER_PID}"
