'use client'

import React from 'react'
import {
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
import { GlossaryTerm } from '@/components/ui/GlossaryTerm'
import { SkeletonCard } from '@/components/ui/skeleton'
import { CategoryDistributionChart } from '@/components/charts/CategoryDistributionChart'
import { DailyVolumeTrendsChart } from '@/components/charts/DailyVolumeTrendsChart'
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

export function AnalyticsView({ analytics, loading }: AnalyticsViewProps) {
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
    atRisk > 0 ? ((recovered / atRisk) * 100).toFixed(1) : '0.0'
  const unrecoveredWidthPct =
    atRisk > 0 ? ((unrecovered / atRisk) * 100).toFixed(1) : '0.0'

  return (
    <div className="space-y-6">
      {/* View Header with Plain-Language Context */}
      <div className="border-b border-border pb-4">
        <h1 className="text-2xl font-bold font-mono text-ink">
          Recovery Economics & Analytics
        </h1>
        <p className="text-sm text-ink-muted mt-0.5">
          Detailed unit economics, net recovered value (NRV) accounting, and counterfactual lift measured against the 10% holdout control group.
        </p>
      </div>

      {/* Counterfactual Lift Banner (A/B Test Holdout Analysis) */}
      <div className="rounded-panel border border-accent/40 bg-accent/5 p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-accent" />
            <span className="font-mono text-sm font-bold text-ink uppercase tracking-wider">
              <GlossaryTerm termKey="HOLDOUT_ARM" showIcon={false}>
                A/B Counterfactual Recovery Lift
              </GlossaryTerm>
            </span>
          </div>
          <p className="text-sm text-ink-muted leading-relaxed">
            The AI engine recovered <strong className="text-recovered font-mono text-base">+{analytics.attributable_lift_pct.toFixed(1)}%</strong> more revenue compared to the natural baseline recovery of uncontacted holdout cases.
          </p>
        </div>

        <div className="flex items-center gap-6 font-mono border-t md:border-t-0 md:border-l border-border pt-3 md:pt-0 md:pl-6">
          <div>
            <span className="text-ink-muted block text-xs">
              <GlossaryTerm termKey="TREATMENT_ARM" showIcon={false}>
                Treatment Cohort
              </GlossaryTerm>
            </span>
            <span className="text-2xl font-bold text-ink">
              {analytics.treatment_recovery_rate_pct.toFixed(1)}%
            </span>
            <span className="text-xs text-ink-subtle block">
              ({analytics.treatment_total.toString()} cases)
            </span>
          </div>

          <div className="h-10 w-px bg-border hidden sm:block" />

          <div>
            <span className="text-ink-muted block text-xs">
              <GlossaryTerm termKey="HOLDOUT_ARM" showIcon={false}>
                Holdout Control (10%)
              </GlossaryTerm>
            </span>
            <span className="text-2xl font-bold text-ink-muted">
              {analytics.holdout_recovery_rate_pct.toFixed(1)}%
            </span>
            <span className="text-xs text-ink-subtle block">
              ({analytics.holdout_total.toString()} uncontacted)
            </span>
          </div>
        </div>
      </div>

      {/* Net Recovered Value (NRV) Accounting Card */}
      <Card>
        <CardHeader className="p-5 pb-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <CardTitle className="text-lg">
                <GlossaryTerm termKey="RECOVERED_NRV">
                  Net Recovered Value (NRV) Accounting
                </GlossaryTerm>
              </CardTitle>
              <CardDescription className="text-xs mt-0.5">
                NRV = Gross Recovered - (Gateway Retry Fees + Communication Costs + Discounts Granted)
              </CardDescription>
            </div>
            <div className="p-3 rounded-control bg-recovered/10 border border-recovered/30 self-start sm:self-auto">
              <span className="text-xs text-ink-muted block font-mono">Net Yield (NRV)</span>
              <span className="text-2xl sm:text-3xl font-mono font-bold text-recovered">
                {formatINR(nrv)}
              </span>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-5 pt-0 space-y-5">
          {/* 4 Big High-Visibility Financial Numbers */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 font-mono">
            <div className="p-4 rounded-control bg-surface-sunken border border-border">
              <span className="text-xs text-ink-muted block font-semibold">Gross At Risk</span>
              <span className="text-2xl font-bold text-ink mt-1 block">
                {formatINR(atRisk)}
              </span>
            </div>
            <div className="p-4 rounded-control bg-recovered/10 border border-recovered/30">
              <span className="text-xs text-recovered block font-semibold">Gross Captured</span>
              <span className="text-2xl font-bold text-recovered mt-1 block">
                {formatINR(recovered)}
              </span>
            </div>
            <div className="p-4 rounded-control bg-failed/10 border border-failed/30">
              <span className="text-xs text-failed block font-semibold">Total Incurred Cost</span>
              <span className="text-2xl font-bold text-failed mt-1 block">
                -{formatINR(totalCost)}
              </span>
            </div>
            <div className="p-4 rounded-control bg-accent/10 border border-accent/30">
              <span className="text-xs text-accent block font-semibold">Recovery Yield</span>
              <span className="text-2xl font-bold text-accent mt-1 block">
                {recoveredWidthPct}%
              </span>
            </div>
          </div>

          {/* Recovery Ratio Visual Bar */}
          <div className="space-y-2 font-mono text-xs">
            <div className="flex justify-between">
              <span className="text-ink-muted">
                Gross Ingested: {formatINR(atRisk)}
              </span>
              <span className="text-recovered font-semibold">
                Gross Captured: {formatINR(recovered)} ({recoveredWidthPct}%)
              </span>
            </div>
            <div className="flex h-3.5 w-full rounded-full bg-surface-sunken overflow-hidden">
              <div
                className="bg-recovered transition-all duration-500"
                style={{ width: `${recoveredWidthPct}%` }}
                title={`Recovered: ${formatINR(recovered)}`}
              />
              <div
                className="bg-border transition-all duration-500"
                style={{ width: `${unrecoveredWidthPct}%` }}
                title={`Unrecovered: ${formatINR(unrecovered)}`}
              />
            </div>
          </div>

          {/* Deductions Breakdown */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 font-mono text-xs border-t border-border">
            <div className="p-3.5 rounded-control bg-surface-sunken border border-border">
              <span className="text-xs text-ink-muted block">Gateway Retry Fees</span>
              <span className="text-base font-bold text-ink mt-0.5 block">
                -{formatINR(analytics.total_gateway_fees_paise)}
              </span>
            </div>
            <div className="p-3.5 rounded-control bg-surface-sunken border border-border">
              <span className="text-xs text-ink-muted block">Outreach Costs</span>
              <span className="text-base font-bold text-ink mt-0.5 block">
                -{formatINR(analytics.total_communication_cost_paise)}
              </span>
            </div>
            <div className="p-3.5 rounded-control bg-surface-sunken border border-border">
              <span className="text-xs text-ink-muted block">Discounts Granted</span>
              <span className="text-base font-bold text-ink mt-0.5 block">
                -{formatINR(analytics.total_discounts_granted_paise)}
              </span>
            </div>
            <div className="p-3.5 rounded-control bg-surface-sunken border border-failed/40">
              <span className="text-xs text-failed block font-semibold">Total Cost Incurred</span>
              <span className="text-base font-bold text-failed mt-0.5 block">
                -{formatINR(totalCost)}
              </span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 1. Daily & Monthly Volume Trends Chart */}
      <DailyVolumeTrendsChart
        dailyMetrics={analytics.daily_metrics}
        monthlyMetrics={analytics.monthly_metrics}
      />

      {/* 2. Visual Analytics Charts Grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <RecoveryVelocityChart timeSeries={analytics.time_series} />
        <CategoryDistributionChart categories={analytics.category_distribution} />
      </div>

      {/* 3. Latency & Rail Distribution */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <PaymentRailChart railPerformance={analytics.rail_performance} />
        </div>
        <LatencyDistributionChart ttrBuckets={analytics.time_to_recovery_buckets} />
      </div>

      {/* 4. Engine Health & Efficiency */}
      <div className="grid grid-cols-1 gap-6">
        <HealthScoreCard
          healthScore={analytics.health_score}
          returnOnSpend={analytics.return_on_recovery_spend}
          recoveryStreak={analytics.recovery_streak}
        />
      </div>
    </div>
  )
}
