'use client'

import React, { useEffect, useState } from 'react'
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  RotateCcw,
  ShieldAlert,
  Tag,
  TrendingUp,
} from 'lucide-react'
import {
  getOperatorMode,
  type AnalyticsSummaryResponse,
  type OperatorAutonomyMode,
  type RecoveryCase,
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
import { RailBadge } from '@/components/ui/BrandIcons'
import { StatCard } from '@/components/ui/StatCard'
import { RecoveryLifecycleStrip } from '@/components/recovery/RecoveryLifecycleStrip'
import { SkeletonCard, SkeletonRow } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { LatencyDistributionChart } from '@/components/charts/LatencyDistributionChart'
import { PaymentRailChart } from '@/components/charts/PaymentRailChart'
import { RecoveryVelocityChart } from '@/components/charts/RecoveryVelocityChart'
import { HealthScoreCard } from '@/components/charts/HealthScoreCard'
import { formatINR, humanizeToken } from '@/lib/format'
import { AUTONOMY_MODE_COPY, OPEN_CASE_STATES } from '@/lib/constants'
import type { NavSection } from '@/components/layout/Sidebar'

interface OverviewViewProps {
  cases: RecoveryCase[]
  analytics: AnalyticsSummaryResponse | null
  loading: boolean
  onSelectCase: (c: RecoveryCase) => void
  onNavigateToRecovery: (subTab?: string) => void
  onNavigateToSection?: (section: NavSection) => void
}

export function OverviewView({
  cases,
  analytics,
  loading,
  onSelectCase,
  onNavigateToRecovery,
  onNavigateToSection,
}: OverviewViewProps) {
  const [autonomyMode, setAutonomyMode] = useState<OperatorAutonomyMode | null>(
    null,
  )

  useEffect(() => {
    let mounted = true
    getOperatorMode()
      .then((state) => {
        if (mounted) setAutonomyMode(state.mode)
      })
      .catch(() => null)
    return () => {
      mounted = false
    }
  }, [])

  const totalRecoveredPaise = analytics
    ? analytics.recovered_amount_paise
    : cases
        .filter((c) => c.state === 'RECOVERED')
        .reduce(
          (acc, c) => acc + (c.recovered_amount_paise || c.amount_paise),
          0,
        )
  const totalNrvPaise = analytics
    ? analytics.net_recovered_value_paise
    : totalRecoveredPaise
  const attributableLiftPct = analytics?.attributable_lift_pct ?? 0
  const holdoutTotal = analytics?.holdout_total ?? 0
  // Only cases still being worked: total at-risk includes resolved ones, which is
  // not money the merchant can still act on.
  const openAtRiskPaise = cases
    .filter((c) => OPEN_CASE_STATES.some((s) => s === c.state))
    .reduce((acc, c) => acc + c.amount_paise, 0)

  const recoveredCasesCount = cases.filter(
    (c) => c.state === 'RECOVERED',
  ).length

  const activeCount =
    analytics?.active_cases !== undefined
      ? analytics.active_cases
      : cases.filter((c) => OPEN_CASE_STATES.some((s) => s === c.state)).length
  const escalatedCount =
    analytics?.escalated_cases !== undefined
      ? analytics.escalated_cases
      : cases.filter((c) => c.state === 'ESCALATED').length
  const recoveredCount =
    analytics?.recovered_cases !== undefined
      ? analytics.recovered_cases
      : recoveredCasesCount

  return (
    <div className="space-y-6">
      {autonomyMode && autonomyMode !== 'FULL_AUTONOMY' ? (
        <div
          className={`flex flex-col gap-1 rounded-panel border p-4 ${
            autonomyMode === 'MONITORING_ONLY'
              ? 'border-failed/50 bg-failed/10'
              : 'border-pending/50 bg-pending/10'
          }`}
        >
          <div className="flex items-center gap-2">
            <ShieldAlert
              className={`h-4 w-4 ${
                autonomyMode === 'MONITORING_ONLY'
                  ? 'text-failed'
                  : 'text-pending'
              }`}
            />
            <span className="text-sm font-semibold text-ink">
              {autonomyMode === 'MONITORING_ONLY'
                ? 'Recovery is paused'
                : 'Every action needs your approval'}
            </span>
          </div>
          <p className="text-sm text-ink-muted">
            {AUTONOMY_MODE_COPY[autonomyMode].effect}
          </p>
        </div>
      ) : null}

      {/* View Header with Plain-Language Context */}
      <div className="flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">
            Revenue Recovery Control Center
          </h1>
          <p className="mt-1 text-sm text-ink-muted">
            Autonomous intervention lifecycle for failed payments, abandoned
            checkouts, and overdue receivables.
          </p>
        </div>
      </div>

      {/* Guided 4-Step Recovery Lifecycle Strip */}
      <RecoveryLifecycleStrip
        cases={cases}
        onStepClick={(idx) => {
          if (idx === 0) onNavigateToRecovery('AT_RISK')
          else if (idx === 1) onNavigateToRecovery('ALL')
          else if (idx === 2) onNavigateToRecovery('ACTIVE')
          else if (idx === 3) onNavigateToRecovery('RECOVERED')
        }}
      />

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {loading ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : (
          <>
            <StatCard
              title={
                <GlossaryTerm termKey="RECOVERED_NRV">
                  Net recovered
                </GlossaryTerm>
              }
              value={formatINR(totalNrvPaise)}
              subtitle={`Gross ${formatINR(totalRecoveredPaise)}, after retry and outreach cost`}
              icon={<CheckCircle2 className="h-4 w-4 text-recovered" />}
              variant="recovered"
            />

            <StatCard
              title={
                <GlossaryTerm termKey="HOLDOUT_ARM">
                  Lift vs holdout
                </GlossaryTerm>
              }
              value={`+${attributableLiftPct.toFixed(1)}%`}
              subtitle={`Measured against ${holdoutTotal.toString()} uncontacted control cases`}
              icon={<TrendingUp className="h-4 w-4 text-accent" />}
              variant="accent"
            />

            <StatCard
              title={
                <GlossaryTerm termKey="HUMAN_IN_THE_LOOP">
                  Awaiting your signoff
                </GlossaryTerm>
              }
              value={escalatedCount.toString()}
              subtitle={
                escalatedCount > 0
                  ? 'Recovery is paused on these until you decide'
                  : 'Nothing waiting on you'
              }
              icon={
                <ShieldAlert
                  className={`h-4 w-4 ${escalatedCount > 0 ? 'text-escalated' : 'text-ink-muted'}`}
                />
              }
              variant={escalatedCount > 0 ? 'escalated' : 'default'}
            />

            <StatCard
              title={
                <GlossaryTerm termKey="AT_RISK_REVENUE">
                  Still at risk
                </GlossaryTerm>
              }
              value={formatINR(openAtRiskPaise)}
              subtitle={`${activeCount.toString()} cases still being worked`}
              icon={<AlertTriangle className="h-4 w-4 text-failed" />}
              variant="default"
            />
          </>
        )}
      </section>

      {/* Operations Quick Action Cards Grid */}
      <section className="grid grid-cols-1 gap-6 md:grid-cols-3">
        <Card
          className="cursor-pointer transition-colors hover:border-accent/40"
          onClick={() => {
            onNavigateToRecovery('ACTIVE')
          }}
        >
          <CardHeader className="p-4 pb-2 sm:p-5">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold text-ink">
                In-Flight Queue
              </CardTitle>
              <RotateCcw className="h-4 w-4 text-accent" />
            </div>
            <CardDescription className="text-xs text-ink-muted">
              Active dunning sequences & scheduled smart retries
            </CardDescription>
          </CardHeader>
          <CardContent className="p-4 pt-0 sm:p-5">
            <div className="mt-2 flex items-baseline justify-between">
              <span className="text-2xl font-bold text-ink">
                {activeCount.toString()}
              </span>
              <span className="flex items-center gap-1 text-xs text-accent">
                View Queue <ArrowRight className="h-3 w-3" />
              </span>
            </div>
          </CardContent>
        </Card>

        <Card
          className={`cursor-pointer transition-colors ${
            escalatedCount > 0
              ? 'border-escalated/50 bg-escalated-subtle/20 hover:border-escalated'
              : 'hover:border-border-strong'
          }`}
          onClick={() => {
            onNavigateToRecovery('ESCALATED')
          }}
        >
          <CardHeader className="p-4 pb-2 sm:p-5">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold text-ink">
                Manual Approvals
              </CardTitle>
              <ShieldAlert className="h-4 w-4 text-escalated" />
            </div>
            <CardDescription className="text-xs text-ink-muted">
              Cases escalated by deterministic guardrails
            </CardDescription>
          </CardHeader>
          <CardContent className="p-4 pt-0 sm:p-5">
            <div className="mt-2 flex items-baseline justify-between">
              <span
                className={`text-2xl font-bold ${escalatedCount > 0 ? 'text-escalated' : 'text-ink'}`}
              >
                {escalatedCount.toString()}
              </span>
              <span className="flex items-center gap-1 text-xs text-escalated">
                Review Cases <ArrowRight className="h-3 w-3" />
              </span>
            </div>
          </CardContent>
        </Card>

        <Card
          className="cursor-pointer transition-colors hover:border-recovered/40"
          onClick={() => {
            onNavigateToRecovery('RECOVERED')
          }}
        >
          <CardHeader className="p-4 pb-2 sm:p-5">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold text-ink">
                Recovered Volume
              </CardTitle>
              <CheckCircle2 className="h-4 w-4 text-recovered" />
            </div>
            <CardDescription className="text-xs text-ink-muted">
              Successfully completed revenue recoveries
            </CardDescription>
          </CardHeader>
          <CardContent className="p-4 pt-0 sm:p-5">
            <div className="mt-2 flex items-baseline justify-between">
              <span className="text-2xl font-bold text-recovered">
                {recoveredCount.toString()}
              </span>
              <span className="flex items-center gap-1 text-xs text-recovered">
                View Ledger <ArrowRight className="h-3 w-3" />
              </span>
            </div>
          </CardContent>
        </Card>
      </section>

      {/* Visual Analytics Charts Grid */}
      {analytics && (
        <section className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <RecoveryVelocityChart timeSeries={analytics.time_series} />
          <LatencyDistributionChart
            ttrBuckets={analytics.time_to_recovery_buckets}
          />
        </section>
      )}

      {/* Rail & Failure Health Distribution */}
      {analytics && (
        <section className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <PaymentRailChart railPerformance={analytics.rail_performance} />
          </div>
          <HealthScoreCard
            healthScore={analytics.health_score}
            returnOnSpend={analytics.return_on_recovery_spend}
          />
        </section>
      )}

      {/* Campaign Attribution Snapshot (Razorpay notes) */}
      {analytics?.campaign_metrics && analytics.campaign_metrics.length > 0 && (
        <Card>
          <CardHeader className="flex flex-col gap-2 border-b border-border p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
            <div>
              <div className="flex items-center gap-2">
                <Tag className="h-4 w-4 text-accent" />
                <CardTitle className="text-base">
                  Campaign Recovery Attribution
                </CardTitle>
                <Badge variant="outline" className="text-[10px]">
                  Razorpay notes
                </Badge>
              </div>
              <CardDescription className="mt-0.5 text-xs">
                Performance across active metadata cohorts tagged during payment
                and order creation
              </CardDescription>
            </div>
            {onNavigateToSection && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  onNavigateToSection('analytics')
                }}
                className="gap-1 text-xs text-accent hover:text-accent"
              >
                <span>View Full Analytics</span>
                <ArrowRight className="h-3 w-3" />
              </Button>
            )}
          </CardHeader>
          <CardContent className="p-4 sm:p-5">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {analytics.campaign_metrics.slice(0, 4).map((c) => {
                const recoveredWidth =
                  (c.recovered_paise / Math.max(1, c.at_risk_paise)) * 100
                return (
                  <div
                    key={c.campaign_id}
                    className="space-y-2 rounded-control border border-border bg-surface-sunken/50 p-3 text-xs"
                  >
                    <div className="flex items-center justify-between">
                      <span
                        className="max-w-[140px] truncate font-semibold text-ink"
                        title={c.campaign_id}
                      >
                        {c.campaign_id}
                      </span>
                      <Badge
                        variant={
                          c.recovery_rate_pct >= 50 ? 'recovered' : 'default'
                        }
                        className="text-[10px]"
                      >
                        {c.recovery_rate_pct.toFixed(1)}%
                      </Badge>
                    </div>

                    <div className="space-y-1">
                      <div className="h-1.5 w-full overflow-hidden rounded border border-border/50 bg-surface">
                        <div
                          className="h-full bg-recovered transition-all duration-300"
                          style={{
                            width: `${Math.min(100, recoveredWidth).toFixed(1)}%`,
                          }}
                        />
                      </div>
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="text-ink-muted">Yield:</span>
                        <span className="money font-bold text-accent">
                          {formatINR(c.net_recovered_value_paise)}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-[10px] text-ink-muted">
                        <span>
                          {c.recovered_cases}/{c.total_cases} resolved
                        </span>
                        <span>{formatINR(c.at_risk_paise)}</span>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Recent Cases Preview Table */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between border-b border-border p-4 sm:p-5">
          <div>
            <CardTitle>Recent Recovery Cases</CardTitle>
            <CardDescription className="mt-0.5 text-xs">
              Live stream of recent failed payments ingested into recovery
              engine
            </CardDescription>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              onNavigateToRecovery('ALL')
            }}
            className="text-xs"
          >
            View All Cases ({cases.length.toString()})
          </Button>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Case ID</TableHead>
                <TableHead>Payment Rail</TableHead>
                <TableHead>Amount</TableHead>
                <TableHead>Experiment Arm</TableHead>
                <TableHead>Current Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <>
                  <SkeletonRow variant="table" />
                  <SkeletonRow variant="table" />
                  <SkeletonRow variant="table" />
                  <SkeletonRow variant="table" />
                </>
              ) : cases.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="h-24 text-center text-sm text-ink-muted"
                  >
                    No recovery cases yet. Cases appear here as failed payment
                    webhooks arrive.
                  </TableCell>
                </TableRow>
              ) : (
                cases.slice(0, 8).map((c) => (
                  <TableRow
                    key={c.case_id}
                    className="cursor-pointer hover:bg-surface-sunken/60"
                    onClick={() => {
                      onSelectCase(c)
                    }}
                  >
                    <TableCell className="text-xs font-semibold text-ink">
                      {c.case_id}
                    </TableCell>
                    <TableCell>
                      <RailBadge rail={c.failure_event.payment_rail} />
                    </TableCell>
                    <TableCell className="money text-xs font-medium text-ink">
                      {formatINR(c.amount_paise)}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-[10px]">
                        {humanizeToken(c.experiment_arm)}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          c.state === 'RECOVERED'
                            ? 'recovered'
                            : c.state === 'ESCALATED'
                              ? 'escalated'
                              : 'pending'
                        }
                      >
                        {humanizeToken(c.state)}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-xs text-ink-muted hover:text-ink"
                        onClick={(e) => {
                          e.stopPropagation()
                          onSelectCase(c)
                        }}
                      >
                        Details
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Counterfactual Lift Callout Banner */}
      {analytics && (
        <div className="flex flex-col justify-between gap-4 rounded-panel border border-accent/40 bg-accent/5 p-4 sm:p-5 md:flex-row md:items-center">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-accent" />
              <span className="text-xs font-semibold tracking-wide text-ink uppercase">
                <GlossaryTerm termKey="HOLDOUT_ARM" showIcon={false}>
                  Counterfactual Recovery Lift (vs. 10% Control Arm)
                </GlossaryTerm>
              </span>
            </div>
            <p className="text-xs text-ink-muted">
              The AI engine achieved{' '}
              <strong className="money text-recovered">
                +{analytics.attributable_lift_pct.toFixed(1)}% lift
              </strong>{' '}
              in net recovery over natural recovery in uncontacted holdout
              cases.
            </p>
            <p className="text-[10px] text-ink-muted">
              {analytics.simulated_executions > 0 &&
              analytics.live_executions > 0
                ? `Mixed rails: ${analytics.live_executions.toLocaleString()} live and ${analytics.simulated_executions.toLocaleString()} simulated interventions, including ${formatINR(analytics.simulated_cost_paise)} of simulated cost.`
                : analytics.simulated_executions > 0
                  ? `Simulated rails: all ${analytics.simulated_executions.toLocaleString()} interventions ran against the sandbox, not a live gateway.`
                  : analytics.live_executions > 0
                    ? `Live rails: all ${analytics.live_executions.toLocaleString()} interventions reached the Razorpay gateway.`
                    : 'No interventions executed yet.'}
            </p>
          </div>
          <div className="flex items-center gap-4 border-t border-border pt-3 text-xs md:border-t-0 md:border-l md:pt-0 md:pl-6">
            <div>
              <span className="block text-[11px] text-ink-muted">
                <GlossaryTerm termKey="TREATMENT_ARM" showIcon={false}>
                  Treatment Cohort
                </GlossaryTerm>
              </span>
              <span className="text-sm font-bold text-ink">
                {analytics.treatment_recovery_rate_pct.toFixed(1)}%
              </span>
            </div>
            <div className="hidden h-6 w-px bg-border sm:block" />
            <div>
              <span className="block text-[11px] text-ink-muted">
                <GlossaryTerm termKey="HOLDOUT_ARM" showIcon={false}>
                  Holdout Control
                </GlossaryTerm>
              </span>
              <span className="text-sm font-bold text-ink-muted">
                {analytics.holdout_recovery_rate_pct.toFixed(1)}%
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
