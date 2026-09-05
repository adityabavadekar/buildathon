#!/usr/bin/env bash
set -euo pipefail

# Reports which Razorpay calls work against test mode, so a "simulated" tool can
# be traced to a quota, an unenabled feature, or a missing credential.

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

RZP_BIN="${RZP_BIN:-razorpay}"
if ! command -v "${RZP_BIN}" >/dev/null 2>&1; then
  err "Razorpay CLI not found on PATH. Install it with:"
  err "  curl -fsSL https://razorpay.com/cli/latest/install.sh | bash"
  err "then configure it with your test keys:"
  err "  ${RZP_BIN} configure"
  exit 1
fi

log "Checking Razorpay CLI availability..."
"${RZP_BIN}" --version

# Load credentials directly from backend/.env exactly as the app does, so this
# reports the same result the application would see.
ENV_FILE="${BACKEND_DIR}/.env"
if [ ! -f "${ENV_FILE}" ]; then
  err "No ${ENV_FILE} found. Create it from .env.example to run this check."
  exit 1
fi

KEY_ID="$(grep '^RAZORPAY_KEY_ID=' "${ENV_FILE}" | cut -d= -f2- | tr -d '"' || true)"
KEY_SECRET="$(grep '^RAZORPAY_KEY_SECRET=' "${ENV_FILE}" | cut -d= -f2- | tr -d '"' || true)"

if [ -z "${KEY_ID}" ] || [ -z "${KEY_SECRET}" ]; then
  err "RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not set in ${ENV_FILE}. Simulation is expected."
  exit 1
fi

log "Credentials present (KEY_ID prefix: ${KEY_ID:0:12}...)."

# Ensure CLI is configured with the same keys.
"${RZP_BIN}" configure --key-id "${KEY_ID}" --key-secret "${KEY_SECRET}" >/dev/null 2>&1

EXTRA="${1:-}"

run_check() {
  local label="$1"
  shift
  local out
  if out="$("${RZP_BIN}" "$@" 2>&1)"; then
    ok "${label}: live API call succeeded (real Razorpay test-mode data)."
    printf '%s\n' "${out}" | grep -E '"id"|"short_url"|"status"' | head -3 || true
  else
    local code
    code="$(printf '%s\n' "${out}" | grep -oE 'status [0-9]+' | head -1 || echo 'unknown')"
    warn "${label}: ${code} - ${out##*: }"
  fi
}

log "Probing real Razorpay test-mode API..."

run_check "Orders (create)" orders create --amount 50000 --currency INR --receipt "livecheck-$(date +%s)"
run_check "Customers (list)" customers list
run_check "Refunds (list)" refunds list
run_check "Payment Links (create)" payment-links create --amount 100 --currency INR

if [ -n "${EXTRA}" ]; then
  log "Extra probes requested..."
  run_check "Subscriptions (create)" subscriptions create --plan-id "${EXTRA}" --total-count 3
  run_check "Invoices (create)" invoices create --amount 100 --currency INR
fi

log "Done. Read the lines above to see which APIs are live versus quota/feature-blocked."
