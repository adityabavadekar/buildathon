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

cleanup() {
  warn "Shutting down background services..."
  trap - INT TERM EXIT
  kill 0 2>/dev/null || true
}

trap cleanup INT TERM EXIT

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
log "Press Ctrl+C to stop both services."

wait "${BACKEND_PID}" "${FRONTEND_PID}"
