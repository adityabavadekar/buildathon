/**
 * Tunnel registry backed by a JSON file on disk.
 * Each tunnel has: { id, url, label, addedAt }
 * File is written synchronously on every mutation so a crash loses at most one write.
 */

import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { randomUUID } from 'node:crypto'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dir = dirname(fileURLToPath(import.meta.url))
const DB_PATH = resolve(__dir, '..', 'tunnels.json')

function load() {
  if (!existsSync(DB_PATH)) return []
  try {
    return JSON.parse(readFileSync(DB_PATH, 'utf8'))
  } catch {
    return []
  }
}

function save(tunnels) {
  writeFileSync(DB_PATH, JSON.stringify(tunnels, null, 2), 'utf8')
}

let tunnels = load()

export function listTunnels() {
  return [...tunnels]
}

export function addTunnel(url, label = '') {
  // Deduplicate by URL
  const existing = tunnels.find((t) => t.url === url)
  if (existing) return existing

  const tunnel = { id: randomUUID(), url: url.replace(/\/$/, ''), label, addedAt: new Date().toISOString() }
  tunnels.push(tunnel)
  save(tunnels)
  return tunnel
}

export function removeTunnel(id) {
  const before = tunnels.length
  tunnels = tunnels.filter((t) => t.id !== id)
  if (tunnels.length !== before) {
    save(tunnels)
    return true
  }
  return false
}
