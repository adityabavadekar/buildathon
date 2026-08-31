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

interface TopNavProps {
  title: string
  health: HealthResponse | null
  analytics: AnalyticsSummaryResponse | null
  healthLoading: boolean
  lastRefreshedAt?: Date | null
  onRefresh: () => void
  onOpenCommand: () => void
}

function formatINR(paise: number): string {
  const rupees = paise / 100
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(rupees)
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

  // Force re-render every 3 seconds to keep relative refresh timestamp live
  useEffect(() => {
    const timer = setInterval(() => {
      setTick((t) => t + 1)
    }, 3000)
    return () => {
      clearInterval(timer)
    }
  }, [])

  return (
    <header className="flex h-16 items-center justify-between border-b border-border bg-surface px-6">
      <div className="flex items-center gap-4">
        <h1 className="text-base font-semibold tracking-tight text-ink capitalize">
          {title}
        </h1>

        {/* Global Autonomy Mode Control */}
        <AutonomySwitcher />

        {/* Live Recovery Pulse Ticker */}
        {analytics && analytics.net_recovered_value_paise > 0 && (
          <div className="hidden items-center gap-2 rounded-control border border-recovered/30 bg-recovered-subtle/20 px-2.5 py-1 font-mono text-xs lg:flex">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-recovered" />
            <span className="font-bold text-recovered">
              {formatINR(analytics.net_recovered_value_paise)} NRV
            </span>
            <span className="text-ink-muted">
              · {analytics.treatment_recovered.toString()} resolved
            </span>
          </div>
        )}
      </div>

      <div className="flex items-center gap-3">
        {/* Command Palette Trigger */}
        <button
          type="button"
          onClick={onOpenCommand}
          className="flex cursor-pointer items-center gap-2 rounded-control border border-border bg-surface-sunken px-3 py-1.5 font-mono text-xs text-ink-muted transition-colors hover:border-border-strong hover:text-ink"
        >
          <Search className="h-3.5 w-3.5 text-ink-subtle" />
          <span className="hidden sm:inline">Search & Actions</span>
          <kbd className="rounded border border-border/80 bg-surface px-1 text-[10px] text-ink-subtle">
            ⌘K
          </kbd>
        </button>

        {/* Live Last Refreshed Indicator */}
        <div className="hidden items-center gap-1.5 rounded-control border border-border/60 bg-surface-sunken px-2 py-1 font-mono text-[11px] text-ink-muted md:flex">
          <Clock className="h-3 w-3 text-ink-subtle" />
          <span>Last sync:</span>
          <span className="font-semibold text-ink">
            {formatTimeAgo(lastRefreshedAt)}
          </span>
        </div>

        {/* Backend Connectivity Status */}
        {healthLoading ? (
          <span className="font-mono text-xs text-ink-muted">
            Connecting...
          </span>
        ) : health ? (
          <div className="flex items-center gap-1.5 text-recovered">
            <CheckCircle2 className="h-3.5 w-3.5" />
            <span className="hidden font-mono text-xs text-ink-muted lg:inline">
              v{health.version} ({health.env})
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-1.5 text-failed">
            <AlertCircle className="h-3.5 w-3.5" />
            <span className="font-mono text-xs">Offline</span>
          </div>
        )}

        <button
          type="button"
          onClick={onRefresh}
          className="flex cursor-pointer items-center gap-1.5 rounded-control border border-border bg-surface-sunken px-2.5 py-1.5 font-mono text-xs text-ink-muted transition-colors hover:bg-border/40 hover:text-ink"
          title="Refresh Data"
        >
          <RotateCcw className="h-3 w-3" />
          <span>Sync</span>
        </button>
      </div>
    </header>
  )
}
