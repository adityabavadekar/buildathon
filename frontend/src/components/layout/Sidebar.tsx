'use client'

import React from 'react'
import {
  Activity,
  BarChart3,
  Bot,
  Coins,
  GitBranch,
  History,
  LayoutDashboard,
  Radio,
  Settings,
  ShieldCheck,
} from 'lucide-react'
import { RazorpaySymbol } from '@/components/ui/BrandIcons'

export type NavSection =
  | 'overview'
  | 'pipeline'
  | 'workflows'
  | 'recovery'
  | 'analytics'
  | 'agent'
  | 'policies'
  | 'audit'
  | 'status'
  | 'settings'

interface SidebarProps {
  activeSection: NavSection
  onSelectSection: (section: NavSection) => void
  casesCount?: number
  escalatedCount?: number
}

export function Sidebar({
  activeSection,
  onSelectSection,
  casesCount = 0,
  escalatedCount = 0,
}: SidebarProps) {
  const navItems: {
    id: NavSection
    label: string
    icon: React.ComponentType<{ className?: string }>
    badge?: number
  }[] = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    { id: 'pipeline', label: 'Data Pipeline', icon: Radio },
    { id: 'workflows', label: 'Workflows', icon: GitBranch },
    { id: 'recovery', label: 'Recovery Cases', icon: Coins, badge: casesCount },
    { id: 'analytics', label: 'Analytics & Lift', icon: BarChart3 },
    { id: 'agent', label: 'AI Agent Telemetry', icon: Bot },
    { id: 'policies', label: 'Merchant Policies', icon: ShieldCheck },
    { id: 'audit', label: 'Audit Trail', icon: History },
    { id: 'status', label: 'System Status', icon: Activity },
    { id: 'settings', label: 'Settings', icon: Settings },
  ]

  return (
    <aside className="flex h-screen w-64 shrink-0 flex-col border-r border-border bg-surface select-none">
      {/* Brand Header */}
      <div className="flex h-16 items-center gap-3 border-b border-border px-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-control border border-accent/30 bg-accent/10 text-accent">
          <RazorpaySymbol className="h-5 w-5" />
        </div>
        <div>
          <span className="block text-base font-bold tracking-tight text-ink">
            FORTX
          </span>
          <span className="block font-mono text-xs tracking-wider text-ink-subtle uppercase">
            Flow Orchestration
          </span>
        </div>
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 space-y-1.5 overflow-y-auto p-3">
        <div className="px-2 py-1.5 font-mono text-xs font-bold tracking-wider text-ink-subtle uppercase">
          Main Navigation
        </div>
        {navItems.map((item) => {
          const isActive = activeSection === item.id
          const Icon = item.icon
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => {
                onSelectSection(item.id)
              }}
              className={`group flex w-full cursor-pointer items-center justify-between rounded-control px-3.5 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? 'border border-border/80 bg-surface-sunken font-bold text-ink shadow-xs'
                  : 'border border-transparent text-ink-muted hover:bg-surface-sunken/60 hover:text-ink'
              }`}
            >
              <div className="flex items-center gap-3">
                <Icon
                  className={`h-4.5 w-4.5 shrink-0 ${isActive ? 'text-accent' : 'text-ink-muted group-hover:text-ink'}`}
                />
                <span className="text-sm font-semibold">{item.label}</span>
              </div>
              {item.badge !== undefined && item.badge > 0 && (
                <span
                  className={`rounded-control px-2 py-0.5 font-mono text-xs font-bold ${
                    item.id === 'recovery' && escalatedCount > 0
                      ? 'border border-escalated/30 bg-escalated-subtle text-escalated'
                      : 'border border-border bg-surface-sunken text-ink-muted'
                  }`}
                >
                  {item.badge.toString()}
                </span>
              )}
            </button>
          )
        })}
      </nav>

      {/* Footer Status Widget */}
      <div className="border-t border-border bg-surface-sunken/40 p-4">
        <button
          type="button"
          onClick={() => {
            onSelectSection('status')
          }}
          className="flex w-full cursor-pointer items-center justify-between font-mono text-sm text-ink-muted transition-colors hover:text-ink"
        >
          <span className="font-semibold">Engine Health</span>
          <span className="flex items-center gap-1.5 text-xs font-bold text-recovered">
            <span className="h-2 w-2 animate-pulse rounded-full bg-recovered" />
            Operational
          </span>
        </button>
      </div>
    </aside>
  )
}
