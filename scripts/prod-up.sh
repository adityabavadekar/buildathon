#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib-log.sh
source "${ROOT_DIR}/scripts/lib-log.sh"

cd "${ROOT_DIR}"

if [ ! -f .env ]; then
  err "No .env found. Copy .env.prod.example to .env and fill it in."
  exit 1
fi

# Refuse the placeholder values rather than starting a dashboard anyone can open.
for placeholder in replace_with_a_strong_password replace_with_the_operator_password replace_with_openssl_rand_hex_32; do
  if grep -q "${placeholder}" .env; then
    err "Placeholder '${placeholder}' is still in .env. Replace it before deploying."
    exit 1
  fi
done

if ! grep -qE '^APP_OPERATOR_PASSWORD=.+' .env; then
  err "APP_OPERATOR_PASSWORD is empty. That disables the login gate entirely."
  exit 1
fi

log "Building images..."
docker compose build

log "Starting services..."
docker compose up -d

log "Waiting for backend to report healthy..."
deadline=$(( SECONDS + 180 ))
while [ "${SECONDS}" -lt "${deadline}" ]; do
  state="$(docker compose ps --format '{{.Service}} {{.Health}}' 2>/dev/null | awk '$1=="backend"{print $2}')"
  if [ "${state}" = "healthy" ]; then
    ok "Backend healthy."
    break
  fi
  if [ "${state}" = "unhealthy" ]; then
    err "Backend became unhealthy. Recent logs:"
    docker compose logs --tail 40 backend
    exit 1
  fi
  sleep 3
done

if [ "${SECONDS}" -ge "${deadline}" ]; then
  err "Backend did not become healthy within 180s. Recent logs:"
  docker compose logs --tail 40 backend
  exit 1
fi

port="$(grep -E '^FRONTEND_PUBLISH_PORT=' .env | cut -d= -f2)"
port="${port:-3000}"

docker compose ps
ok "Dashboard: http://localhost:${port}"
ok "Follow logs with: docker compose logs -f"
