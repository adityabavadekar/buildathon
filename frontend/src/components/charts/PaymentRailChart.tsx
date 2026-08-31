'use client'

import React from 'react'
import { Landmark, RefreshCw } from 'lucide-react'
import type { RailBreakdown } from '@/lib/api'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { RuPayIcon, UpiIcon } from '@/components/ui/BrandIcons'

interface PaymentRailChartProps {
  railPerformance: RailBreakdown[]
}

function formatINR(paise: number): string {
  const rupees = paise / 100
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(rupees)
}

function getRailIcon(rail: string) {
  const upper = rail.toUpperCase()
  if (upper.includes('UPI')) return <UpiIcon className="h-4 w-4 shrink-0" />
  if (upper.includes('CARD') || upper.includes('RUPAY'))
    return <RuPayIcon className="h-3.5 w-5 shrink-0" />
  if (
    upper.includes('MANDATE') ||
    upper.includes('AUTOPAY') ||
    upper.includes('SUBSCRIPTION')
  )
    return <RefreshCw className="h-3.5 w-3.5 shrink-0 text-accent" />
  return <Landmark className="h-3.5 w-3.5 shrink-0 text-ink-muted" />
}

export function PaymentRailChart({ railPerformance }: PaymentRailChartProps) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Landmark className="h-4 w-4 text-accent" />
          <CardTitle>Payment Rail Recovery Efficiency</CardTitle>
        </div>
        <CardDescription>
          Multi-rail performance across UPI Intent, AutoPay mandates, e-NACH,
          and Cards
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 font-mono text-xs">
        {railPerformance.length === 0 ? (
          <div className="py-8 text-center text-ink-muted">
            No payment rail telemetry available.
          </div>
        ) : (
          railPerformance.map((item) => (
            <div
              key={item.rail}
              className="space-y-1.5 rounded-control border border-border bg-surface-sunken/60 p-3"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {getRailIcon(item.rail)}
                  <span className="font-bold text-ink uppercase">
                    {item.rail.replace('_', ' ')}
                  </span>
                  <span className="text-[10px] text-ink-muted">
                    ({item.total_cases.toString()} cases)
                  </span>
                </div>
                <span className="font-bold text-recovered">
                  {item.recovery_rate_pct.toFixed(1)}% Recovery
                </span>
              </div>

              <div className="h-2 w-full overflow-hidden rounded-full bg-surface-sunken">
                <div
                  className="h-full bg-recovered transition-all duration-500"
                  style={{
                    width: `${Math.min(100, item.recovery_rate_pct).toString()}%`,
                  }}
                />
              </div>

              <div className="flex items-center justify-between pt-0.5 text-[10px] text-ink-subtle">
                <span>At Risk: {formatINR(item.at_risk_paise)}</span>
                <span className="font-semibold text-ink">
                  Recovered: {formatINR(item.recovered_paise)}
                </span>
              </div>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  )
}
