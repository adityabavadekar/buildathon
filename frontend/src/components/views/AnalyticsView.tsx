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
import { ArmComparisonChart } from '@/components/charts/ArmComparisonChart'
import { GaugeMeter } from '@/components/charts/GaugeMeter'
import { MoneyFlowBar } from '@/components/charts/MoneyFlowBar'
import { SkeletonCard } from '@/components/ui/skeleton'
import { CategoryDistributionChart } from '@/components/charts/CategoryDistributionChart'
import { CampaignAttributionChart } from '@/components/charts/CampaignAttributionChart'
import { DailyVolumeTrendsChart } from '@/components/charts/DailyVolumeTrendsChart'
import { HealthScoreCard } from '@/components/charts/HealthScoreCard'
import { LatencyDistributionChart } from '@/components/charts/LatencyDistributionChart'
import { PaymentRailChart } from '@/components/charts/PaymentRailChart'
import { RecoveryVelocityChart } from '@/components/charts/RecoveryVelocityChart'
import { formatINR } from '@/lib/format'

interface AnalyticsViewProps {
  analytics: AnalyticsSummaryResponse | null
  loading: boolean
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
          model.trained_count > 0
            ? `Forecasts updated from ${model.trained_count.toString()} completed cases.`
            : 'Not enough completed cases yet to update forecasts.',
        )
      })
      .catch((err: unknown) => {
        setTrainMessage(
          err instanceof Error
            ? `Could not update forecasts: ${err.message}`
            : 'Could not update forecasts',
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
    atRisk > 0 ? Math.min(100, (recovered / atRisk) * 100) : 0

  return (
    <div className="space-y-6">
      <p className="border-b border-border pb-4 text-sm text-ink-muted">
        Recovery performance, unit economics, and lift against the holdout
        control arm.
      </p>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="metric-tile border-recovered/30 bg-recovered-subtle/20">
          <p className="metric-tile-label text-recovered">
            Net recovered value
          </p>
          <p className="metric-tile-value money text-left text-recovered">
            {formatINR(nrv)}
          </p>
          <p className="metric-tile-hint">
            After fees, outreach, and discounts.
          </p>
        </div>
        <div className="metric-tile border-accent/30 bg-accent-subtle/30">
          <p className="metric-tile-label text-accent">Attributable lift</p>
          <p className="metric-tile-value text-accent">
            +{analytics.attributable_lift_pct.toFixed(1)}%
          </p>
          <p className="metric-tile-hint">Treatment vs holdout baseline.</p>
        </div>
        <div className="metric-tile">
          <p className="metric-tile-label">Recovery rate</p>
          <p className="metric-tile-value">
            {analytics.overall_recovery_rate_pct.toFixed(1)}%
          </p>
          <p className="metric-tile-hint">
            {analytics.treatment_recovered.toString()} payments recovered.
          </p>
        </div>
        <div className="metric-tile">
          <p className="metric-tile-label">Revenue at risk</p>
          <p className="metric-tile-value money text-left">
            {formatINR(atRisk)}
          </p>
          <p className="metric-tile-hint">
            {formatINR(unrecovered)} still unrecovered.
          </p>
        </div>
      </div>

      <Card className="border-accent/30 bg-accent-subtle/10">
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-accent" />
            <CardTitle className="text-base">
              <GlossaryTerm termKey="HOLDOUT_ARM" showIcon={false}>
                Treatment vs holdout
              </GlossaryTerm>
            </CardTitle>
          </div>
          <CardDescription>
            The engine recovered{' '}
            <strong className="text-recovered">
              +{analytics.attributable_lift_pct.toFixed(1)}%
            </strong>{' '}
            more than the uncontacted holdout cohort.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <ArmComparisonChart
            liftPct={analytics.attributable_lift_pct}
            arms={[
              {
                key: 'treatment',
                label: 'Treatment cohort',
                ratePct: analytics.treatment_recovery_rate_pct,
                caseCount: analytics.treatment_total,
                color: 'var(--color-recovered)',
                sublabel: 'Contacted by the recovery engine',
              },
              {
                key: 'holdout',
                label: 'Holdout control',
                ratePct: analytics.holdout_recovery_rate_pct,
                caseCount: analytics.holdout_total,
                color: 'var(--color-ink-subtle)',
                sublabel: 'Deliberately uncontacted counterfactual',
              },
            ]}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
            <div>
              <CardTitle className="text-base">
                <GlossaryTerm termKey="RECOVERED_NRV">
                  Net recovered value breakdown
                </GlossaryTerm>
              </CardTitle>
              <CardDescription className="mt-1">
                Gross captured minus gateway fees, outreach costs, and
                discounts.
              </CardDescription>
            </div>
            <div className="rounded-panel border border-recovered/30 bg-recovered-subtle/30 px-4 py-2 text-right">
              <p className="text-xs text-ink-muted">Net yield</p>
              <p className="money text-2xl font-bold text-recovered">
                {formatINR(nrv)}
              </p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <div className="metric-tile">
              <p className="metric-tile-label">Gross at risk</p>
              <p className="metric-tile-value money text-left">
                {formatINR(atRisk)}
              </p>
            </div>
            <div className="metric-tile border-recovered/30 bg-recovered-subtle/20">
              <p className="metric-tile-label text-recovered">Gross captured</p>
              <p className="metric-tile-value money text-left text-recovered">
                {formatINR(recovered)}
              </p>
            </div>
            <div className="metric-tile border-failed/30 bg-failed-subtle/20">
              <p className="metric-tile-label text-failed">Total cost</p>
              <p className="metric-tile-value money text-left text-failed">
                -{formatINR(totalCost)}
              </p>
            </div>
            <div className="metric-tile border-accent/30 bg-accent-subtle/20">
              <p className="metric-tile-label text-accent">Capture rate</p>
              <p className="metric-tile-value text-accent">
                {recoveredWidthPct.toFixed(1)}%
              </p>
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-xs text-ink-muted">
              Where the at-risk revenue went. Net yield is what remains after
              the cost of recovering it.
            </p>
            <MoneyFlowBar
              totalPaise={atRisk}
              segments={[
                {
                  key: 'net',
                  label: 'Net recovered',
                  amountPaise: Math.max(0, nrv),
                  color: 'var(--color-recovered)',
                },
                {
                  key: 'fees',
                  label: 'Gateway fees',
                  amountPaise: analytics.total_gateway_fees_paise,
                  color: 'var(--color-escalated)',
                },
                {
                  key: 'outreach',
                  label: 'Outreach cost',
                  amountPaise: analytics.total_communication_cost_paise,
                  color: 'var(--color-pending)',
                },
                {
                  key: 'discounts',
                  label: 'Discounts granted',
                  amountPaise: analytics.total_discounts_granted_paise,
                  color: 'var(--color-failed)',
                },
              ]}
            />
          </div>

          <div className="grid grid-cols-1 gap-3 border-t border-border pt-3 sm:grid-cols-3">
            <div className="metric-tile">
              <p className="metric-tile-label">Gateway fees</p>
              <p className="money text-lg font-semibold text-ink">
                -{formatINR(analytics.total_gateway_fees_paise)}
              </p>
            </div>
            <div className="metric-tile">
              <p className="metric-tile-label">Outreach costs</p>
              <p className="money text-lg font-semibold text-ink">
                -{formatINR(analytics.total_communication_cost_paise)}
              </p>
            </div>
            <div className="metric-tile">
              <p className="metric-tile-label">Discounts granted</p>
              <p className="money text-lg font-semibold text-ink">
                -{formatINR(analytics.total_discounts_granted_paise)}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      <DailyVolumeTrendsChart
        dailyMetrics={analytics.daily_metrics}
        monthlyMetrics={analytics.monthly_metrics}
      />

      <CampaignAttributionChart campaigns={analytics.campaign_metrics} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <RecoveryVelocityChart timeSeries={analytics.time_series} />
        <CategoryDistributionChart
          categories={analytics.category_distribution}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <PaymentRailChart railPerformance={analytics.rail_performance} />
        </div>
        <LatencyDistributionChart
          ttrBuckets={analytics.time_to_recovery_buckets}
        />
      </div>

      <HealthScoreCard
        healthScore={analytics.health_score}
        healthScoreAvailable={analytics.health_score_available}
        returnOnSpend={analytics.return_on_recovery_spend}
      />

      <Card>
        <CardHeader>
          <CardTitle>Recovery model</CardTitle>
          <CardDescription>
            Likelihood and expected value forecasts for open cases.
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
              </div>

              <div className="grid gap-4 rounded-panel border border-border p-4 sm:grid-cols-2">
                <GaugeMeter
                  label="Prediction accuracy"
                  value={metricValue(recoveryModel.holdout_metrics, 'accuracy')}
                  hint="How often the forecast was right on cases it had never seen."
                />
                <GaugeMeter
                  label="Confidence in ranking"
                  value={metricValue(recoveryModel.cv_metrics, 'mean_auc')}
                  hint="How reliably it separates cases that recover from those that do not."
                  warnBelow={0.7}
                  criticalBelow={0.6}
                />
              </div>
            </div>
          ) : (
            <p className="text-sm text-ink-muted">
              No recovery model trained yet.
            </p>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="secondary"
              onClick={handleTrain}
              disabled={training}
            >
              <BrainCircuit className="h-4 w-4" />
              {training ? 'Training...' : 'Train model'}
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
          <CardTitle>Recovery patterns</CardTitle>
          <CardDescription>
            Descriptive clusters only. They do not change policy decisions.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {patterns.map((pattern) => (
            <div
              key={pattern.alert_id}
              className="rounded-panel border border-border p-3 text-sm"
            >
              <div className="flex flex-wrap justify-between gap-2">
                <span className="font-medium text-ink">
                  {pattern.dominant_category}
                </span>
                <span className="text-ink-muted">
                  {pattern.dominant_intervention}
                </span>
              </div>
              <p className="mt-1 text-xs text-ink-muted">
                {pattern.member_count.toString()} cases · mean{' '}
                {formatINR(pattern.mean_amount_paise, {
                  maximumFractionDigits: 2,
                })}
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {pattern.example_case_ids.map((caseId) => (
                  <Link
                    key={caseId}
                    href={`/recovery?case_id=${encodeURIComponent(caseId)}`}
                    className="text-xs font-medium text-accent"
                  >
                    {caseId}
                  </Link>
                ))}
              </div>
            </div>
          ))}
          {patterns.length === 0 ? (
            <p className="text-sm text-ink-muted">
              No persisted pattern alerts are available.
            </p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}
