#!/usr/bin/env bash
# tunnel.sh - Register or remove a dev tunnel from the webhook relay at webhook.adixb.me
#
# Usage:
#   bash tunnel.sh add   [url] [label]   - register a tunnel
#   bash tunnel.sh list                  - list active tunnels
#   bash tunnel.sh remove [id]           - remove a tunnel by id
#   bash tunnel.sh ngrok                 - auto-detect running ngrok and register it
#   bash tunnel.sh cf                    - auto-detect running cloudflared and register it
#
# Config (set in env or edit below):
#   RELAY_URL    - base URL of the relay (default: https://webhook.adixb.me)
#   RELAY_SECRET - management auth secret

set -euo pipefail

log()  { printf '[ INFO ] %s\n' "$*"; }
ok()   { printf '[  OK  ] %s\n' "$*"; }
warn() { printf '[ WARN ] %s\n' "$*"; }
err()  { printf '[ ERR  ] %s\n' "$*"; exit 1; }

RELAY_URL="${RELAY_URL:-https://webhook.adixb.me}"
RELAY_SECRET="${RELAY_SECRET:-}"

# Load .env from same dir as this script if present
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/.env" ]; then
  # shellcheck disable=SC1091
  set -a; . "${SCRIPT_DIR}/.env"; set +a
fi

cmd_help() {
  cat <<HELP
tunnel.sh - Manage dev tunnels on ${RELAY_URL}

Usage:
  bash tunnel.sh add [url] [label]   Register a tunnel URL
  bash tunnel.sh list                List all active tunnels
  bash tunnel.sh remove [id]         Remove a tunnel by ID
  bash tunnel.sh ngrok               Auto-detect + register running ngrok
  bash tunnel.sh cf                  Auto-detect + register running cloudflared

Config (env vars or .env file):
  RELAY_URL     Base URL of relay  (default: https://webhook.adixb.me)
  RELAY_SECRET  Management secret  (required)

Examples:
  RELAY_SECRET=abc123 bash tunnel.sh ngrok
  RELAY_SECRET=abc123 bash tunnel.sh add https://xyz.ngrok.io "office-laptop"
  RELAY_SECRET=abc123 bash tunnel.sh list
  RELAY_SECRET=abc123 bash tunnel.sh remove d3f1a2b3-...
HELP
}

CMD="${1:-help}"

# Help doesn't need auth
if [ "$CMD" = "help" ]; then cmd_help; exit 0; fi

if [ -z "$RELAY_SECRET" ]; then
  err "RELAY_SECRET is not set. Export it or add it to webhook-relay/.env"
fi

# ---- Helpers ---------------------------------------------------------------

relay_request() {
  local method="$1" path="$2"
  shift 2
  curl -fsSL \
    --max-time 10 \
    -X "$method" \
    -H "x-relay-secret: ${RELAY_SECRET}" \
    -H "Content-Type: application/json" \
    "$@" \
    "${RELAY_URL}${path}"
}

pretty() {
  # pretty-print JSON if python3 available, else raw
  if command -v python3 &>/dev/null; then
    python3 -m json.tool
  else
    cat
  fi
}

# ---- Commands --------------------------------------------------------------

cmd_list() {
  log "Active tunnels on ${RELAY_URL}:"
  relay_request GET /tunnels | pretty
}

cmd_add() {
  local url="${1:-}"
  local label="${2:-$(hostname)}"

  if [ -z "$url" ]; then
    printf '[ INFO ] Enter tunnel URL (e.g. https://abc123.ngrok.io): '
    read -r url
  fi

  log "Registering tunnel: ${url} (label: ${label})"
  relay_request POST /tunnels --data "{\"url\":\"${url}\",\"label\":\"${label}\"}" | pretty
  ok "Registered. Razorpay events will now fan out to ${url}"
}

cmd_remove() {
  local id="${1:-}"

  if [ -z "$id" ]; then
    log "Current tunnels:"
    relay_request GET /tunnels | pretty
    printf '[ INFO ] Enter tunnel ID to remove: '
    read -r id
  fi

  relay_request DELETE "/tunnels/${id}" | pretty
  ok "Tunnel ${id} removed."
}

cmd_ngrok() {
  log "Detecting running ngrok tunnel..."

  # ngrok exposes a local API on port 4040
  if ! curl -fsSL --max-time 3 http://127.0.0.1:4040/api/tunnels &>/dev/null; then
    err "ngrok does not appear to be running (no API at 127.0.0.1:4040). Start ngrok first."
  fi

  NGROK_URL="$(curl -fsSL http://127.0.0.1:4040/api/tunnels | \
    python3 -c "import sys,json; t=[x for x in json.load(sys.stdin)['tunnels'] if x['proto']=='https']; print(t[0]['public_url'])" 2>/dev/null || true)"

  if [ -z "$NGROK_URL" ]; then
    err "Could not detect an HTTPS ngrok tunnel. Is ngrok running with 'ngrok http <port>'?"
  fi

  ok "Detected ngrok URL: ${NGROK_URL}"
  cmd_add "$NGROK_URL" "ngrok-$(hostname)"
}

cmd_cf() {
  log "Detecting running cloudflared tunnel..."

  # cloudflared writes its URL to a local metrics server on 20241
  CF_URL="$(curl -fsSL --max-time 3 http://127.0.0.1:20241/metrics 2>/dev/null | \
    grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | head -1 || true)"

  if [ -z "$CF_URL" ]; then
    # Try reading from cloudflared log output saved to /tmp
    CF_URL="$(grep -rh 'trycloudflare.com' /tmp/cloudflared*.log 2>/dev/null | \
      grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1 || true)"
  fi

  if [ -z "$CF_URL" ]; then
    err "Could not detect a cloudflared tunnel URL. Run: cloudflared tunnel --url http://localhost:8000 2>/tmp/cloudflared.log &"
  fi

  ok "Detected cloudflared URL: ${CF_URL}"
  cmd_add "$CF_URL" "cf-$(hostname)"
}


# ---- Dispatch --------------------------------------------------------------

case "$CMD" in
  add)    cmd_add    "${2:-}" "${3:-}" ;;
  list)   cmd_list ;;
  remove) cmd_remove "${2:-}" ;;
  ngrok)  cmd_ngrok ;;
  cf)     cmd_cf ;;
  help|*) cmd_help ;;
esac
