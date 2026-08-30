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

  const maxTotal = Math.max(
    ...items.map((i) => i.total_transactions),
    1
  )

  const hoveredItem = hoveredIdx !== null && items[hoveredIdx] ? items[hoveredIdx] : null

  return (
    <Card className="col-span-full">
      <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-3 gap-3 border-b border-border/40">
        <div>
          <div className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-accent" />
            <CardTitle className="text-base font-mono">
              Transaction Volume & Recovery Trajectory
            </CardTitle>
          </div>
          <CardDescription className="text-xs mt-0.5">
            Historical transaction breakdown per day/month across failed, recovered, and human-escalated states.
          </CardDescription>
        </div>

        {/* Time Granularity Toggle */}
        <div className="flex items-center gap-2">
          <div className="flex items-center rounded-control bg-surface-sunken p-1 border border-border">
            <Button
              size="sm"
              variant={granularity === 'daily' ? 'primary' : 'ghost'}
              onClick={() => {
                setGranularity('daily')
                setHoveredIdx(null)
              }}
              className="h-7 text-xs font-mono px-2.5"
            >
              <Calendar className="h-3 w-3 mr-1" />
              Daily
            </Button>
            <Button
              size="sm"
              variant={granularity === 'monthly' ? 'primary' : 'ghost'}
              onClick={() => {
                setGranularity('monthly')
                setHoveredIdx(null)
              }}
              className="h-7 text-xs font-mono px-2.5"
            >
              <BarChart3 className="h-3 w-3 mr-1" />
              Monthly
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="pt-4 space-y-4">
        {/* Legend & Hovered Detail Strip */}
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs font-mono bg-surface-sunken/40 p-3 rounded-control border border-border/50">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5 text-ink">
              <span className="h-2.5 w-2.5 rounded-xs bg-ink/70" /> Total Ingested
            </span>
            <span className="flex items-center gap-1.5 text-recovered">
              <span className="h-2.5 w-2.5 rounded-xs bg-recovered" /> Recovered
            </span>
            <span className="flex items-center gap-1.5 text-escalated">
              <span className="h-2.5 w-2.5 rounded-xs bg-escalated" /> Escalated (HITL)
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
              <span className="text-recovered font-bold">
                +{formatINR(hoveredItem.recovered_paise)} ({hoveredItem.recovery_rate_pct.toFixed(1)}% rate)
              </span>
              <span className="text-ink-muted">
                At Risk: {formatINR(hoveredItem.at_risk_paise)}
              </span>
            </div>
          ) : (
            <span className="text-ink-subtle text-[11px]">Hover over a period bar to inspect details</span>
          )}
        </div>

        {items.length === 0 ? (
          <div className="py-16 text-center text-xs font-mono text-ink-muted">
            No chronological transaction telemetry recorded yet. Seed a recovery batch to populate volume graphs.
          </div>
        ) : (
          <div className="space-y-3">
            {/* Chart Area */}
            <div className="flex h-56 items-end gap-2 sm:gap-4 pt-8 border-b border-border pb-2 overflow-x-auto">
              {items.map((item, idx) => {
                const totalH = Math.max(12, Math.round((item.total_transactions / maxTotal) * 100))
                const recH = Math.max(4, Math.round((item.recovered_count / maxTotal) * 100))
                const escH = Math.max(0, Math.round((item.escalated_count / maxTotal) * 100))
                const isHovered = hoveredIdx === idx
                const label = 'date' in item ? item.date.slice(5) : item.month

                return (
                  <div
                    key={'date' in item ? item.date : item.month}
                    className="flex flex-1 flex-col items-center gap-1.5 h-full justify-end cursor-pointer group min-w-[36px]"
                    onMouseEnter={() => {
                      setHoveredIdx(idx)
                    }}
                    onMouseLeave={() => {
                      setHoveredIdx(null)
                    }}
                  >
                    <div className="relative w-full max-w-[32px] flex items-end justify-center gap-0.5 h-full">
                      {/* Total Ingested Bar */}
                      <div
                        className={`w-2.5 rounded-t-xs transition-all duration-300 ${
                          isHovered ? 'bg-ink' : 'bg-ink/40 group-hover:bg-ink/70'
                        }`}
                        style={{ height: `${totalH.toString()}%` }}
                        title={`Total: ${item.total_transactions.toString()}`}
                      />
                      {/* Recovered Bar */}
                      <div
                        className={`w-2.5 rounded-t-xs transition-all duration-300 ${
                          isHovered ? 'bg-recovered' : 'bg-recovered/80 group-hover:bg-recovered'
                        }`}
                        style={{ height: `${recH.toString()}%` }}
                        title={`Recovered: ${item.recovered_count.toString()}`}
                      />
                      {/* Escalated Bar */}
                      {escH > 0 && (
                        <div
                          className={`w-2 rounded-t-xs transition-all duration-300 ${
                            isHovered ? 'bg-escalated' : 'bg-escalated/80 group-hover:bg-escalated'
                          }`}
                          style={{ height: `${escH.toString()}%` }}
                          title={`Escalated: ${item.escalated_count.toString()}`}
                        />
                      )}
                    </div>
                    <span
                      className={`text-[10px] font-mono whitespace-nowrap ${
                        isHovered ? 'font-bold text-ink' : 'text-ink-muted'
                      }`}
                    >
                      {label}
                    </span>
                  </div>
                )
              })}
            </div>

            {/* Summary KPI Strip */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono text-xs pt-2">
              <div className="p-3 rounded-control bg-surface-sunken border border-border">
                <span className="text-ink-muted block text-[11px]">Total Transactions</span>
                <span className="text-base font-bold text-ink mt-0.5 block">
                  {items.reduce((acc, i) => acc + i.total_transactions, 0).toString()}
                </span>
              </div>
              <div className="p-3 rounded-control bg-recovered/10 border border-recovered/30">
                <span className="text-recovered block text-[11px] font-semibold">Recovered Transactions</span>
                <span className="text-base font-bold text-recovered mt-0.5 block">
                  {items.reduce((acc, i) => acc + i.recovered_count, 0).toString()}
                </span>
              </div>
              <div className="p-3 rounded-control bg-escalated/10 border border-escalated/30">
                <span className="text-escalated block text-[11px] font-semibold">Escalated to Operator</span>
                <span className="text-base font-bold text-escalated mt-0.5 block">
                  {items.reduce((acc, i) => acc + i.escalated_count, 0).toString()}
                </span>
              </div>
              <div className="p-3 rounded-control bg-accent/10 border border-accent/30">
                <span className="text-accent block text-[11px] font-semibold">Total Recovered Yield</span>
                <span className="text-base font-bold text-accent mt-0.5 block">
                  {formatINR(items.reduce((acc, i) => acc + i.recovered_paise, 0))}
                </span>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
