'use client'

import React from 'react'
import {
  BarChart3,
  CheckCircle2,
  TrendingUp,
} from 'lucide-react'
import type { AnalyticsSummaryResponse, PolicyResponse } from '@/lib/api'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { SkeletonCard } from '@/components/ui/skeleton'
import { HealthScoreCard } from '@/components/charts/HealthScoreCard'
import { LatencyDistributionChart } from '@/components/charts/LatencyDistributionChart'
import { PaymentRailChart } from '@/components/charts/PaymentRailChart'
import { RecoveryVelocityChart } from '@/components/charts/RecoveryVelocityChart'

interface AnalyticsViewProps {
  analytics: AnalyticsSummaryResponse | null
  policies: PolicyResponse | null
  loading: boolean
}

function formatINR(paise: number): string {
  const rupees = paise / 100
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(rupees)
}

export function AnalyticsView({ analytics, policies, loading }: AnalyticsViewProps) {
  if (loading || !analytics) {
    return (
      <div className="space-y-6">
        <SkeletonCard />
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      </div>
    )
  }

  const atRisk = analytics.total_at_risk_paise
  const recovered = analytics.recovered_amount_paise
  const totalCost =
    analytics.total_gateway_fees_paise +
    analytics.total_communication_cost_paise +
    analytics.total_discounts_granted_paise
  const nrv = analytics.net_recovered_value_paise
  const unrecovered = Math.max(0, atRisk - recovered)

  const recoveredWidthPct =
    atRisk > 0 ? ((recovered / atRisk) * 100).toFixed(1) : '0'
  const costWidthPct =
    atRisk > 0 ? Math.max(1, (totalCost / atRisk) * 100).toFixed(1) : '0'

  return (
    <div className="space-y-6">
      {/* 1. Health Score & Streak Card */}
      <HealthScoreCard
        healthScore={analytics.health_score}
        returnOnSpend={analytics.return_on_recovery_spend}
        recoveryStreak={analytics.recovery_streak}
      />

      {/* 2. Counterfactual Lift Banner */}
      <Card className="border-accent/40 bg-accent-subtle/20">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-accent" />
              <CardTitle>Counterfactual Proof & A/B Recovery Lift</CardTitle>
            </div>
            <span className="rounded-control bg-accent/20 px-2.5 py-1 text-xs font-mono font-bold text-accent">
              +{analytics.attributable_lift_pct.toFixed(1)}% Absolute Uplift
            </span>
          </div>
          <CardDescription>
            Rigorous A/B verification measuring autonomous engine lift against the uncontacted holdout arm
          </CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="p-3.5 rounded-control bg-surface border border-border">
            <span className="text-xs text-ink-muted font-mono block">Treatment Group (AI Engine)</span>
            <span className="text-2xl font-bold font-mono text-recovered mt-1 block">
              {analytics.treatment_recovery_rate_pct.toFixed(1)}%
            </span>
            <span className="text-[11px] text-ink-subtle mt-0.5 block font-mono">
              {analytics.treatment_recovered.toString()} / {analytics.treatment_total.toString()} cases resolved
            </span>
          </div>

          <div className="p-3.5 rounded-control bg-surface border border-border">
            <span className="text-xs text-ink-muted font-mono block">Holdout Control Group (Naive)</span>
            <span className="text-2xl font-bold font-mono text-ink mt-1 block">
              {analytics.holdout_recovery_rate_pct.toFixed(1)}%
            </span>
            <span className="text-[11px] text-ink-subtle mt-0.5 block font-mono">
              {analytics.holdout_recovered.toString()} / {analytics.holdout_total.toString()} natural baseline
            </span>
          </div>

          <div className="p-3.5 rounded-control bg-surface border border-accent/40">
            <span className="text-xs text-accent font-mono block">Net Attributable Recovered Value</span>
            <span className="text-2xl font-bold font-mono text-recovered mt-1 block">
              {formatINR(analytics.net_recovered_value_paise)}
            </span>
            <span className="text-[11px] text-ink-subtle mt-0.5 block font-mono">
              Net of INR {(totalCost / 100).toFixed(0)} costs & discounts
            </span>
          </div>
        </CardContent>
      </Card>

      {/* 3. Time Series Recovery Velocity Chart */}
      <RecoveryVelocityChart timeSeries={analytics.time_series} />

      {/* 4. Financial Recovery Waterfall */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-accent" />
            <CardTitle>Revenue Recovery Waterfall</CardTitle>
          </div>
          <CardDescription>
            Step-by-step accounting: At-Risk Capital → Recovery Volume → Unit Costs → Net Recovered Value (NRV)
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 font-mono text-xs">
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-ink font-semibold">1. Total Revenue at Risk</span>
              <span className="font-bold text-ink">{formatINR(atRisk)}</span>
            </div>
            <div className="h-3 w-full rounded-full bg-surface-sunken overflow-hidden">
              <div className="h-full bg-ink/70 w-full" />
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-recovered font-semibold">2. Gross Autonomous Recovery</span>
              <span className="font-bold text-recovered">+{formatINR(recovered)}</span>
            </div>
            <div className="h-3 w-full rounded-full bg-surface-sunken overflow-hidden">
              <div
                className="h-full bg-recovered transition-all duration-500"
                style={{ width: `${recoveredWidthPct}%` }}
              />
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-failed font-semibold">3. Outreach & Gateway Fees</span>
              <span className="font-bold text-failed">-{formatINR(totalCost)}</span>
            </div>
            <div className="h-3 w-full rounded-full bg-surface-sunken overflow-hidden">
              <div
                className="h-full bg-failed transition-all duration-500"
                style={{ width: `${costWidthPct}%` }}
              />
            </div>
          </div>

          <div className="space-y-2 pt-2 border-t border-border">
            <div className="flex justify-between text-sm font-bold">
              <span className="text-recovered flex items-center gap-1.5">
                <CheckCircle2 className="h-4 w-4" />
                <span>Net Recovered Value (NRV)</span>
              </span>
              <span className="text-recovered font-mono">{formatINR(nrv)}</span>
            </div>
            <span className="text-[10px] text-ink-subtle block">
              Remaining unrecovered pipeline: {formatINR(unrecovered)}
            </span>
          </div>
        </CardContent>
      </Card>

      {/* 5. Payment Rail Efficiency & Latency Distribution */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <PaymentRailChart railPerformance={analytics.rail_performance} />
        <LatencyDistributionChart ttrBuckets={analytics.time_to_recovery_buckets} />
      </div>

      {/* 6. Root Cause Taxonomy & Policy Boundaries */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Root Cause Taxonomy Distribution</CardTitle>
            <CardDescription>
              Dynamic classification across transient windows, liquidity, and checkout drop-offs
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 font-mono text-xs">
            {analytics.category_distribution.length > 0 ? (
              analytics.category_distribution.map((item) => (
                <div key={item.category} className="space-y-1.5">
                  <div className="flex justify-between">
                    <span className="text-ink">{item.category.replace(/_/g, ' ')}</span>
                    <span className="text-ink-muted">
                      {item.count.toString()} cases ({item.percentage.toFixed(1)}%)
                    </span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-surface-sunken overflow-hidden">
                    <div
                      className="h-full bg-accent transition-all duration-500"
                      style={{ width: `${item.percentage.toString()}%` }}
                    />
                  </div>
                </div>
              ))
            ) : (
              <div className="py-8 text-center text-ink-muted">No failure category telemetry recorded.</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Dynamic Guardrail Safety Boundaries</CardTitle>
            <CardDescription>Hard invariant thresholds fetched directly from active policy configuration</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 font-mono text-xs">
            {policies ? (
              <>
                <div className="flex justify-between p-2.5 rounded-control bg-surface-sunken">
                  <span className="text-ink-muted">Dunning Frequency Cap</span>
                  <span className="text-ink font-semibold">Max {policies.max_touches.toString()} touches / transaction</span>
                </div>
                <div className="flex justify-between p-2.5 rounded-control bg-surface-sunken">
                  <span className="text-ink-muted">Mandate Retry Cooldown</span>
                  <span className="text-ink font-semibold">{policies.min_cooldown_hours.toString()} hours minimum</span>
                </div>
                <div className="flex justify-between p-2.5 rounded-control bg-surface-sunken">
                  <span className="text-ink-muted">Incentive Margin Cap</span>
                  <span className="text-ink font-semibold">{(policies.max_discount_bps / 100).toFixed(2)}% ({policies.max_discount_bps.toString()} bps) max</span>
                </div>
                <div className="flex justify-between p-2.5 rounded-control bg-surface-sunken">
                  <span className="text-ink-muted">Counterfactual Holdout Group</span>
                  <span className="text-ink font-semibold">{policies.holdout_percentage.toString()}% uncontacted control</span>
                </div>
              </>
            ) : (
              <div className="py-8 text-center text-ink-muted">Loading merchant policy invariants...</div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
