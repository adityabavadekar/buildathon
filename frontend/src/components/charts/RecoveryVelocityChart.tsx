'use client'

import React, { useState } from 'react'
import { Activity } from 'lucide-react'
import type { TimePointStats } from '@/lib/api'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

interface RecoveryVelocityChartProps {
  timeSeries: TimePointStats[]
}

function formatINR(paise: number): string {
  const rupees = paise / 100
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(rupees)
}

export function RecoveryVelocityChart({ timeSeries }: RecoveryVelocityChartProps) {
  const [hoveredPoint, setHoveredPoint] = useState<TimePointStats | null>(null)

  const maxVal = Math.max(...timeSeries.map((p) => p.failed_paise), 100000)

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <div>
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-accent" />
            <CardTitle>Recovery Velocity & Time Horizon</CardTitle>
          </div>
          <CardDescription>
            Cumulative revenue at risk vs autonomous net recoveries across rolling time horizons
          </CardDescription>
        </div>
        <div className="flex items-center gap-3 text-[11px] font-mono text-ink-muted">
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-xs bg-ink/50" /> At Risk
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-xs bg-recovered" /> Recovered
          </span>
        </div>
      </CardHeader>
      <CardContent className="pt-4">
        {timeSeries.length === 0 ? (
          <div className="py-12 text-center text-xs font-mono text-ink-muted">
            No time-series telemetry available.
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex h-48 items-end gap-3 pt-6 border-b border-border/80 pb-2">
              {timeSeries.map((pt) => {
                const failedHeightPct = Math.min(100, Math.max(8, (pt.failed_paise / maxVal) * 100))
                const recHeightPct = Math.min(100, Math.max(4, (pt.recovered_paise / maxVal) * 100))

                return (
                  <div
                    key={pt.label}
                    className="flex flex-1 flex-col items-center gap-2 h-full justify-end group cursor-pointer"
                    onMouseEnter={() => {
                      setHoveredPoint(pt)
                    }}
                    onMouseLeave={() => {
                      setHoveredPoint(null)
                    }}
                  >
                    <div className="flex items-end gap-1 w-full justify-center h-full">
                      {/* At Risk Bar */}
                      <div
                        className="w-full max-w-4 rounded-t-xs bg-ink/40 group-hover:bg-ink/60 transition-all duration-300"
                        style={{ height: `${failedHeightPct.toString()}%` }}
                      />
                      {/* Recovered Bar */}
                      <div
                        className="w-full max-w-4 rounded-t-xs bg-recovered group-hover:bg-recovered-strong transition-all duration-300 shadow-xs"
                        style={{ height: `${recHeightPct.toString()}%` }}
                      />
                    </div>
                    <span className="text-[10px] font-mono text-ink-muted group-hover:text-ink">
                      {pt.label}
                    </span>
                  </div>
                )
              })}
            </div>

            {/* Context Tooltip / Active Point Details */}
            <div className="min-h-8 rounded-control bg-surface-sunken p-2 font-mono text-xs flex items-center justify-between">
              {hoveredPoint ? (
                <>
                  <span className="font-semibold text-ink">
                    Horizon: {hoveredPoint.label}
                  </span>
                  <div className="flex items-center gap-4">
                    <span className="text-ink-muted">
                      At Risk: {formatINR(hoveredPoint.failed_paise)}
                    </span>
                    <span className="text-recovered font-bold">
                      Recovered: {formatINR(hoveredPoint.recovered_paise)} (
                      {hoveredPoint.failed_paise > 0
                        ? ((hoveredPoint.recovered_paise / hoveredPoint.failed_paise) * 100).toFixed(1)
                        : 0}
                      %)
                    </span>
                  </div>
                </>
              ) : (
                <span className="text-ink-subtle text-[11px]">
                  Hover over any time horizon bar to inspect exact financial recovery volume.
                </span>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
