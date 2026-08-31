'use client'

import React, { useEffect, useState } from 'react'
import type { RecoveryCase } from '@/lib/api'
import type { NavSection } from '@/lib/navigation'
import { formatCustomerName } from '@/lib/format'
import {
  MAIN_NAV_ITEMS,
  NAV_SECTION_LABELS,
  OPERATIONS_NAV_ITEMS,
  SETTINGS_NAV_ITEMS,
} from '@/lib/navigation'

interface CommandPaletteProps {
  open: boolean
  onClose: () => void
  cases: RecoveryCase[]
  onSelectCase: (c: RecoveryCase) => void
  onNavigate: (section: NavSection) => void
  onSeed: () => void
  onReset: () => void
}

const NAV_DESCRIPTIONS: Partial<Record<NavSection, string>> = {
  overview: 'Executive KPI dashboard and opportunity matrix',
  analytics: 'Counterfactual proof and NRV accounting',
  transactions: 'Active recovery queue and operational table',
  audit: 'System-wide immutable chronology',
  'settings-policies': 'Guardrails, touch limits, and discount caps',
  'settings-general': 'LLM provider hierarchy and experiment evaluation',
  'settings-integrations': 'Razorpay gateway, webhooks, and subsystem health',
  pipeline: 'Ingestion queue, fleet control, and worker telemetry',
  workflows: 'Durable recovery workflows and decision history',
  recovery: 'Active dunning queue and operational table',
  agent: 'Live decision stream and model token metrics',
  policies: 'Guardrails, touch limits, and discount caps',
  status: 'Telemetry, gateway health, and active queues',
  settings: 'Razorpay webhook URLs and integration config',
}

export function CommandPalette({
  open,
  onClose,
  cases,
  onSelectCase,
  onNavigate,
  onSeed,
  onReset,
}: CommandPaletteProps) {
  const [query, setQuery] = useState<string>('')

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        if (open) onClose()
      }
      if (e.key === 'Escape' && open) {
        onClose()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [open, onClose])

  if (!open) return null

  const navOptions = [
    ...MAIN_NAV_ITEMS.map((item) => item.id),
    ...SETTINGS_NAV_ITEMS.map((item) => item.id),
    ...OPERATIONS_NAV_ITEMS.map((item) => item.id),
    'policies' as const,
    'settings' as const,
  ].map((id) => ({
    id,
    label: `Go to ${NAV_SECTION_LABELS[id]}`,
    desc: NAV_DESCRIPTIONS[id] ?? '',
  }))

  const filteredNav = navOptions.filter(
    (n) =>
      n.label.toLowerCase().includes(query.toLowerCase()) ||
      n.desc.toLowerCase().includes(query.toLowerCase()),
  )

  const filteredCases = cases
    .filter(
      (c) =>
        c.case_id.toLowerCase().includes(query.toLowerCase()) ||
        c.failure_event.payment_id
          .toLowerCase()
          .includes(query.toLowerCase()) ||
        c.failure_event.customer_id.toLowerCase().includes(query.toLowerCase()),
    )
    .slice(0, 5)

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4 pt-20 backdrop-blur-xs">
      <div className="animate-in fade-in zoom-in-95 w-full max-w-xl overflow-hidden rounded-panel border border-border bg-surface shadow-2xl duration-150">
        <div className="flex items-center border-b border-border bg-surface-sunken/40 px-4 py-3">
          <span className="mr-2 font-mono text-xs font-bold text-ink-subtle">
            [⌘K]
          </span>
          <input
            type="text"
            autoFocus
            placeholder="Type a command, case ID, customer, or navigation..."
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
            }}
            className="flex-1 bg-transparent font-mono text-xs text-ink placeholder:text-ink-subtle focus:outline-none"
          />
          <button
            type="button"
            onClick={onClose}
            className="cursor-pointer font-mono text-[10px] text-ink-muted hover:text-ink"
          >
            [Esc]
          </button>
        </div>

        <div className="max-h-96 space-y-3 overflow-y-auto p-2 font-mono text-xs">
          <div className="space-y-1">
            <div className="px-2 py-1 text-[10px] tracking-wider text-ink-subtle uppercase">
              Quick Actions
            </div>
            <button
              type="button"
              onClick={() => {
                onSeed()
                onClose()
              }}
              className="flex w-full cursor-pointer items-center justify-between rounded-control px-3 py-2 text-left text-ink transition-colors hover:bg-surface-sunken"
            >
              <span>Seed 50 Synthetic Recovery Cases</span>
              <span className="text-[10px] font-semibold text-accent">
                Simulation
              </span>
            </button>
            <button
              type="button"
              onClick={() => {
                onReset()
                onClose()
              }}
              className="flex w-full cursor-pointer items-center justify-between rounded-control px-3 py-2 text-left text-ink transition-colors hover:bg-surface-sunken"
            >
              <span>Reset & Purge All Simulation Data</span>
              <span className="text-[10px] font-semibold text-failed">
                Purge
              </span>
            </button>
          </div>

          {filteredNav.length > 0 && (
            <div className="space-y-1 border-t border-border/50 pt-1">
              <div className="px-2 py-1 text-[10px] tracking-wider text-ink-subtle uppercase">
                Navigation
              </div>
              {filteredNav.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    onNavigate(item.id)
                    onClose()
                  }}
                  className="flex w-full cursor-pointer items-center justify-between rounded-control px-3 py-2 text-left text-ink transition-colors hover:bg-surface-sunken"
                >
                  <div>
                    <span className="block font-semibold">{item.label}</span>
                    <span className="block text-[10px] text-ink-muted">
                      {item.desc}
                    </span>
                  </div>
                  <span className="text-[10px] text-ink-subtle">Jump</span>
                </button>
              ))}
            </div>
          )}

          {filteredCases.length > 0 && (
            <div className="space-y-1 border-t border-border/50 pt-1">
              <div className="px-2 py-1 text-[10px] tracking-wider text-ink-subtle uppercase">
                Matching Cases
              </div>
              {filteredCases.map((c) => (
                <button
                  key={c.case_id}
                  type="button"
                  onClick={() => {
                    onSelectCase(c)
                    onClose()
                  }}
                  className="flex w-full cursor-pointer items-center justify-between rounded-control px-3 py-2 text-left text-ink transition-colors hover:bg-surface-sunken"
                >
                  <div>
                    <span className="block font-semibold">{c.case_id}</span>
                    <span className="block text-[10px] text-ink-muted">
                      {formatCustomerName(c.failure_event.customer_id)} ·{' '}
                      {c.failure_event.payment_rail} · INR{' '}
                      {(c.amount_paise / 100).toFixed(0)}
                    </span>
                  </div>
                  <span className="text-[10px] text-recovered">{c.state}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
