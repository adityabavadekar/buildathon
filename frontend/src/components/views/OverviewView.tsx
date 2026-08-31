'use client'

import React, { useState } from 'react'
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  RotateCcw,
  ShieldAlert,
  TrendingUp,
} from 'lucide-react'
import {
  resetSimulation,
  seedSimulationBatch,
  type AnalyticsSummaryResponse,
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

interface OverviewViewProps {
  cases: RecoveryCase[]
  analytics: AnalyticsSummaryResponse | null
  loading: boolean
  onSelectCase: (c: RecoveryCase) => void
  onNavigateToRecovery: (subTab?: string) => void
  onRefresh: () => void
}

function formatINR(paise: number): string {
  const rupees = paise / 100
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(rupees)
}

export function OverviewView({
  cases,
  analytics,
  loading,
  onSelectCase,
  onNavigateToRecovery,
  onRefresh,
}: OverviewViewProps) {
  const [seeding, setSeeding] = useState(false)

  const totalAtRiskPaise = analytics
    ? analytics.total_at_risk_paise
    : cases.reduce((acc, c) => acc + c.amount_paise, 0)
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

  const recoveredCasesCount = cases.filter(
    (c) => c.state === 'RECOVERED',
  ).length
  const totalCasesCount = cases.length

  const activeCount =
    analytics?.active_cases !== undefined
      ? analytics.active_cases
      : cases.filter((c) =>
          [
            'IN_DUNNING',
            'OUTREACH_PENDING',
            'RETRY_SCHEDULED',
            'ANALYSIS_QUEUED',
          ].includes(c.state),
        ).length
  const escalatedCount =
    analytics?.escalated_cases !== undefined
      ? analytics.escalated_cases
      : cases.filter((c) => c.state === 'ESCALATED').length
  const recoveredCount =
    analytics?.recovered_cases !== undefined
      ? analytics.recovered_cases
      : recoveredCasesCount
  const totalCount =
    analytics?.total_cases !== undefined
      ? analytics.total_cases
      : totalCasesCount

  let recoveryRate = 0
  if (analytics) {
    recoveryRate = analytics.overall_recovery_rate_pct
  } else if (totalCasesCount > 0) {
    recoveryRate = (recoveredCasesCount / totalCasesCount) * 100
  }

  const handleSeedBatch = async (count: number = 50) => {
    try {
      setSeeding(true)
      await seedSimulationBatch(count)
      onRefresh()
    } finally {
      setSeeding(false)
    }
  }

  const handleResetData = async () => {
    try {
      setSeeding(true)
      await resetSimulation()
      onRefresh()
    } finally {
      setSeeding(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* View Header with Plain-Language Context */}
      <div className="flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-mono text-2xl font-bold text-ink">
            Revenue Recovery Control Center
          </h1>
          <p className="mt-0.5 text-sm text-ink-muted">
            Autonomous intervention lifecycle for failed payments, abandoned
            checkouts, and overdue receivables.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void handleResetData()
            }}
            disabled={seeding}
            className="font-mono text-xs"
          >
            Reset Test Cohort
          </Button>
          <Button
            size="sm"
            onClick={() => {
              void handleSeedBatch(50)
            }}
            disabled={seeding}
            className="font-mono text-xs"
          >
            {seeding ? 'Generating...' : 'Seed 50 Failures'}
          </Button>
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

      {/* 4 Primary Top Metrics with High-Contrast Typography */}
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
                <GlossaryTerm termKey="AT_RISK_REVENUE">
                  At Risk Revenue
                </GlossaryTerm>
              }
              value={formatINR(totalAtRiskPaise)}
              subtitle={`${totalCount.toString()} total failed transactions worked`}
              icon={<AlertTriangle className="h-4 w-4 text-failed" />}
              variant="default"
            />

            <StatCard
              title={
                <GlossaryTerm termKey="RECOVERED_NRV">
                  Recovered (NRV)
                </GlossaryTerm>
              }
              value={formatINR(totalNrvPaise)}
              subtitle={`Gross: ${formatINR(totalRecoveredPaise)} (Net of Costs)`}
              icon={<CheckCircle2 className="h-4 w-4 text-recovered" />}
              variant="recovered"
            />

            <StatCard
              title={
                <GlossaryTerm termKey="RECOVERY_RATE">
                  Recovery Rate
                </GlossaryTerm>
              }
              value={`${recoveryRate.toFixed(1)}%`}
              subtitle={`${recoveredCount.toString()} of ${totalCount.toString()} cases resolved`}
              icon={<TrendingUp className="h-4 w-4 text-accent" />}
              variant="default"
            />

            <StatCard
              title={
                <GlossaryTerm termKey="HUMAN_IN_THE_LOOP">
                  Need Attention
                </GlossaryTerm>
              }
              value={escalatedCount.toString()}
              subtitle={
                escalatedCount > 0
                  ? 'Escalated cases require operator signoff'
                  : 'Zero high-risk escalations pending'
              }
              icon={
                <ShieldAlert
                  className={`h-4 w-4 ${escalatedCount > 0 ? 'text-escalated' : 'text-ink-muted'}`}
                />
              }
              variant={escalatedCount > 0 ? 'escalated' : 'default'}
            />
          </>
        )}
      </section>

      {/* Counterfactual Lift Callout Banner */}
      {analytics && (
        <div className="flex flex-col justify-between gap-4 rounded-panel border border-accent/40 bg-accent/5 p-4 sm:p-5 md:flex-row md:items-center">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-accent" />
              <span className="font-mono text-xs font-bold tracking-wider text-ink uppercase">
                <GlossaryTerm termKey="HOLDOUT_ARM" showIcon={false}>
                  Counterfactual Recovery Lift (vs. 10% Control Arm)
                </GlossaryTerm>
              </span>
            </div>
            <p className="text-xs text-ink-muted">
              The AI engine achieved{' '}
              <strong className="font-mono text-recovered">
                +{analytics.attributable_lift_pct.toFixed(1)}% lift
              </strong>{' '}
              in net recovery over natural recovery in uncontacted holdout
              cases.
            </p>
          </div>
          <div className="flex items-center gap-4 border-t border-border pt-3 font-mono text-xs md:border-t-0 md:border-l md:pt-0 md:pl-6">
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
              <CardTitle className="font-mono text-sm text-ink">
                In-Flight Queue
              </CardTitle>
              <RotateCcw className="h-4 w-4 text-accent" />
            </div>
            <CardDescription className="text-xs text-ink-muted">
              Active dunning sequences & scheduled smart retries
            </CardDescription>
          </CardHeader>
          <CardContent className="p-4 pt-0 sm:p-5">
            <div className="mt-2 flex items-baseline justify-between font-mono">
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
              <CardTitle className="font-mono text-sm text-ink">
                Manual Approvals
              </CardTitle>
              <ShieldAlert className="h-4 w-4 text-escalated" />
            </div>
            <CardDescription className="text-xs text-ink-muted">
              Cases escalated by deterministic guardrails
            </CardDescription>
          </CardHeader>
          <CardContent className="p-4 pt-0 sm:p-5">
            <div className="mt-2 flex items-baseline justify-between font-mono">
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
              <CardTitle className="font-mono text-sm text-ink">
                Recovered Volume
              </CardTitle>
              <CheckCircle2 className="h-4 w-4 text-recovered" />
            </div>
            <CardDescription className="text-xs text-ink-muted">
              Successfully completed revenue recoveries
            </CardDescription>
          </CardHeader>
          <CardContent className="p-4 pt-0 sm:p-5">
            <div className="mt-2 flex items-baseline justify-between font-mono">
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
            recoveryStreak={analytics.recovery_streak}
          />
        </section>
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
            className="font-mono text-xs"
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
                  <SkeletonRow />
                  <SkeletonRow />
                  <SkeletonRow />
                  <SkeletonRow />
                </>
              ) : cases.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="h-24 text-center font-mono text-xs text-ink-muted"
                  >
                    No recovery cases found. Click &quot;Seed 50 Failures&quot;
                    to generate synthetic cases.
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
                    <TableCell className="font-mono text-xs font-semibold text-ink">
                      {c.case_id}
                    </TableCell>
                    <TableCell>
                      <RailBadge rail={c.failure_event.payment_rail} />
                    </TableCell>
                    <TableCell className="font-mono text-xs font-medium text-ink">
                      {formatINR(c.amount_paise)}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className="font-mono text-[10px]"
                      >
                        {c.experiment_arm}
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
                        {c.state.replace('_', ' ')}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="font-mono text-xs text-ink-muted hover:text-ink"
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
    </div>
  )
}
