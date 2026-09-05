'use client'

import React, { useState } from 'react'
import { BarChart3, Calendar } from 'lucide-react'
import type { DailyMetricPoint, MonthlyMetricPoint } from '@/lib/api'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'

interface DailyVolumeTrendsChartProps {
  dailyMetrics?: DailyMetricPoint[]
  monthlyMetrics?: MonthlyMetricPoint[]
}

function formatINR(paise: number): string {
  const rupees = paise / 100
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(rupees)
}

export function DailyVolumeTrendsChart({
  dailyMetrics = [],
  monthlyMetrics = [],
}: DailyVolumeTrendsChartProps) {
  const [granularity, setGranularity] = useState<'daily' | 'monthly'>('daily')
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null)

  const items = granularity === 'daily' ? dailyMetrics : monthlyMetrics

  const maxTotal = Math.max(...items.map((i) => i.total_transactions), 1)

  const hoveredItem =
    hoveredIdx !== null && items[hoveredIdx] ? items[hoveredIdx] : null

  return (
    <Card className="col-span-full">
      <CardHeader className="flex flex-col gap-3 border-b border-border/40 pb-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-accent" />
            <CardTitle className="text-base">
              Transaction volume and recovery
            </CardTitle>
          </div>
          <CardDescription className="mt-0.5">
            Failed, recovered, and escalated cases by day or month.
          </CardDescription>
        </div>

        {/* Time Granularity Toggle */}
        <div className="flex items-center gap-2">
          <div className="flex items-center rounded-control border border-border bg-surface-sunken p-1">
            <Button
              size="sm"
              variant={granularity === 'daily' ? 'primary' : 'ghost'}
              onClick={() => {
                setGranularity('daily')
                setHoveredIdx(null)
              }}
              className="h-7 px-2.5 text-xs"
            >
              <Calendar className="mr-1 h-3 w-3" />
              Daily
            </Button>
            <Button
              size="sm"
              variant={granularity === 'monthly' ? 'primary' : 'ghost'}
              onClick={() => {
                setGranularity('monthly')
                setHoveredIdx(null)
              }}
              className="h-7 px-2.5 text-xs"
            >
              <BarChart3 className="mr-1 h-3 w-3" />
              Monthly
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4 pt-4">
        {/* Legend & Hovered Detail Strip */}
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-panel border border-border/50 bg-surface-sunken/40 p-3 text-xs">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5 text-ink">
              <span className="h-2.5 w-2.5 rounded-xs bg-ink/70" /> Total
              Ingested
            </span>
            <span className="flex items-center gap-1.5 text-recovered">
              <span className="h-2.5 w-2.5 rounded-xs bg-recovered" /> Recovered
            </span>
            <span className="flex items-center gap-1.5 text-escalated">
              <span className="h-2.5 w-2.5 rounded-xs bg-escalated" /> Escalated
              (HITL)
            </span>
            <span className="flex items-center gap-1.5 text-failed">
              <span className="h-2.5 w-2.5 rounded-xs bg-failed" /> Unrecovered
            </span>
          </div>

          {hoveredItem ? (
            <div className="flex items-center gap-3 text-xs">
              <span className="font-bold text-ink">
                {'date' in hoveredItem ? hoveredItem.date : hoveredItem.month}:
              </span>
              <span className="font-bold text-recovered">
                +{formatINR(hoveredItem.recovered_paise)} (
                {hoveredItem.recovery_rate_pct.toFixed(1)}% rate)
              </span>
              <span className="text-ink-muted">
                At Risk: {formatINR(hoveredItem.at_risk_paise)}
              </span>
            </div>
          ) : (
            <span className="text-[11px] text-ink-subtle">
              Hover over a period bar to inspect details
            </span>
          )}
        </div>

        {items.length === 0 ? (
          <div className="py-16 text-center text-sm text-ink-muted">
            No chronological transaction telemetry recorded yet. Seed a recovery
            batch to populate volume graphs.
          </div>
        ) : (
          <div className="space-y-3">
            {/* Chart Area */}
            <div className="flex h-56 items-end gap-2 overflow-x-auto border-b border-border pt-8 pb-2 sm:gap-4">
              {items.map((item, idx) => {
                const totalH = Math.max(
                  12,
                  Math.round((item.total_transactions / maxTotal) * 100),
                )
                const recH = Math.max(
                  4,
                  Math.round((item.recovered_count / maxTotal) * 100),
                )
                const escH = Math.max(
                  0,
                  Math.round((item.escalated_count / maxTotal) * 100),
                )
                const isHovered = hoveredIdx === idx
                const label = 'date' in item ? item.date.slice(5) : item.month

                return (
                  <div
                    key={'date' in item ? item.date : item.month}
                    className="group flex h-full min-w-[36px] flex-1 cursor-pointer flex-col items-center justify-end gap-1.5"
                    onMouseEnter={() => {
                      setHoveredIdx(idx)
                    }}
                    onMouseLeave={() => {
                      setHoveredIdx(null)
                    }}
                  >
                    <div className="relative flex h-full w-full max-w-[32px] items-end justify-center gap-0.5">
                      {/* Total Ingested Bar */}
                      <div
                        className={`w-2.5 rounded-t-xs transition-all duration-300 ${
                          isHovered
                            ? 'bg-ink'
                            : 'bg-ink/40 group-hover:bg-ink/70'
                        }`}
                        style={{ height: `${totalH.toString()}%` }}
                        title={`Total: ${item.total_transactions.toString()}`}
                      />
                      {/* Recovered Bar */}
                      <div
                        className={`w-2.5 rounded-t-xs transition-all duration-300 ${
                          isHovered
                            ? 'bg-recovered'
                            : 'bg-recovered/80 group-hover:bg-recovered'
                        }`}
                        style={{ height: `${recH.toString()}%` }}
                        title={`Recovered: ${item.recovered_count.toString()}`}
                      />
                      {/* Escalated Bar */}
                      {escH > 0 && (
                        <div
                          className={`w-2 rounded-t-xs transition-all duration-300 ${
                            isHovered
                              ? 'bg-escalated'
                              : 'bg-escalated/80 group-hover:bg-escalated'
                          }`}
                          style={{ height: `${escH.toString()}%` }}
                          title={`Escalated: ${item.escalated_count.toString()}`}
                        />
                      )}
                    </div>
                    <span
                      className={`text-[11px] whitespace-nowrap ${
                        isHovered ? 'font-semibold text-ink' : 'text-ink-muted'
                      }`}
                    >
                      {label}
                    </span>
                  </div>
                )
              })}
            </div>

            {/* Summary KPI Strip */}
            <div className="grid grid-cols-2 gap-3 pt-2 text-xs sm:grid-cols-4">
              <div className="rounded-control border border-border bg-surface-sunken p-3">
                <span className="block text-[11px] text-ink-muted">
                  Total Transactions
                </span>
                <span className="mt-0.5 block text-base font-bold text-ink">
                  {items
                    .reduce((acc, i) => acc + i.total_transactions, 0)
                    .toString()}
                </span>
              </div>
              <div className="rounded-control border border-recovered/30 bg-recovered/10 p-3">
                <span className="block text-[11px] font-semibold text-recovered">
                  Recovered Transactions
                </span>
                <span className="mt-0.5 block text-base font-bold text-recovered">
                  {items
                    .reduce((acc, i) => acc + i.recovered_count, 0)
                    .toString()}
                </span>
              </div>
              <div className="rounded-control border border-escalated/30 bg-escalated/10 p-3">
                <span className="block text-[11px] font-semibold text-escalated">
                  Escalated to Operator
                </span>
                <span className="mt-0.5 block text-base font-bold text-escalated">
                  {items
                    .reduce((acc, i) => acc + i.escalated_count, 0)
                    .toString()}
                </span>
              </div>
              <div className="rounded-control border border-accent/30 bg-accent/10 p-3">
                <span className="block text-[11px] font-semibold text-accent">
                  Total Recovered Yield
                </span>
                <span className="mt-0.5 block text-base font-bold text-accent">
                  {formatINR(
                    items.reduce((acc, i) => acc + i.recovered_paise, 0),
                  )}
                </span>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
