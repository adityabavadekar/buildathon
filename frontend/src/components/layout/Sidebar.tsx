'use client'

import React from 'react'
import {
  Activity,
  BarChart3,
  Bot,
  Coins,
  History,
  LayoutDashboard,
  Settings,
  ShieldCheck,
} from 'lucide-react'

export type NavSection =
  | 'overview'
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
    { id: 'recovery', label: 'Recovery Cases', icon: Coins, badge: casesCount },
    { id: 'analytics', label: 'Analytics & Lift', icon: BarChart3 },
    { id: 'agent', label: 'AI Agent Telemetry', icon: Bot },
    { id: 'policies', label: 'Merchant Policies', icon: ShieldCheck },
    { id: 'audit', label: 'Audit Trail', icon: History },
    { id: 'status', label: 'System Status', icon: Activity },
    { id: 'settings', label: 'Settings', icon: Settings },
  ]

  return (
    <aside className="flex h-screen w-64 flex-col border-r border-border bg-surface shrink-0 select-none">
      {/* Brand Header */}
      <div className="flex h-16 items-center gap-3 border-b border-border px-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-control bg-accent-subtle border border-accent/40 font-mono font-bold text-xs text-accent">
          RZ
        </div>
        <div>
          <span className="text-sm font-semibold tracking-tight text-ink block">
            Revenue Recovery
          </span>
          <span className="text-[10px] font-mono text-ink-subtle block uppercase tracking-wider">
            Autonomous Engine
          </span>
        </div>
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 space-y-1 p-3 overflow-y-auto">
        <div className="px-2 py-1.5 text-[10px] font-mono font-medium uppercase tracking-wider text-ink-subtle">
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
              className={`group flex w-full items-center justify-between rounded-control px-3 py-2 text-xs font-medium transition-colors cursor-pointer ${
                isActive
                  ? 'bg-surface-sunken font-semibold text-ink shadow-xs border border-border/80'
                  : 'text-ink-muted hover:bg-surface-sunken/60 hover:text-ink border border-transparent'
              }`}
            >
              <div className="flex items-center gap-2.5">
                <Icon className={`h-4 w-4 shrink-0 ${isActive ? 'text-accent' : 'text-ink-muted group-hover:text-ink'}`} />
                <span>{item.label}</span>
              </div>
              {item.badge !== undefined && item.badge > 0 && (
                <span
                  className={`rounded-control px-1.5 py-0.5 text-[10px] font-mono ${
                    item.id === 'recovery' && escalatedCount > 0
                      ? 'bg-escalated-subtle text-escalated border border-escalated/30'
                      : 'bg-surface-sunken text-ink-muted border border-border'
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
      <div className="border-t border-border p-4 bg-surface-sunken/40">
        <button
          type="button"
          onClick={() => {
            onSelectSection('status')
          }}
          className="flex w-full items-center justify-between text-xs text-ink-muted font-mono hover:text-ink transition-colors cursor-pointer"
        >
          <span>Engine Health</span>
          <span className="flex items-center gap-1.5 text-recovered font-medium">
            <span className="h-1.5 w-1.5 rounded-full bg-recovered animate-pulse" />
            Operational
          </span>
        </button>
      </div>
    </aside>
  )
}
