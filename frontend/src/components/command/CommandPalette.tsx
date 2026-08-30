'use client'

import React, { useEffect, useState } from 'react'
import type { RecoveryCase } from '@/lib/api'
import type { NavSection } from '@/components/layout/Sidebar'

interface CommandPaletteProps {
  open: boolean
  onClose: () => void
  cases: RecoveryCase[]
  onSelectCase: (c: RecoveryCase) => void
  onNavigate: (section: NavSection) => void
  onSeed: () => void
  onReset: () => void
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
        else {
          // Open trigger handled by parent or shortcut
        }
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

  const navOptions: { id: NavSection; label: string; desc: string }[] = [
    { id: 'overview', label: 'Go to Overview', desc: 'Executive KPI dashboard and opportunity matrix' },
    { id: 'recovery', label: 'Go to Recovery Cases', desc: 'Active dunning queue and operational table' },
    { id: 'analytics', label: 'Go to Analytics & Lift', desc: 'Counterfactual proof and NRV accounting' },
    { id: 'agent', label: 'Go to AI Agent Telemetry', desc: 'Live decision stream and model token metrics' },
    { id: 'policies', label: 'Go to Merchant Policies', desc: 'Guardrails, touch limits, and discount caps' },
    { id: 'audit', label: 'Go to Audit Trail', desc: 'System-wide immutable chronology' },
    { id: 'status', label: 'Go to System Status', desc: 'Telemetry, gateway health, and active queues' },
    { id: 'settings', label: 'Go to Settings', desc: 'Razorpay webhook URLs and integration config' },
  ]

  const filteredNav = navOptions.filter(
    (n) => n.label.toLowerCase().includes(query.toLowerCase()) || n.desc.toLowerCase().includes(query.toLowerCase())
  )

  const filteredCases = cases.filter(
    (c) =>
      c.case_id.toLowerCase().includes(query.toLowerCase()) ||
      c.failure_event.payment_id.toLowerCase().includes(query.toLowerCase()) ||
      c.failure_event.customer_id.toLowerCase().includes(query.toLowerCase())
  ).slice(0, 5)

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 bg-black/60 backdrop-blur-xs p-4">
      <div className="w-full max-w-xl rounded-panel bg-surface border border-border shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Search Input */}
        <div className="flex items-center border-b border-border px-4 py-3 bg-surface-sunken/40">
          <span className="text-xs font-mono text-ink-subtle mr-2 font-bold">[⌘K]</span>
          <input
            type="text"
            autoFocus
            placeholder="Type a command, case ID, customer, or navigation..."
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
            }}
            className="flex-1 bg-transparent text-xs font-mono text-ink placeholder:text-ink-subtle focus:outline-none"
          />
          <button
            type="button"
            onClick={onClose}
            className="text-[10px] font-mono text-ink-muted hover:text-ink cursor-pointer"
          >
            [Esc]
          </button>
        </div>

        {/* Results Stream */}
        <div className="max-h-96 overflow-y-auto p-2 space-y-3 font-mono text-xs">
          {/* Quick Actions */}
          <div className="space-y-1">
            <div className="px-2 py-1 text-[10px] uppercase tracking-wider text-ink-subtle">Quick Actions</div>
            <button
              type="button"
              onClick={() => {
                onSeed()
                onClose()
              }}
              className="flex w-full items-center justify-between px-3 py-2 rounded-control hover:bg-surface-sunken text-ink text-left cursor-pointer transition-colors"
            >
              <span>Seed 50 Synthetic Recovery Cases</span>
              <span className="text-[10px] text-accent font-semibold">Simulation</span>
            </button>
            <button
              type="button"
              onClick={() => {
                onReset()
                onClose()
              }}
              className="flex w-full items-center justify-between px-3 py-2 rounded-control hover:bg-surface-sunken text-ink text-left cursor-pointer transition-colors"
            >
              <span>Reset & Purge All Simulation Data</span>
              <span className="text-[10px] text-failed font-semibold">Purge</span>
            </button>
          </div>

          {/* Navigation */}
          {filteredNav.length > 0 && (
            <div className="space-y-1 pt-1 border-t border-border/50">
              <div className="px-2 py-1 text-[10px] uppercase tracking-wider text-ink-subtle">Navigation</div>
              {filteredNav.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    onNavigate(item.id)
                    onClose()
                  }}
                  className="flex w-full items-center justify-between px-3 py-2 rounded-control hover:bg-surface-sunken text-ink text-left cursor-pointer transition-colors"
                >
                  <div>
                    <span className="font-semibold block">{item.label}</span>
                    <span className="text-[10px] text-ink-muted block">{item.desc}</span>
                  </div>
                  <span className="text-[10px] text-ink-subtle">Jump</span>
                </button>
              ))}
            </div>
          )}

          {/* Matching Cases */}
          {filteredCases.length > 0 && (
            <div className="space-y-1 pt-1 border-t border-border/50">
              <div className="px-2 py-1 text-[10px] uppercase tracking-wider text-ink-subtle">Matching Cases</div>
              {filteredCases.map((c) => (
                <button
                  key={c.case_id}
                  type="button"
                  onClick={() => {
                    onSelectCase(c)
                    onClose()
                  }}
                  className="flex w-full items-center justify-between px-3 py-2 rounded-control hover:bg-surface-sunken text-ink text-left cursor-pointer transition-colors"
                >
                  <div>
                    <span className="font-semibold block">{c.case_id}</span>
                    <span className="text-[10px] text-ink-muted block">
                      {c.failure_event.customer_id} · {c.failure_event.payment_rail} · INR {(c.amount_paise / 100).toFixed(0)}
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
