'use client'

import React, { useEffect, useState } from 'react'
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  RotateCcw,
  Search,
} from 'lucide-react'
import type { AnalyticsSummaryResponse, HealthResponse } from '@/lib/api'
import { AutonomySwitcher } from '@/components/layout/AutonomySwitcher'
import { formatINR } from '@/lib/format'

interface TopNavProps {
  title: string
  health: HealthResponse | null
  analytics: AnalyticsSummaryResponse | null
  healthLoading: boolean
  lastRefreshedAt?: Date | null
  onRefresh: () => void
  onOpenCommand: () => void
}

function formatTimeAgo(date: Date | null | undefined): string {
  if (!date) return 'Live'
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000))
  if (seconds < 5) return 'Just now'
  if (seconds < 60) return `${seconds.toString()}s ago`
  const minutes = Math.floor(seconds / 60)
  return `${minutes.toString()}m ago`
}

export function TopNav({
  title,
  health,
  analytics,
  healthLoading,
  lastRefreshedAt,
  onRefresh,
  onOpenCommand,
}: TopNavProps) {
  const [, setTick] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => {
      setTick((t) => t + 1)
    }, 3000)
    return () => {
      clearInterval(timer)
    }
  }, [])

  return (
    <header className="app-topbar flex h-[3.75rem] shrink-0 items-center justify-between gap-4 px-5 lg:px-6">
      <div className="flex min-w-0 items-center gap-4 lg:gap-5">
        <div className="min-w-0">
          <h1 className="topbar-title truncate">{title}</h1>
        </div>

        <div className="topbar-divider hidden sm:block" />

        <AutonomySwitcher />

        {analytics && analytics.net_recovered_value_paise > 0 ? (
          <div className="topbar-chip topbar-chip--success hidden xl:flex">
            <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
            <span>
              <strong>{formatINR(analytics.net_recovered_value_paise)}</strong>{' '}
              NRV
            </span>
            <span className="text-sidebar-ink-subtle">
              · {analytics.treatment_recovered.toString()} recovered
            </span>
          </div>
        ) : null}
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <button type="button" onClick={onOpenCommand} className="topbar-action">
          <Search className="h-3.5 w-3.5 shrink-0" />
          <span className="hidden sm:inline">Search</span>
          <kbd>⌘K</kbd>
        </button>

        <div className="topbar-chip hidden md:inline-flex">
          <Clock className="h-3.5 w-3.5 shrink-0" />
          <span>
            Synced <strong>{formatTimeAgo(lastRefreshedAt)}</strong>
          </span>
        </div>

        {healthLoading ? (
          <div className="topbar-chip">Connecting...</div>
        ) : health ? (
          <div className="topbar-chip topbar-chip--success hidden lg:inline-flex">
            <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
            <span>
              <strong>Online</strong>
            </span>
          </div>
        ) : (
          <div className="topbar-chip hidden lg:inline-flex">
            <AlertCircle className="h-3.5 w-3.5 shrink-0 text-failed" />
            <span className="text-failed">
              <strong>Offline</strong>
            </span>
          </div>
        )}

        <button
          type="button"
          onClick={onRefresh}
          className="topbar-action topbar-action--emphasis"
          title="Refresh data"
        >
          <RotateCcw className="h-3.5 w-3.5 shrink-0" />
          <span className="hidden sm:inline">Sync</span>
        </button>
      </div>
    </header>
  )
}
