'use client'

import React, { useState } from 'react'
import { approveCase, type RecoveryCase, type RecoveryState } from '@/lib/api'
import { Badge, type BadgeVariant } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
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
}

type SubTab = 'ALL' | 'ACTIVE' | 'AT_RISK' | 'RECOVERED' | 'ESCALATED'

function formatINR(paise: number): string {
  const rupees = paise / 100
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(rupees)
}

function stateToVariant(state: RecoveryState): BadgeVariant {
  switch (state) {
    case 'RECOVERED':
      return 'recovered'
    case 'ESCALATED':
      return 'escalated'
    case 'FAILED':
      return 'failed'
    case 'OUTREACH_PENDING':
    case 'RETRY_SCHEDULED':
    case 'IN_DUNNING':
    case 'ANALYSIS_QUEUED':
      return 'pending'
    default:
      return 'default'
  }
}

export function RecoveryView({
  cases,
  loading,
  onSelectCase,
  onRefresh,
}: RecoveryViewProps) {
  const [subTab, setSubTab] = useState<SubTab>('ALL')
  const [searchQuery, setSearchQuery] = useState<string>('')
  const [approvingId, setApprovingId] = useState<string | null>(null)

  const filteredCases = cases.filter((c) => {
    // 1. State Filter
    let matchesTab: boolean
    switch (subTab) {
      case 'ACTIVE':
        matchesTab = ['IN_DUNNING', 'OUTREACH_PENDING', 'RETRY_SCHEDULED'].includes(c.state)
        break
      case 'AT_RISK':
        matchesTab = ['ANALYSIS_QUEUED', 'IN_DUNNING', 'ESCALATED'].includes(c.state)
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

    // 2. Search Query
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
      <Card>
        <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between p-4">
          <div>
            <CardTitle>Recovery Workspace</CardTitle>
            <CardDescription>
              Operational pipeline for managing automated recovery workflows and escalations
            </CardDescription>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Search Input */}
            <input
              type="text"
              placeholder="Search case, payment, customer..."
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value)
              }}
              className="rounded-control bg-surface-sunken border border-border px-3 py-1.5 text-xs font-mono text-ink placeholder:text-ink-subtle w-60 focus:outline-none focus:border-accent"
            />

            {/* Sub Navigation Tabs from UI_ROUGH.md */}
            <div className="flex gap-1 rounded-control bg-surface-sunken p-1 border border-border">
              {(
                [
                  { id: 'ALL', label: 'All' },
                  { id: 'ACTIVE', label: 'Active' },
                  { id: 'AT_RISK', label: 'At Risk' },
                  { id: 'RECOVERED', label: 'Recovered' },
                  { id: 'ESCALATED', label: 'Escalated' },
                ] as const
              ).map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => {
                    setSubTab(tab.id)
                  }}
                  className={`rounded-control px-2.5 py-1 text-xs font-mono transition-colors cursor-pointer ${
                    subTab === tab.id
                      ? 'bg-surface text-ink font-semibold shadow-xs border border-border/80'
                      : 'text-ink-muted hover:text-ink'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>
        </CardHeader>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Case ID</TableHead>
              <TableHead>Customer</TableHead>
              <TableHead>Rail</TableHead>
              <TableHead>Failure Reason</TableHead>
              <TableHead className="text-right">Amount</TableHead>
              <TableHead className="text-center">Touches</TableHead>
              <TableHead className="text-center">Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={8} className="p-0">
                  <SkeletonRow />
                  <SkeletonRow />
                  <SkeletonRow />
                </TableCell>
              </TableRow>
            ) : filteredCases.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={8}
                  className="py-12 text-center text-xs font-mono text-ink-muted"
                >
                  No cases found matching the criteria.
                </TableCell>
              </TableRow>
            ) : (
              filteredCases.map((c) => (
                <TableRow
                  key={c.case_id}
                  className="cursor-pointer hover:bg-surface-sunken/50"
                  onClick={() => {
                    onSelectCase(c)
                  }}
                >
                  <TableCell className="font-mono text-xs font-medium">
                    {c.case_id}
                    <div className="text-[10px] text-ink-subtle">
                      {c.failure_event.payment_id}
                    </div>
                  </TableCell>
                  <TableCell className="font-mono text-xs">{c.failure_event.customer_id}</TableCell>
                  <TableCell className="font-mono text-xs uppercase">{c.failure_event.payment_rail}</TableCell>
                  <TableCell className="text-xs text-ink-muted max-w-xs truncate">
                    {c.failure_event.error_reason || c.failure_event.error_code}
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs font-medium tabular-nums">
                    {formatINR(c.amount_paise)}
                  </TableCell>
                  <TableCell className="text-center font-mono text-xs">
                    {c.touches_count.toString()} / 3
                  </TableCell>
                  <TableCell className="text-center">
                    <Badge variant={stateToVariant(c.state)}>
                      {c.state.replace('_', ' ')}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right space-x-2">
                    {c.state === 'ESCALATED' && (
                      <Button
                        size="sm"
                        variant="primary"
                        disabled={approvingId === c.case_id}
                        onClick={(e) => {
                          e.stopPropagation()
                          void handleApprove(c.case_id)
                        }}
                      >
                        {approvingId === c.case_id ? 'Approving...' : 'Approve'}
                      </Button>
                    )}
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
