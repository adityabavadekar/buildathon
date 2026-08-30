'use client'

import React, { useEffect, useState } from 'react'
import {
  CheckCircle2,
  RefreshCw,
  Search,
  ShieldAlert,
  Sliders,
  UserCheck,
} from 'lucide-react'
import {
  approveCase,
  getPolicies,
  type PolicyResponse,
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
import { RecoveryLifecycleStrip } from '@/components/recovery/RecoveryLifecycleStrip'
import { SkeletonRow } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

interface RecoveryViewProps {
  cases: RecoveryCase[]
  loading: boolean
  onSelectCase: (c: RecoveryCase) => void
  onRefresh: () => void
  initialSubTab?: string
}

function formatINR(paise: number): string {
  const rupees = paise / 100
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(rupees)
}

export function RecoveryView({
  cases,
  loading,
  onSelectCase,
  onRefresh,
  initialSubTab = 'ALL',
}: RecoveryViewProps) {
  const [activeTabOverride, setActiveTabOverride] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState<string>('')
  const [approvingId, setApprovingId] = useState<string | null>(null)
  const [policy, setPolicy] = useState<PolicyResponse | null>(null)

  const subTab = activeTabOverride ?? initialSubTab

  useEffect(() => {
    getPolicies()
      .then((p) => {
        setPolicy(p)
      })
      .catch(() => null)
  }, [])

  const maxTouches = policy?.max_touches ?? 3

  const activeCasesCount = cases.filter((c) =>
    ['IN_DUNNING', 'OUTREACH_PENDING', 'RETRY_SCHEDULED'].includes(c.state)
  ).length
  const recoveredCasesCount = cases.filter((c) => c.state === 'RECOVERED').length
  const totalRecoveredPaise = cases
    .filter((c) => c.state === 'RECOVERED')
    .reduce((acc, c) => acc + (c.recovered_amount_paise || c.amount_paise), 0)
  const escalatedCasesCount = cases.filter((c) => c.state === 'ESCALATED').length

  const filteredCases = cases.filter((c) => {
    let matchesTab: boolean
    switch (subTab) {
      case 'ACTIVE':
        matchesTab = ['IN_DUNNING', 'OUTREACH_PENDING', 'RETRY_SCHEDULED'].includes(c.state)
        break
      case 'AT_RISK':
        matchesTab = ['ANALYSIS_QUEUED', 'IN_DUNNING', 'ESCALATED', 'FAILED'].includes(c.state)
        break
      case 'RECOVERED':
        matchesTab = c.state === 'RECOVERED'
        break
      case 'ESCALATED':
        matchesTab = c.state === 'ESCALATED'
        break
      default:
        matchesTab = true
    }

    if (!matchesTab) return false

    if (searchQuery.trim() === '') return true
    const q = searchQuery.toLowerCase()
    return (
      c.case_id.toLowerCase().includes(q) ||
      c.failure_event.payment_id.toLowerCase().includes(q) ||
      c.failure_event.customer_id.toLowerCase().includes(q) ||
      (c.failure_event.error_reason || '').toLowerCase().includes(q)
    )
  })

  const handleApprove = async (caseId: string) => {
    try {
      setApprovingId(caseId)
      await approveCase(caseId, 'Approved by operator from recovery dashboard')
      onRefresh()
    } finally {
      setApprovingId(null)
    }
  }

  return (
    <div className="space-y-6">
      {/* View Header with Plain-Language Context */}
      <div className="border-b border-border pb-4">
        <h1 className="text-2xl font-bold font-mono text-ink">
          Recovery Workspace
        </h1>
        <p className="text-sm text-ink-muted mt-0.5">
          Every failed payment the engine is working, with its diagnosed cause, current lifecycle status, and next operator action.
        </p>
      </div>

      {/* Guided 4-Step Recovery Lifecycle Strip */}
      <RecoveryLifecycleStrip
        cases={cases}
        onStepClick={(idx) => {
          if (idx === 0) setActiveTabOverride('AT_RISK')
          else if (idx === 1) setActiveTabOverride('ALL')
          else if (idx === 2) setActiveTabOverride('ACTIVE')
          else if (idx === 3) setActiveTabOverride('RECOVERED')
        }}
      />

      {/* Large-Font Summary Statistics Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="hover:border-accent/40 transition-colors">
          <CardHeader className="p-5 pb-2 border-none">
            <div className="flex items-center justify-between">
              <CardDescription className="text-xs font-semibold text-ink-muted">
                In-Flight Interventions
              </CardDescription>
              <div className="p-2 rounded-control bg-accent/15 text-accent">
                <RefreshCw className="h-4 w-4" />
              </div>
            </div>
            <CardTitle className="text-3xl font-mono font-bold tabular-nums text-ink mt-1">
              {activeCasesCount.toString()}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-5 pt-0 text-xs text-ink-subtle">
            Active retries & payment links in-flight
          </CardContent>
        </Card>

        <Card className="border-recovered/30 bg-recovered/5 hover:border-recovered/60 transition-colors">
          <CardHeader className="p-5 pb-2 border-none">
            <div className="flex items-center justify-between">
              <CardDescription className="text-xs font-semibold text-ink-muted">
                Recovered Volume
              </CardDescription>
              <div className="p-2 rounded-control bg-recovered/20 text-recovered">
                <CheckCircle2 className="h-4 w-4" />
              </div>
            </div>
            <CardTitle className="text-3xl font-mono font-bold tabular-nums text-recovered mt-1">
              {formatINR(totalRecoveredPaise)}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-5 pt-0 text-xs text-ink-subtle">
            {recoveredCasesCount.toString()} successfully resolved cases
          </CardContent>
        </Card>

        <Card
          className={
            escalatedCasesCount > 0
              ? 'border-escalated/50 bg-escalated-subtle/20'
              : 'hover:border-border-strong transition-colors'
          }
        >
          <CardHeader className="p-5 pb-2 border-none">
            <div className="flex items-center justify-between">
              <CardDescription className="text-xs font-semibold text-ink-muted">
                Requires Operator Review
              </CardDescription>
              <div
                className={`p-2 rounded-control ${
                  escalatedCasesCount > 0
                    ? 'bg-escalated/20 text-escalated'
                    : 'bg-surface-sunken text-ink-muted'
                }`}
              >
                <ShieldAlert className="h-4 w-4" />
              </div>
            </div>
            <CardTitle
              className={`text-3xl font-mono font-bold tabular-nums mt-1 ${
                escalatedCasesCount > 0 ? 'text-escalated' : 'text-ink'
              }`}
            >
              {escalatedCasesCount.toString()}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-5 pt-0 text-xs text-ink-subtle">
            {escalatedCasesCount > 0
              ? 'High-value or low-confidence escalations'
              : 'Zero cases pending manual approval'}
          </CardContent>
        </Card>

        <Card className="hover:border-border-strong transition-colors">
          <CardHeader className="p-5 pb-2 border-none">
            <div className="flex items-center justify-between">
              <CardDescription className="text-xs font-semibold text-ink-muted">
                Touch Cap Bound
              </CardDescription>
              <div className="p-2 rounded-control bg-accent/15 text-accent">
                <Sliders className="h-4 w-4" />
              </div>
            </div>
            <CardTitle className="text-3xl font-mono font-bold tabular-nums text-ink mt-1">
              &le; {maxTouches.toString()} Max
            </CardTitle>
          </CardHeader>
          <CardContent className="p-5 pt-0 text-xs text-ink-subtle">
            Strict stopping rule enforced per customer
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between p-5 border-b border-border">
          <div>
            <CardTitle>Case Directory</CardTitle>
            <CardDescription className="text-xs mt-0.5">
              Filter by operational state or search by customer ID, payment ID, or error reason
            </CardDescription>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Search Input */}
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-ink-muted" />
              <input
                type="text"
                placeholder="Search case, payment, customer..."
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value)
                }}
                className="rounded-control border border-border bg-surface-sunken pl-8 pr-3 py-1.5 text-xs font-mono text-ink placeholder:text-ink-subtle focus:outline-none focus:ring-1 focus:ring-accent w-[240px]"
              />
            </div>

            {/* Sub-Tabs */}
            <div className="flex items-center gap-1 rounded-control bg-surface-sunken p-1 text-xs font-mono">
              {['ALL', 'ACTIVE', 'AT_RISK', 'ESCALATED', 'RECOVERED'].map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => {
                    setActiveTabOverride(tab)
                  }}
                  className={`rounded-xs px-2.5 py-1 text-xs transition-colors cursor-pointer ${
                    subTab === tab
                      ? 'bg-surface text-ink font-semibold shadow-xs'
                      : 'text-ink-muted hover:text-ink'
                  }`}
                >
                  {tab.replace('_', ' ')}
                </button>
              ))}
            </div>
          </div>
        </CardHeader>

        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Case ID</TableHead>
                <TableHead>Payment & Rail</TableHead>
                <TableHead>Customer</TableHead>
                <TableHead>Amount</TableHead>
                <TableHead>Arm</TableHead>
                <TableHead>Touches</TableHead>
                <TableHead>State</TableHead>
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
                  <SkeletonRow />
                </>
              ) : filteredCases.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={8}
                    className="h-32 text-center font-mono text-xs text-ink-muted"
                  >
                    No recovery cases matched the selected criteria.
                  </TableCell>
                </TableRow>
              ) : (
                filteredCases.map((c) => (
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
                      <div className="font-mono text-xs text-ink">
                        {c.failure_event.payment_id}
                      </div>
                      <div className="font-mono text-[10px] uppercase text-ink-subtle">
                        {c.failure_event.payment_rail}
                      </div>
                    </TableCell>
                    <TableCell className="font-mono text-xs text-ink-muted">
                      {c.failure_event.customer_id}
                    </TableCell>
                    <TableCell className="font-mono text-xs font-semibold text-ink">
                      {formatINR(c.amount_paise)}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="font-mono text-[10px]">
                        {c.experiment_arm}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs text-ink-muted">
                      {c.touches_count.toString()} / {maxTouches.toString()}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          c.state === 'RECOVERED'
                            ? 'recovered'
                            : c.state === 'ESCALATED'
                            ? 'escalated'
                            : c.state === 'FAILED'
                            ? 'failed'
                            : 'pending'
                        }
                      >
                        {c.state.replace('_', ' ')}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      {c.state === 'ESCALATED' && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="font-mono text-xs text-escalated border-escalated/40 hover:bg-escalated/10"
                          onClick={(e) => {
                            e.stopPropagation()
                            void handleApprove(c.case_id)
                          }}
                          disabled={approvingId === c.case_id}
                        >
                          <UserCheck className="mr-1 h-3 w-3" />
                          {approvingId === c.case_id ? 'Approving...' : 'Approve'}
                        </Button>
                      )}
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
