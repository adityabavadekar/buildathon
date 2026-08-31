'use client'

import React from 'react'
import { ChevronDown } from 'lucide-react'
import { RazorpaySymbol } from '@/components/ui/BrandIcons'
import {
  MAIN_NAV_ITEMS,
  OPERATIONS_NAV_ITEMS,
  SETTINGS_GROUP_ICON,
  SETTINGS_NAV_ITEMS,
  SETTINGS_SECTIONS,
  type NavSection,
} from '@/lib/navigation'

export type { NavSection }

interface SidebarProps {
  activeSection: NavSection
  onSelectSection: (section: NavSection) => void
  casesCount?: number
  escalatedCount?: number
}

function navButtonClass(isActive: boolean, nested = false): string {
  const base = nested ? 'pl-9 pr-3 py-2 text-[13px]' : 'px-3.5 py-2.5 text-sm'
  const state = isActive
    ? 'border border-border/80 bg-surface-sunken font-bold text-ink'
    : 'border border-transparent text-ink-muted hover:bg-surface-sunken/60 hover:text-ink'
  return `group flex w-full cursor-pointer items-center justify-between rounded-control font-medium transition-colors ${base} ${state}`
}

export function Sidebar({
  activeSection,
  onSelectSection,
  casesCount = 0,
  escalatedCount = 0,
}: SidebarProps) {
  const settingsActive = SETTINGS_SECTIONS.includes(activeSection)
  const [settingsExpanded, setSettingsExpanded] = React.useState(false)
  const showSettingsItems = settingsActive || settingsExpanded

  const SettingsGroupIcon = SETTINGS_GROUP_ICON

  const renderNavItem = (
    item: {
      id: NavSection
      label: string
      icon: React.ComponentType<{ className?: string }>
      badgeKey?: 'cases'
    },
    nested = false,
  ) => {
    const isActive = activeSection === item.id
    const Icon = item.icon
    const badge =
      item.badgeKey === 'cases' && casesCount > 0 ? casesCount : undefined
    const showEscalated =
      (item.id === 'recovery' || item.id === 'transactions') &&
      escalatedCount > 0

    return (
      <button
        key={item.id}
        type="button"
        onClick={() => {
          onSelectSection(item.id)
        }}
        className={navButtonClass(isActive, nested)}
      >
        <div className="flex items-center gap-3">
          <Icon
            className={`${nested ? 'h-4 w-4' : 'h-4.5 w-4.5'} shrink-0 ${isActive ? 'text-accent' : 'text-ink-muted group-hover:text-ink'}`}
          />
          <span className={nested ? 'truncate font-medium' : 'font-semibold'}>
            {item.label}
          </span>
        </div>
        {badge !== undefined ? (
          <span
            className={`rounded-control px-2 py-0.5 font-mono text-xs font-bold ${
              showEscalated
                ? 'border border-escalated/30 bg-escalated-subtle text-escalated'
                : 'border border-border bg-surface-sunken text-ink-muted'
            }`}
          >
            {badge.toString()}
          </span>
        ) : null}
      </button>
    )
  }

  return (
    <aside className="flex h-screen w-64 shrink-0 flex-col border-r border-border bg-surface select-none">
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

      <nav className="flex-1 space-y-1.5 overflow-y-auto p-3">
        <div className="px-2 py-1.5 font-mono text-xs font-bold tracking-wider text-ink-subtle uppercase">
          Main Navigation
        </div>

        {MAIN_NAV_ITEMS.map((item) => renderNavItem(item))}

        <div className="pt-2">
          <button
            type="button"
            onClick={() => {
              setSettingsExpanded((open) => !open)
            }}
            className={navButtonClass(settingsActive)}
            aria-expanded={showSettingsItems}
          >
            <div className="flex items-center gap-3">
              <SettingsGroupIcon
                className={`h-4.5 w-4.5 shrink-0 ${settingsActive ? 'text-accent' : 'text-ink-muted group-hover:text-ink'}`}
              />
              <span className="font-semibold">Settings</span>
            </div>
            <ChevronDown
              className={`h-4 w-4 shrink-0 text-ink-subtle transition-transform ${showSettingsItems ? 'rotate-180' : ''}`}
            />
          </button>

          {showSettingsItems ? (
            <div className="mt-1 space-y-0.5">
              {SETTINGS_NAV_ITEMS.map((item) => renderNavItem(item, true))}
            </div>
          ) : null}
        </div>

        <div className="px-2 py-1.5 pt-3 font-mono text-xs font-bold tracking-wider text-ink-subtle uppercase">
          Operations
        </div>

        {OPERATIONS_NAV_ITEMS.map((item) => renderNavItem(item))}
      </nav>

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
            <span className="h-2 w-2 rounded-full bg-recovered" />
            Operational
          </span>
        </button>
      </div>
    </aside>
  )
}
