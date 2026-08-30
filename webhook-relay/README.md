# webhook-relay

Lightweight Express.js fanout relay. Set `https://webhook.adixb.me/relay/api/webhooks/razorpay` as your Razorpay webhook URL. It will forward every event to all registered dev tunnel URLs in parallel.

## Setup

```bash
npm install
cp .env.example .env
# edit .env with your PORT and RELAY_SECRET
npm start
```

## Managing Tunnels

```bash
# List registered tunnels
curl https://webhook.adixb.me/tunnels -H 'x-relay-secret: <secret>'

# Add a new ngrok/CF tunnel
curl -X POST https://webhook.adixb.me/tunnels \
  -H 'Content-Type: application/json' \
  -H 'x-relay-secret: <secret>' \
  -d '{"url":"https://abc123.ngrok.io","label":"laptop-dev"}'

# Remove a tunnel
curl -X DELETE https://webhook.adixb.me/tunnels/<id> \
  -H 'x-relay-secret: <secret>'
```

## Set Razorpay Webhook URL

```
https://webhook.adixb.me/relay/api/webhooks/razorpay
```

All `x-razorpay-signature` headers are forwarded transparently, so HMAC verification works on your dev backend.

## Deploy (simple)

```bash
# On your VPS/server with nginx proxying webhook.adixb.me -> 127.0.0.1:3099
npm install --production
npm start
# Or use PM2:
pm2 start npm --name webhook-relay -- start
```

## Nginx Config (webhook.adixb.me)

```nginx
server {
    listen 80;
    server_name webhook.adixb.me;

    location / {
        proxy_pass http://127.0.0.1:3099;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

Then add SSL with `certbot --nginx -d webhook.adixb.me`.
