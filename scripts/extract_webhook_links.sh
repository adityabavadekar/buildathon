#!/usr/bin/env bash
# Pulls every webhook/event-related documentation link out of Razorpay's
# llms.txt and writes them to docs/razorpay_webhook_links.txt.
#
# Usage: scripts/extract_webhook_links.sh

set -euo pipefail

log() {
  printf '[ INFO ] %s\n' "$*"
}
ok() {
  printf '[  OK  ] %s\n' "$*"
}
err() {
  printf '[ ERR  ] %s\n' "$*"
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_URL="https://razorpay.com/docs/llms.txt"
RAW_FILE="$(mktemp)"
OUTPUT_FILE="$REPO_ROOT/docs/razorpay_webhook_links.txt"

trap 'rm -f "$RAW_FILE"' EXIT

log "Downloading $SOURCE_URL"
if ! curl -sf "$SOURCE_URL" -o "$RAW_FILE"; then
  err "Failed to download $SOURCE_URL"
  exit 1
fi

log "Extracting webhook/event-related links"
mkdir -p "$(dirname "$OUTPUT_FILE")"

# Matches markdown link lines [Title](url) whose title or url text mentions
# webhook or event, case-insensitive. Deduplicated, sorted for stable diffs.
grep -iE '^\-\s*\[.*\]\(https://[^)]+\)' "$RAW_FILE" \
  | grep -iE 'webhook|\bevent' \
  | sed -E 's/^\-\s*\[(.*)\]\(([^)]+)\):?\s*(.*)$/\2\t\1\t\3/' \
  | sort -u -t $'\t' -k1,1 \
  > "$OUTPUT_FILE"

count=$(wc -l < "$OUTPUT_FILE" | tr -d ' ')
ok "Wrote $count links to $OUTPUT_FILE"
