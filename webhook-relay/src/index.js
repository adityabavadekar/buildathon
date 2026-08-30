/**
 * webhook-relay: Razorpay webhook fanout relay.
 *
 * Receives any inbound POST from Razorpay at /relay/*, then fans out to all
 * registered tunnel URLs in parallel. Forwards original headers including
 * x-razorpay-signature so HMAC verification keeps working on dev servers.
 *
 * Routes:
 *   GET    /           - info & current tunnel list
 *   GET    /health     - liveness probe
 *   GET    /tunnels    - list tunnels
 *   POST   /tunnels    - add tunnel { url, label? }
 *   DELETE /tunnels/:id - remove tunnel
 *   POST   /relay/*    - receive webhook and fan out
 */

import express from 'express'
import { fetch } from 'undici'
import { addTunnel, listTunnels, removeTunnel } from './store.js'

const log  = (...a) => process.stdout.write(`[ INFO ] ${a.join(' ')}\n`)
const warn = (...a) => process.stdout.write(`[ WARN ] ${a.join(' ')}\n`)
const err  = (...a) => process.stdout.write(`[ ERR  ] ${a.join(' ')}\n`)

const PORT = parseInt(process.env.PORT ?? '3099', 10)
const RELAY_SECRET = process.env.RELAY_SECRET ?? ''

const app = express()
app.use(express.json({ limit: '1mb' }))

function requireSecret(req, res, next) {
  if (!RELAY_SECRET) return next()
  const token = req.headers['x-relay-secret'] ?? req.query.secret
  if (token !== RELAY_SECRET) {
    res.status(403).json({ error: 'Forbidden: invalid relay secret' })
    return
  }
  next()
}

// Tunnel management

app.get('/tunnels', requireSecret, (_req, res) => {
  res.json({ tunnels: listTunnels() })
})

app.post('/tunnels', requireSecret, (req, res) => {
  const { url, label } = req.body ?? {}
  if (!url || typeof url !== 'string') {
    res.status(400).json({ error: '`url` is required' })
    return
  }
  try { new URL(url) } catch {
    res.status(400).json({ error: '`url` must be a valid absolute URL' })
    return
  }
  const tunnel = addTunnel(url, typeof label === 'string' ? label : '')
  log(`tunnel.added id=${tunnel.id} url=${tunnel.url}`)
  res.status(201).json({ tunnel })
})

app.delete('/tunnels/:id', requireSecret, (req, res) => {
  const removed = removeTunnel(req.params.id)
  if (!removed) { res.status(404).json({ error: 'Tunnel not found' }); return }
  log(`tunnel.removed id=${req.params.id}`)
  res.json({ status: 'removed', id: req.params.id })
})

// Fanout relay

const HOP_BY_HOP = new Set([
  'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
  'te', 'trailers', 'transfer-encoding', 'upgrade', 'host',
])

async function fanout(suffix, body, headers) {
  const tunnels = listTunnels()
  if (tunnels.length === 0) { warn('fanout: no tunnels registered, dropping event'); return [] }

  const fwdHeaders = {}
  for (const [k, v] of Object.entries(headers)) {
    if (!HOP_BY_HOP.has(k.toLowerCase())) fwdHeaders[k] = v
  }
  fwdHeaders['content-type'] = 'application/json'

  const bodyStr = JSON.stringify(body)

  const results = await Promise.allSettled(
    tunnels.map(async (tunnel) => {
      const target = `${tunnel.url}${suffix}`
      const t0 = Date.now()
      const resp = await fetch(target, {
        method: 'POST',
        headers: fwdHeaders,
        body: bodyStr,
        signal: AbortSignal.timeout(10_000),
      })
      return { id: tunnel.id, url: target, status: resp.status, ms: Date.now() - t0 }
    })
  )

  return results.map((r, i) => {
    const t = tunnels[i]
    if (r.status === 'fulfilled') {
      log(`fanout.ok url=${r.value.url} status=${r.value.status} ms=${r.value.ms}`)
      return r.value
    }
    warn(`fanout.error url=${t.url}${suffix} error=${String(r.reason)}`)
    return { id: t.id, url: `${t.url}${suffix}`, error: String(r.reason) }
  })
}

app.post(['/relay', '/relay/*'], async (req, res) => {
  const suffix = req.path.replace(/^\/relay/, '') || '/'
  log(`relay.received suffix=${suffix} tunnels=${listTunnels().length}`)
  try {
    const results = await fanout(suffix, req.body, req.headers)
    res.json({ relayed_to: results.length, results })
  } catch (e) {
    err(`relay.error ${String(e)}`)
    res.status(500).json({ error: 'Relay error' })
  }
})

app.get('/health', (_req, res) => {
  res.json({ status: 'ok', tunnels: listTunnels().length, relay_path: '/relay/*' })
})

app.get('/', (_req, res) => {
  res.json({
    name: 'webhook-relay',
    relay_endpoint: 'POST /relay/api/webhooks/razorpay',
    manage: { list: 'GET /tunnels', add: 'POST /tunnels', remove: 'DELETE /tunnels/:id' },
    active_tunnels: listTunnels(),
  })
})

app.listen(PORT, () => {
  log(`webhook-relay listening on :${PORT}`)
  log(`Set Razorpay webhook URL to: https://webhook.adixb.me/relay/api/webhooks/razorpay`)
  log(`Active tunnels: ${listTunnels().length}`)
})
