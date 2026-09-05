#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib-log.sh
source "${ROOT_DIR}/scripts/lib-log.sh"

cd "${ROOT_DIR}"

PURGE_VOLUMES=0
if [ "${1:-}" = "--purge-volumes" ]; then
  PURGE_VOLUMES=1
fi

if [ "${PURGE_VOLUMES}" -eq 1 ]; then
  warn "This deletes the postgres volume: every case, audit row, and credential."
  printf 'Type DELETE to confirm: '
  read -r reply
  if [ "${reply}" != "DELETE" ]; then
    log "Aborted. Nothing was removed."
    exit 0
  fi
  docker compose down --volumes
  ok "Services stopped and volumes deleted."
  exit 0
fi

docker compose down
ok "Services stopped. Data volume retained."
