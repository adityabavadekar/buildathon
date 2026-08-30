'use client'

import React, { useState } from 'react'
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

  const totalAtRiskPaise = analytics ? analytics.total_at_risk_paise : cases.reduce((acc, c) => acc + c.amount_paise, 0)
  const totalRecoveredPaise = analytics ? analytics.recovered_amount_paise : cases.reduce((acc, c) => acc + (c.recovered_amount_paise || 0), 0)
  const totalNrvPaise = analytics ? analytics.net_recovered_value_paise : cases.reduce((acc, c) => acc + (c.net_recovered_value_paise || 0), 0)
  const totalCasesCount = analytics ? analytics.total_cases : cases.length

  const recoveredCount = cases.filter((c) => c.state === 'RECOVERED').length
  const escalatedCount = cases.filter((c) => c.state === 'ESCALATED').length
  const recoveryRate = analytics
    ? analytics.overall_recovery_rate_pct.toFixed(1)
    : totalCasesCount > 0 ? ((recoveredCount / totalCasesCount) * 100).toFixed(1) : '0.0'

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
      {/* 4 Primary Top Metrics */}
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
            <Card>
              <CardHeader className="p-4 pb-2 border-none">
                <CardDescription>At Risk Revenue</CardDescription>
                <CardTitle className="text-2xl font-mono tabular-nums text-ink">
                  {formatINR(totalAtRiskPaise)}
                </CardTitle>
              </CardHeader>
              <CardContent className="p-4 pt-0 text-[11px] text-ink-subtle">
                {totalCasesCount.toString()} total failed transactions
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="p-4 pb-2 border-none">
                <CardDescription>Recovered (NRV)</CardDescription>
                <CardTitle className="text-2xl font-mono tabular-nums text-recovered">
                  {formatINR(totalNrvPaise)}
                </CardTitle>
              </CardHeader>
              <CardContent className="p-4 pt-0 text-[11px] text-ink-subtle">
                Gross: {formatINR(totalRecoveredPaise)}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="p-4 pb-2 border-none">
                <CardDescription>Recovery Rate</CardDescription>
                <CardTitle className="text-2xl font-mono tabular-nums text-accent">
                  {recoveryRate}%
                </CardTitle>
              </CardHeader>
              <CardContent className="p-4 pt-0 text-[11px] text-ink-subtle">
                {recoveredCount.toString()} / {totalCasesCount.toString()} cases resolved
              </CardContent>
            </Card>

            <Card
              className={escalatedCount > 0 ? 'border-escalated/40 bg-escalated-subtle/20' : ''}
            >
              <CardHeader className="p-4 pb-2 border-none">
                <CardDescription>Need Attention</CardDescription>
                <CardTitle
                  className={`text-2xl font-mono tabular-nums ${
                    escalatedCount > 0 ? 'text-escalated' : 'text-ink'
                  }`}
                >
                  {escalatedCount.toString()}
                </CardTitle>
              </CardHeader>
              <CardContent className="p-4 pt-0 text-[11px] text-ink-subtle">
                {escalatedCount > 0
                  ? `${escalatedCount.toString()} cases escalated for review`
                  : 'All autonomous workflows optimal'}
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
            <CardDescription>
              Dynamic intervention breakdown by recovery channel and automated retry workflows
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {analytics?.intervention_performance && analytics.intervention_performance.length > 0 ? (
              analytics.intervention_performance.map((item) => (
                <div key={item.intervention_type} className="space-y-2">
                  <div className="flex justify-between text-xs font-mono">
                    <span className="text-ink">{item.intervention_type.replace('_', ' ')}</span>
                    <span className="text-recovered font-semibold">
                      {item.success_rate_pct.toFixed(1)}% Success ({item.successful_recoveries.toString()}/{item.total_attempts.toString()})
                    </span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-surface-sunken overflow-hidden">
                    <div
                      className="h-full bg-recovered transition-all duration-500"
                      style={{ width: `${Math.min(100, item.success_rate_pct).toString()}%` }}
                    />
                  </div>
                </div>
              ))
            ) : (
              <div className="py-6 text-center text-xs font-mono text-ink-muted">
                No active intervention telemetry.
              </div>
            )}
          </CardContent>
        </Card>

        {/* Live Simulation Controls */}
        <Card>
          <CardHeader>
            <CardTitle>Cohort Simulation</CardTitle>
            <CardDescription>Generate test recovery batches</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Button
              className="w-full"
              variant="primary"
              disabled={seeding}
              onClick={() => {
                void handleSeedBatch(50)
              }}
            >
              {seeding ? 'Seeding Batch...' : 'Seed 50 Synthetic Cases'}
            </Button>
            <Button
              className="w-full"
              variant="outline"
              disabled={seeding}
              onClick={() => {
                void handleResetData()
              }}
            >
              Reset Repository
            </Button>
            <Button
              className="w-full"
              variant="ghost"
              onClick={() => {
                onNavigateToRecovery()
              }}
            >
              Open Recovery Workspace
            </Button>
          </CardContent>
        </Card>
      </section>

      {/* Recent Cases Section */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Recent Recovery Cases</CardTitle>
            <CardDescription>Latest failure events ingested from Razorpay webhooks</CardDescription>
          </div>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              onNavigateToRecovery()
            }}
          >
            View All Cases
          </Button>
        </CardHeader>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Case ID</TableHead>
              <TableHead>Customer</TableHead>
              <TableHead>Rail</TableHead>
              <TableHead className="text-right">Amount</TableHead>
              <TableHead className="text-center">Status</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={6} className="p-0">
                  <SkeletonRow />
                  <SkeletonRow />
                </TableCell>
              </TableRow>
            ) : cases.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="py-12 text-center text-xs font-mono text-ink-muted">
                  <p>No recovery cases recorded yet.</p>
                  <Button
                    className="mt-3"
                    size="sm"
                    variant="primary"
                    disabled={seeding}
                    onClick={() => {
                      void handleSeedBatch(25)
                    }}
                  >
                    Seed Demo Dataset
                  </Button>
                </TableCell>
              </TableRow>
            ) : (
              cases.slice(0, 6).map((c) => (
                <TableRow
                  key={c.case_id}
                  className="cursor-pointer hover:bg-surface-sunken/50"
                  onClick={() => {
                    onSelectCase(c)
                  }}
                >
                  <TableCell className="font-mono text-xs font-medium">
                    {c.case_id}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{c.failure_event.customer_id}</TableCell>
                  <TableCell className="font-mono text-xs uppercase">{c.failure_event.payment_rail}</TableCell>
                  <TableCell className="text-right font-mono text-xs font-medium tabular-nums">
                    {formatINR(c.amount_paise)}
                  </TableCell>
                  <TableCell className="text-center">
                    <Badge variant={c.state === 'RECOVERED' ? 'recovered' : c.state === 'ESCALATED' ? 'escalated' : 'pending'}>
                      {c.state.replace('_', ' ')}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={(e) => {
                        e.stopPropagation()
                        onSelectCase(c)
                      }}
                    >
                      Inspect
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Card>
    </div>
  )
}
