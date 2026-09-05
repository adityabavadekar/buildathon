#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib-log.sh
source "${ROOT_DIR}/scripts/lib-log.sh"

log "Syncing backend dependencies"
cd "${ROOT_DIR}/backend"
uv sync --all-groups
ok "Backend .venv ready"

log "Installing frontend dependencies"
cd "${ROOT_DIR}/frontend"
pnpm install
ok "Frontend dependencies installed"
