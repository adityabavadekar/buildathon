'use client'

import React, { useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  ShieldAlert,
  TrendingUp,
} from 'lucide-react'
import {
  resetSimulation,
  seedSimulation,
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
import { OpportunityMatrix } from '@/components/matrix/OpportunityMatrix'

interface OverviewViewProps {
  cases: RecoveryCase[]
  analytics: AnalyticsSummaryResponse | null
  loading: boolean
  onSelectCase: (c: RecoveryCase) => void
  onNavigateToRecovery: (substate?: string) => void
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
  const [seeding, setSeeding] = useState<boolean>(false)

  const totalAtRiskPaise = analytics
    ? analytics.total_at_risk_paise
    : cases.reduce((acc, c) => acc + c.amount_paise, 0)
  const totalRecoveredPaise = analytics
    ? analytics.recovered_amount_paise
    : cases.reduce((acc, c) => acc + (c.recovered_amount_paise || 0), 0)
  const totalNrvPaise = analytics
    ? analytics.net_recovered_value_paise
    : cases.reduce((acc, c) => acc + (c.net_recovered_value_paise || 0), 0)
  const totalCasesCount = analytics ? analytics.total_cases : cases.length

  const recoveredCount = cases.filter((c) => c.state === 'RECOVERED').length
  const escalatedCount = cases.filter((c) => c.state === 'ESCALATED').length
  const recoveryRate = analytics
    ? analytics.overall_recovery_rate_pct.toFixed(1)
    : totalCasesCount > 0
    ? ((recoveredCount / totalCasesCount) * 100).toFixed(1)
    : '0.0'

  const handleSeedBatch = async (count: number = 50) => {
    try {
      setSeeding(true)
      await seedSimulation(count, true)
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
      {/* View Header with Plain-Language Intro */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border pb-4">
        <div>
          <h1 className="text-2xl font-bold font-mono text-ink">
            Revenue Recovery Control Center
          </h1>
          <p className="text-sm text-ink-muted mt-0.5">
            Real-time detection, contextual diagnosis, and policy-bounded recovery execution for failed checkouts and subscriptions.
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

      {/* 4 Primary Top Metrics with Filled Semantic Icons */}
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
            {/* Card 1: At Risk Revenue */}
            <Card className="hover:border-failed/40 transition-colors">
              <CardHeader className="p-5 pb-2 border-none">
                <div className="flex items-center justify-between">
                  <CardDescription className="text-xs font-semibold text-ink-muted">
                    <GlossaryTerm termKey="AT_RISK_REVENUE">At Risk Revenue</GlossaryTerm>
                  </CardDescription>
                  <div className="p-2 rounded-control bg-failed/15 text-failed">
                    <AlertTriangle className="h-4 w-4" />
                  </div>
                </div>
                <CardTitle className="text-3xl font-mono font-bold tabular-nums text-ink mt-1">
                  {formatINR(totalAtRiskPaise)}
                </CardTitle>
              </CardHeader>
              <CardContent className="p-5 pt-0 text-xs text-ink-subtle">
                {totalCasesCount.toString()} total failed transactions worked
              </CardContent>
            </Card>

            {/* Card 2: Recovered (NRV) */}
            <Card className="border-recovered/30 bg-recovered/5 hover:border-recovered/60 transition-colors">
              <CardHeader className="p-5 pb-2 border-none">
                <div className="flex items-center justify-between">
                  <CardDescription className="text-xs font-semibold text-ink-muted">
                    <GlossaryTerm termKey="RECOVERED_NRV">Recovered (NRV)</GlossaryTerm>
                  </CardDescription>
                  <div className="p-2 rounded-control bg-recovered/20 text-recovered">
                    <CheckCircle2 className="h-4 w-4" />
                  </div>
                </div>
                <CardTitle className="text-3xl font-mono font-bold tabular-nums text-recovered mt-1">
                  {formatINR(totalNrvPaise)}
                </CardTitle>
              </CardHeader>
              <CardContent className="p-5 pt-0 text-xs text-ink-subtle flex items-center justify-between">
                <span>
                  Gross:{' '}
                  <GlossaryTerm termKey="GROSS_RECOVERED" showIcon={false}>
                    {formatINR(totalRecoveredPaise)}
                  </GlossaryTerm>
                </span>
                <span className="text-recovered font-mono text-[11px] font-semibold">Net of Costs</span>
              </CardContent>
            </Card>

            {/* Card 3: Recovery Rate */}
            <Card className="hover:border-accent/40 transition-colors">
              <CardHeader className="p-5 pb-2 border-none">
                <div className="flex items-center justify-between">
                  <CardDescription className="text-xs font-semibold text-ink-muted">
                    <GlossaryTerm termKey="RECOVERY_RATE">Recovery Rate</GlossaryTerm>
                  </CardDescription>
                  <div className="p-2 rounded-control bg-accent/15 text-accent">
                    <TrendingUp className="h-4 w-4" />
                  </div>
                </div>
                <CardTitle className="text-3xl font-mono font-bold tabular-nums text-accent mt-1">
                  {recoveryRate}%
                </CardTitle>
              </CardHeader>
              <CardContent className="p-5 pt-0 text-xs text-ink-subtle">
                {recoveredCount.toString()} / {totalCasesCount.toString()} cases resolved
              </CardContent>
            </Card>

            {/* Card 4: Need Attention */}
            <Card
              className={
                escalatedCount > 0
                  ? 'border-escalated/50 bg-escalated-subtle/20'
                  : 'hover:border-border-strong transition-colors'
              }
            >
              <CardHeader className="p-5 pb-2 border-none">
                <div className="flex items-center justify-between">
                  <CardDescription className="text-xs font-semibold text-ink-muted">
                    <GlossaryTerm termKey="NEED_ATTENTION">Need Attention</GlossaryTerm>
                  </CardDescription>
                  <div
                    className={`p-2 rounded-control ${
                      escalatedCount > 0
                        ? 'bg-escalated/20 text-escalated'
                        : 'bg-surface-sunken text-ink-muted'
                    }`}
                  >
                    <ShieldAlert className="h-4 w-4" />
                  </div>
                </div>
                <CardTitle
                  className={`text-3xl font-mono font-bold tabular-nums mt-1 ${
                    escalatedCount > 0 ? 'text-escalated' : 'text-ink'
                  }`}
                >
                  {escalatedCount.toString()}
                </CardTitle>
              </CardHeader>
              <CardContent className="p-5 pt-0 text-xs text-ink-subtle">
                {escalatedCount > 0
                  ? `${escalatedCount.toString()} cases escalated for human review`
                  : 'All autonomous workflows within guardrails'}
              </CardContent>
            </Card>
          </>
        )}
      </section>

      {/* Recovery Opportunity Matrix (2x2) */}
      <OpportunityMatrix cases={cases} onSelectCase={onSelectCase} />

      {/* Recovery Performance & Quick Actions */}
      <section className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Channel Performance & Effectiveness</CardTitle>
            <CardDescription className="text-sm">
              Dynamic intervention success rates across single-use payment links, WhatsApp nudges, and smart retries
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {analytics?.intervention_performance &&
            analytics.intervention_performance.length > 0 ? (
              analytics.intervention_performance.map((item) => (
                <div key={item.intervention_type} className="space-y-2">
                  <div className="flex justify-between text-xs font-mono">
                    <span className="text-ink font-semibold">
                      {item.intervention_type.replace('_', ' ')}
                    </span>
                    <span className="text-recovered font-bold">
                      {item.success_rate_pct.toFixed(1)}% Success (
                      {item.successful_recoveries.toString()}/
                      {item.total_attempts.toString()})
                    </span>
                  </div>
                  <div className="h-2.5 w-full rounded-full bg-surface-sunken overflow-hidden">
                    <div
                      className="h-full bg-recovered transition-all duration-500"
                      style={{
                        width: `${Math.min(100, item.success_rate_pct).toString()}%`,
                      }}
                    />
                  </div>
                </div>
              ))
            ) : (
              <p className="py-4 text-center text-xs font-mono text-ink-muted">
                No channel metrics recorded yet. Seed transactions to generate real-time performance data.
              </p>
            )}
          </CardContent>
        </Card>

        {/* Quick Operational Actions */}
        <Card>
          <CardHeader>
            <CardTitle>Autonomous Ops</CardTitle>
            <CardDescription className="text-sm">
              Batch generation and holdout verification
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="p-3.5 rounded-control bg-surface-sunken border border-border space-y-1">
              <span className="text-xs font-mono font-bold text-ink">
                10% Holdout Control Arm
              </span>
              <p className="text-xs text-ink-muted leading-relaxed">
                Deliberately holds out 10% of failed payments uncontacted to verify counterfactual recovery lift.
              </p>
            </div>

            <Button
              variant="outline"
              size="sm"
              className="w-full justify-start font-mono text-xs"
              onClick={() => {
                void handleSeedBatch(100)
              }}
              disabled={seeding}
            >
              Seed 100 Realistic Invoices
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="w-full justify-start font-mono text-xs"
              onClick={() => {
                onNavigateToRecovery('ESCALATED')
              }}
            >
              Inspect Escalations ({escalatedCount.toString()})
            </Button>
          </CardContent>
        </Card>
      </section>

      {/* Recent Activity Table */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Recent Recovery Transactions</CardTitle>
            <CardDescription className="text-sm">
              Real-time feed of detected payment failures and active dunning state
            </CardDescription>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="font-mono text-xs text-accent"
            onClick={() => {
              onNavigateToRecovery()
            }}
          >
            View All ({cases.length.toString()})
          </Button>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Case ID</TableHead>
                <TableHead>Rail</TableHead>
                <TableHead>Amount</TableHead>
                <TableHead>Arm</TableHead>
                <TableHead>State</TableHead>
                <TableHead>Error Reason</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <>
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
                    No recovery cases found. Click &apos;Seed 50 Failures&apos; to begin.
                  </TableCell>
                </TableRow>
              ) : (
                cases.slice(0, 5).map((c) => (
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
                    <TableCell className="font-mono text-xs uppercase text-ink-muted">
                      {c.failure_event.payment_rail}
                    </TableCell>
                    <TableCell className="font-mono text-xs font-medium text-ink">
                      {formatINR(c.amount_paise)}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="font-mono text-[10px]">
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
                    <TableCell className="text-xs text-ink-muted max-w-[200px] truncate">
                      {c.failure_event.error_reason || c.failure_event.error_code}
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
