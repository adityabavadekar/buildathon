'use client'

import React from 'react'

interface MetricBarProps {
  label: string
  value: number
  max?: number
  hint?: string
}

function formatPercent(value: number, max: number): string {
  const share = max > 0 ? (value / max) * 100 : 0
  const rounded = Math.round(share * 10) / 10
  return `${String(rounded)}%`
}

export function MetricBar({ label, value, max = 1, hint }: MetricBarProps) {
  const share = max > 0 ? Math.max(0, Math.min(1, value / max)) : 0
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs text-ink">{label}</span>
        <span className="font-mono text-xs font-semibold text-ink">
          {formatPercent(value, max)}
        </span>
      </div>
      <div className="h-2.5 w-full overflow-hidden rounded-full border border-border bg-surface-sunken">
        <div
          className="h-full rounded-full bg-accent"
          style={{ width: `${String(Math.round(share * 100))}%` }}
        />
      </div>
      {hint ? <p className="text-[11px] text-ink-subtle">{hint}</p> : null}
    </div>
  )
}
