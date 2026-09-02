'use client'

import React from 'react'
import { RazorpaySymbol } from '@/components/ui/BrandIcons'
import {
  MAIN_NAV_ITEMS,
  OPERATIONS_NAV_ITEMS,
  SETTINGS_NAV_ITEMS,
  hashForSection,
  type NavSection,
} from '@/lib/navigation'

export type { NavSection }

interface SidebarProps {
  activeSection: NavSection
  onSelectSection: (section: NavSection) => void
  casesCount?: number
  escalatedCount?: number
}

interface NavItemConfig {
  id: NavSection
  label: string
  icon: React.ComponentType<{ className?: string }>
  badgeKey?: 'cases' | 'escalated'
}

export function Sidebar({
  activeSection,
  onSelectSection,
  casesCount = 0,
  escalatedCount = 0,
}: SidebarProps) {
  const renderNavItem = (item: NavItemConfig, nested = false) => {
    const isActive = activeSection === item.id
    const Icon = item.icon
    const badge =
      item.badgeKey === 'cases' && casesCount > 0
        ? casesCount
        : item.badgeKey === 'escalated' && escalatedCount > 0
          ? escalatedCount
          : undefined
    const showEscalated =
      (item.id === 'recovery' ||
        item.id === 'transactions' ||
        item.id === 'approvals') &&
      escalatedCount > 0

    return (
      <a
        key={item.id}
        href={hashForSection(item.id)}
        aria-current={isActive ? 'page' : undefined}
        onClick={(event) => {
          // Let modified clicks (new tab/window) fall through to the browser.
          if (
            event.metaKey ||
            event.ctrlKey ||
            event.shiftKey ||
            event.button !== 0
          ) {
            return
          }
          event.preventDefault()
          onSelectSection(item.id)
        }}
        className={`sidebar-nav-item ${isActive ? 'sidebar-nav-item--active' : ''} ${nested ? 'sidebar-nav-item--nested' : ''}`}
      >
        <div className="flex min-w-0 items-center gap-3">
          <Icon className="sidebar-nav-icon h-[1.125rem] w-[1.125rem] shrink-0" />
          <span className="truncate">{item.label}</span>
        </div>
        {badge !== undefined ? (
          <span
            className={`sidebar-nav-badge ${showEscalated ? 'sidebar-nav-badge--alert' : ''}`}
          >
            {badge.toString()}
          </span>
        ) : null}
      </a>
    )
  }

  return (
    <aside className="app-sidebar flex h-screen w-[17.5rem] shrink-0 flex-col select-none">
      <div className="flex h-16 items-center gap-3 border-b border-sidebar-border px-5">
        <div className="sidebar-brand-logo flex h-9 w-9 items-center justify-center rounded-control border">
          <RazorpaySymbol className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <span className="sidebar-brand-title block text-[0.9375rem] font-semibold tracking-tight">
            FORTX
          </span>
          <span className="sidebar-brand-tagline block truncate text-xs">
            Revenue recovery
          </span>
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-2">
        <div className="sidebar-section-label">Main</div>
        {MAIN_NAV_ITEMS.map((item) => renderNavItem(item))}

        <div className="sidebar-section-label">Settings</div>
        {SETTINGS_NAV_ITEMS.map((item) => renderNavItem(item, true))}

        <div className="sidebar-section-label">Operations</div>
        {OPERATIONS_NAV_ITEMS.map((item) => renderNavItem(item))}
      </nav>

      <div className="sidebar-footer px-4 py-3.5">
        <button
          type="button"
          onClick={() => {
            onSelectSection('status')
          }}
          className="sidebar-footer-button flex w-full cursor-pointer items-center justify-between text-sm transition-colors"
        >
          <span className="font-medium">Engine health</span>
          <span className="flex items-center gap-1.5 text-xs font-semibold text-recovered">
            <span className="h-1.5 w-1.5 rounded-full bg-recovered" />
            Operational
          </span>
        </button>
      </div>
    </aside>
  )
}
