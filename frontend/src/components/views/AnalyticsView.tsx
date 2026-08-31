'use client'

import React, { useEffect, useState } from 'react'
import Link from 'next/link'
import { BrainCircuit, TrendingUp } from 'lucide-react'
import {
  getPatternAlerts,
  getRecoveryModel,
  trainRecoveryModel,
  type AnalyticsSummaryResponse,
  type PatternAlert,
  type PolicyResponse,
  type RecoveryModelStatus,
} from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { GlossaryTerm } from '@/components/ui/GlossaryTerm'
import { MetricBar } from '@/components/ui/MetricBar'
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

function metricValue(
  metrics: Record<string, unknown> | null | undefined,
  key: string,
): number {
  const raw = metrics?.[key]
  return typeof raw === 'number' ? raw : 0
}

export function AnalyticsView({ analytics, loading }: AnalyticsViewProps) {
  const [patterns, setPatterns] = useState<PatternAlert[]>([])
  const [recoveryModel, setRecoveryModel] =
    useState<RecoveryModelStatus | null>(null)
  const [trainMessage, setTrainMessage] = useState<string | null>(null)
  const [training, setTraining] = useState(false)
  const loadRecoveryModel = () => {
    void getRecoveryModel()
      .then((model) => {
        setRecoveryModel(model)
        setTrainMessage(null)
      })
      .catch(() => {
        setRecoveryModel(null)
        setTrainMessage('Unable to load model status.')
      })
  }
  const handleTrain = () => {
    setTraining(true)
    setTrainMessage(null)
    void trainRecoveryModel()
      .then((model) => {
        setRecoveryModel(model)
        setTrainMessage(
          `Retrained ${model.version} on ${model.trained_count.toString()} treatment cases.`,
        )
      })
      .catch((err: unknown) => {
        setTrainMessage(
          err instanceof Error
            ? `Train failed: ${err.message}`
            : 'Train failed',
        )
      })
      .finally(() => {
        setTraining(false)
      })
  }
  useEffect(() => {
    void getPatternAlerts()
      .then(setPatterns)
      .catch(() => {
        setPatterns([])
      })
    loadRecoveryModel()
  }, [])
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
        <h1 className="font-mono text-2xl font-bold text-ink">
          Recovery Economics & Analytics
        </h1>
        <p className="mt-0.5 text-sm text-ink-muted">
          Detailed unit economics, net recovered value (NRV) accounting, and
          counterfactual lift measured against the 10% holdout control group.
        </p>
      </div>

      {/* Counterfactual Lift Banner (A/B Test Holdout Analysis) */}
      <div className="flex flex-col justify-between gap-4 rounded-panel border border-accent/40 bg-accent/5 p-5 md:flex-row md:items-center">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-accent" />
            <span className="font-mono text-sm font-bold tracking-wider text-ink uppercase">
              <GlossaryTerm termKey="HOLDOUT_ARM" showIcon={false}>
                A/B Counterfactual Recovery Lift
              </GlossaryTerm>
            </span>
          </div>
          <p className="text-sm leading-relaxed text-ink-muted">
            The AI engine recovered{' '}
            <strong className="font-mono text-base text-recovered">
              +{analytics.attributable_lift_pct.toFixed(1)}%
            </strong>{' '}
            more revenue compared to the natural baseline recovery of
            uncontacted holdout cases.
          </p>
        </div>

        <div className="flex items-center gap-6 border-t border-border pt-3 font-mono md:border-t-0 md:border-l md:pt-0 md:pl-6">
          <div>
            <span className="block text-xs text-ink-muted">
              <GlossaryTerm termKey="TREATMENT_ARM" showIcon={false}>
                Treatment Cohort
              </GlossaryTerm>
            </span>
            <span className="text-2xl font-bold text-ink">
              {analytics.treatment_recovery_rate_pct.toFixed(1)}%
            </span>
            <span className="block text-xs text-ink-subtle">
              ({analytics.treatment_total.toString()} cases)
            </span>
          </div>

          <div className="hidden h-10 w-px bg-border sm:block" />

          <div>
            <span className="block text-xs text-ink-muted">
              <GlossaryTerm termKey="HOLDOUT_ARM" showIcon={false}>
                Holdout Control (10%)
              </GlossaryTerm>
            </span>
            <span className="text-2xl font-bold text-ink-muted">
              {analytics.holdout_recovery_rate_pct.toFixed(1)}%
            </span>
            <span className="block text-xs text-ink-subtle">
              ({analytics.holdout_total.toString()} uncontacted)
            </span>
          </div>
        </div>
      </div>

      {/* Net Recovered Value (NRV) Accounting Card */}
      <Card>
        <CardHeader className="p-5 pb-3">
          <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
            <div>
              <CardTitle className="text-lg">
                <GlossaryTerm termKey="RECOVERED_NRV">
                  Net Recovered Value (NRV) Accounting
                </GlossaryTerm>
              </CardTitle>
              <CardDescription className="mt-0.5 text-xs">
                NRV = Gross Recovered - (Gateway Retry Fees + Communication
                Costs + Discounts Granted)
              </CardDescription>
            </div>
            <div className="self-start rounded-control border border-recovered/30 bg-recovered/10 p-3 sm:self-auto">
              <span className="block font-mono text-xs text-ink-muted">
                Net Yield (NRV)
              </span>
              <span className="font-mono text-2xl font-bold text-recovered sm:text-3xl">
                {formatINR(nrv)}
              </span>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-5 p-5 pt-0">
          {/* 4 Big High-Visibility Financial Numbers */}
          <div className="grid grid-cols-2 gap-4 font-mono sm:grid-cols-4">
            <div className="rounded-control border border-border bg-surface-sunken p-4">
              <span className="block text-xs font-semibold text-ink-muted">
                Gross At Risk
              </span>
              <span className="mt-1 block text-2xl font-bold text-ink">
                {formatINR(atRisk)}
              </span>
            </div>
            <div className="rounded-control border border-recovered/30 bg-recovered/10 p-4">
              <span className="block text-xs font-semibold text-recovered">
                Gross Captured
              </span>
              <span className="mt-1 block text-2xl font-bold text-recovered">
                {formatINR(recovered)}
              </span>
            </div>
            <div className="rounded-control border border-failed/30 bg-failed/10 p-4">
              <span className="block text-xs font-semibold text-failed">
                Total Incurred Cost
              </span>
              <span className="mt-1 block text-2xl font-bold text-failed">
                -{formatINR(totalCost)}
              </span>
            </div>
            <div className="rounded-control border border-accent/30 bg-accent/10 p-4">
              <span className="block text-xs font-semibold text-accent">
                Recovery Yield
              </span>
              <span className="mt-1 block text-2xl font-bold text-accent">
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
              <span className="font-semibold text-recovered">
                Gross Captured: {formatINR(recovered)} ({recoveredWidthPct}%)
              </span>
            </div>
            <div className="flex h-3.5 w-full overflow-hidden rounded-full bg-surface-sunken">
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
          <div className="grid grid-cols-2 gap-3 border-t border-border pt-2 font-mono text-xs sm:grid-cols-4">
            <div className="rounded-control border border-border bg-surface-sunken p-3.5">
              <span className="block text-xs text-ink-muted">
                Gateway Retry Fees
              </span>
              <span className="mt-0.5 block text-base font-bold text-ink">
                -{formatINR(analytics.total_gateway_fees_paise)}
              </span>
            </div>
            <div className="rounded-control border border-border bg-surface-sunken p-3.5">
              <span className="block text-xs text-ink-muted">
                Outreach Costs
              </span>
              <span className="mt-0.5 block text-base font-bold text-ink">
                -{formatINR(analytics.total_communication_cost_paise)}
              </span>
            </div>
            <div className="rounded-control border border-border bg-surface-sunken p-3.5">
              <span className="block text-xs text-ink-muted">
                Discounts Granted
              </span>
              <span className="mt-0.5 block text-base font-bold text-ink">
                -{formatINR(analytics.total_discounts_granted_paise)}
              </span>
            </div>
            <div className="rounded-control border border-failed/40 bg-surface-sunken p-3.5">
              <span className="block text-xs font-semibold text-failed">
                Total Cost Incurred
              </span>
              <span className="mt-0.5 block text-base font-bold text-failed">
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
        <CategoryDistributionChart
          categories={analytics.category_distribution}
        />
      </div>

      {/* 3. Latency & Rail Distribution */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <PaymentRailChart railPerformance={analytics.rail_performance} />
        </div>
        <LatencyDistributionChart
          ttrBuckets={analytics.time_to_recovery_buckets}
        />
      </div>

      {/* 4. Engine Health & Efficiency */}
      <div className="grid grid-cols-1 gap-6">
        <HealthScoreCard
          healthScore={analytics.health_score}
          returnOnSpend={analytics.return_on_recovery_spend}
          recoveryStreak={analytics.recovery_streak}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recovery Model</CardTitle>
          <CardDescription>
            How likely each pending case is to recover, and how much money is at
            stake. The numbers below show how accurately the model has predicted
            past outcomes.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {recoveryModel ? (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge
                  variant={
                    recoveryModel.trained_count > 0 ? 'recovered' : 'default'
                  }
                >
                  {recoveryModel.status}
                </Badge>
                <span className="font-mono text-sm text-ink">
                  {recoveryModel.version}
                </span>
                <span className="text-xs text-ink-muted">
                  {recoveryModel.trained_count.toString()} training cases
                </span>
              </div>

              <div className="space-y-3 rounded-control border border-border p-3">
                <p className="font-mono text-[11px] tracking-wider text-ink-muted uppercase">
                  Accuracy on past cases
                </p>
                <MetricBar
                  label="Cross-validated accuracy"
                  value={metricValue(recoveryModel.cv_metrics, 'mean_accuracy')}
                  hint="How often the model's recovery prediction was right on the training data, checked several ways."
                />
                <MetricBar
                  label="Cross-validated precision (AUC)"
                  value={metricValue(recoveryModel.cv_metrics, 'mean_auc')}
                  hint="How well the model separates cases that recover from ones that don't."
                />
                <MetricBar
                  label="Accuracy on untouched cases"
                  value={metricValue(recoveryModel.holdout_metrics, 'accuracy')}
                  hint="Accuracy on a test group the model never trained on, so the number is honest."
                />
              </div>

              <div className="space-y-2 rounded-control border border-border p-3">
                <p className="font-mono text-[11px] tracking-wider text-ink-muted uppercase">
                  What it predicts per case
                </p>
                <div className="flex flex-wrap items-center gap-1.5">
                  {recoveryModel.expected_outputs &&
                  recoveryModel.expected_outputs.length > 0 ? (
                    recoveryModel.expected_outputs.map((output) => (
                      <span
                        key={output}
                        className="rounded-full border border-border px-2 py-0.5 font-mono text-[10px] text-ink-muted"
                      >
                        {output}
                      </span>
                    ))
                  ) : (
                    <span className="text-xs text-ink-muted">
                      Waiting for trained data.
                    </span>
                  )}
                </div>
                <p className="text-[11px] text-ink-subtle">
                  Likelihood of recovery, expected money recoverable, and days
                  to recovery for each open case.
                </p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-ink-muted">
              No recovery model trained yet. Train it to see live recovery
              estimates.
            </p>
          )}
          <div className="flex items-center gap-3">
            <Button
              variant="secondary"
              onClick={handleTrain}
              disabled={training}
            >
              <BrainCircuit className="h-4 w-4" />
              {training ? 'Training...' : 'Train Model'}
            </Button>
            <Button variant="ghost" onClick={loadRecoveryModel}>
              Refresh
            </Button>
            {trainMessage ? (
              <span className="text-sm text-ink-muted">{trainMessage}</span>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recovery Patterns</CardTitle>
          <CardDescription>
            Descriptive clusters only. They do not change policy or recovery
            decisions.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {patterns.map((pattern) => (
            <div
              key={pattern.alert_id}
              className="rounded-control border border-border p-3 text-sm"
            >
              <div className="flex flex-wrap justify-between gap-2 font-mono text-ink">
                <span>{pattern.dominant_category}</span>
                <span>{pattern.dominant_intervention}</span>
              </div>
              <p className="mt-1 text-xs text-ink-muted">
                {pattern.member_count.toString()} cases | Mean INR{' '}
                {(pattern.mean_amount_paise / 100).toFixed(2)}
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {pattern.example_case_ids.map((caseId) => (
                  <Link
                    key={caseId}
                    href={`/recovery?case_id=${encodeURIComponent(caseId)}`}
                    className="font-mono text-xs text-accent"
                  >
                    {caseId}
                  </Link>
                ))}
              </div>
            </div>
          ))}
          {patterns.length === 0 && (
            <p className="text-sm text-ink-muted">
              No persisted pattern alerts are available.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
