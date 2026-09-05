#!/usr/bin/env bash
# setup.sh - Full server setup for webhook-relay on webhook.adixb.me
# Installs Node.js, nginx, certbot, creates systemd service.
# Run as root on a fresh Ubuntu/Debian VPS.

set -euo pipefail

log()  { printf '[ INFO ] %s\n' "$*"; }
ok()   { printf '[  OK  ] %s\n' "$*"; }
warn() { printf '[ WARN ] %s\n' "$*"; }
err()  { printf '[ ERR  ] %s\n' "$*"; }

# Config
DOMAIN="${DOMAIN:-webhook.adixb.me}"
PORT="${PORT:-3099}"
APP_DIR="${APP_DIR:-/opt/webhook-relay}"
SERVICE_USER="${SERVICE_USER:-webhookd}"
RELAY_SECRET="${RELAY_SECRET:-}"
EMAIL="${EMAIL:-}"   # for certbot Let's Encrypt registration
# -

# Require root
if [ "$(id -u)" -ne 0 ]; then
  err "Run this script as root: sudo bash setup.sh"
  exit 1
fi

# Detect public IP
PUBLIC_IP="$(curl -fsSL --max-time 5 https://api.ipify.org 2>/dev/null || \
             curl -fsSL --max-time 5 https://checkip.amazonaws.com 2>/dev/null || \
             hostname -I | awk '{print $1}')"

log "Detected public IP: ${PUBLIC_IP}"
log ""
log " IMPORTANT: Before running this script, set your DNS A record:"
log ""
log "   Domain  : ${DOMAIN}"
log "   Type    : A"
log "   Value   : ${PUBLIC_IP}"
log "   TTL     : 60 (or lowest available)"
log ""
log " Verify with:  dig +short ${DOMAIN}"
log " (DNS may take 1-5 minutes to propagate)"
log ""

if [ -z "$EMAIL" ]; then
  printf '[ INFO ] Enter your email for Let'"'"'s Encrypt SSL certificate: '
  read -r EMAIL
fi

if [ -z "$RELAY_SECRET" ]; then
  RELAY_SECRET="$(openssl rand -hex 24)"
  warn "No RELAY_SECRET set - generated a random one (save this!):"
  warn "  RELAY_SECRET=${RELAY_SECRET}"
fi

log "Waiting 5 seconds - press Ctrl+C to abort if DNS is not set yet..."
sleep 5

# System dependencies
log "Updating apt packages..."
apt-get update -qq

log "Installing nginx, certbot, curl, git..."
apt-get install -y -qq nginx certbot python3-certbot-nginx curl git

# Install Node.js 22 LTS via NodeSource
if ! command -v node &>/dev/null || ! node --version | grep -qE '^v2[0-9]'; then
  log "Installing Node.js 22 LTS..."
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash - -qq
  apt-get install -y -qq nodejs
fi

ok "Node.js $(node --version) ready"

# Create service user
if ! id "$SERVICE_USER" &>/dev/null; then
  log "Creating system user '${SERVICE_USER}'..."
  useradd --system --shell /usr/sbin/nologin --create-home "$SERVICE_USER"
fi

# Deploy app
log "Deploying app to ${APP_DIR}..."
mkdir -p "$APP_DIR"

# Copy files from the repo directory (works when run from within the repo)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp -r "${SCRIPT_DIR}/src" "$APP_DIR/"
cp "${SCRIPT_DIR}/package.json" "$APP_DIR/"
cp "${SCRIPT_DIR}/package-lock.json" "$APP_DIR/" 2>/dev/null || true

chown -R "${SERVICE_USER}:${SERVICE_USER}" "$APP_DIR"

log "Installing npm dependencies (production)..."
sudo -u "$SERVICE_USER" npm install --production --prefix "$APP_DIR" 2>&1 | grep -v "^npm warn"

ok "App deployed to ${APP_DIR}"

# Write .env
cat > "${APP_DIR}/.env" <<ENV
PORT=${PORT}
RELAY_SECRET=${RELAY_SECRET}
ENV

chown "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}/.env"
chmod 600 "${APP_DIR}/.env"

ok ".env written"

# systemd service
cat > /etc/systemd/system/webhook-relay.service <<UNIT
[Unit]
Description=Razorpay Webhook Fanout Relay
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=/usr/bin/node src/index.js
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=webhook-relay

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable webhook-relay
systemctl restart webhook-relay

ok "systemd service 'webhook-relay' started"

# Give it a moment to come up
sleep 2
if systemctl is-active --quiet webhook-relay; then
  ok "webhook-relay is running on port ${PORT}"
else
  err "webhook-relay failed to start - check: journalctl -u webhook-relay -n 30"
  exit 1
fi

# nginx config
log "Writing nginx config for ${DOMAIN}..."

# Use a quoted heredoc delimiter ('NGINX') to prevent shell expanding $host etc.
# nginx variables must reach the file as literal $host, $remote_addr, etc.
cat > "/etc/nginx/sites-available/${DOMAIN}" <<'__NGINX_TEMPLATE__'
server {
    listen 80;
    listen [::]:80;
    server_name PLACEHOLDER_DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:PLACEHOLDER_PORT;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
        proxy_connect_timeout 5s;
        client_max_body_size 2m;
    }
}
__NGINX_TEMPLATE__

# Substitute placeholders now that shell expansion is safe
sed -i "s/PLACEHOLDER_DOMAIN/${DOMAIN}/g" "/etc/nginx/sites-available/${DOMAIN}"
sed -i "s/PLACEHOLDER_PORT/${PORT}/g"     "/etc/nginx/sites-available/${DOMAIN}"

ln -sf "/etc/nginx/sites-available/${DOMAIN}" "/etc/nginx/sites-enabled/${DOMAIN}"
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

nginx -t
systemctl reload nginx

ok "nginx configured for ${DOMAIN}"

# certbot SSL
log "Requesting Let's Encrypt SSL certificate for ${DOMAIN}..."

certbot --nginx \
  --non-interactive \
  --agree-tos \
  --email "$EMAIL" \
  --domains "$DOMAIN" \
  --redirect

ok "SSL certificate issued and nginx updated"
systemctl reload nginx

# Final summary
log ""
ok " Setup complete!"
log ""
log " Server public IP : ${PUBLIC_IP}"
log " Domain           : https://${DOMAIN}"
log " Service          : systemctl status webhook-relay"
log " Logs             : journalctl -fu webhook-relay"
log ""
log " RELAY_SECRET     : ${RELAY_SECRET}"
log "   (store this - needed for all management API calls)"
log ""
log " Razorpay Webhook URL (set this in dashboard):"
log "   https://${DOMAIN}/relay/api/webhooks/razorpay"
log ""
log " Add a dev tunnel:"
log "   curl -X POST https://${DOMAIN}/tunnels \\"
log "     -H 'Content-Type: application/json' \\"
log "     -H 'x-relay-secret: ${RELAY_SECRET}' \\"
log "     -d '{\"url\":\"https://YOUR-NGROK-ID.ngrok.io\",\"label\":\"laptop\"}'"
log ""
log " List tunnels:"
log "   curl https://${DOMAIN}/tunnels \\"
log "     -H 'x-relay-secret: ${RELAY_SECRET}'"
log ""
log " Health check:"
log "   curl https://${DOMAIN}/health"
