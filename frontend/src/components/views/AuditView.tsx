'use client'

import React, { useState } from 'react'
import type { RecoveryCase } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

interface AuditViewProps {
  cases: RecoveryCase[]
}

export function AuditView({ cases }: AuditViewProps) {
  const [filterActor, setFilterActor] = useState<string>('ALL')

  const allEntries = cases.flatMap((c) =>
    c.audit_trail.map((e) => ({
      ...e,
      paymentId: c.failure_event.payment_id,
      amountPaise: c.amount_paise,
    }))
  )

  allEntries.sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  )

  const filteredEntries = allEntries.filter((e) => {
    if (filterActor === 'ALL') return true
    return e.actor === filterActor
  })

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between p-4">
          <div>
            <CardTitle>System-Wide Audit Trail</CardTitle>
            <CardDescription>
              Chronological immutable log of all state transitions, AI decisions, policy evaluations, and payment captures
            </CardDescription>
          </div>

          {/* Actor Filters */}
          <div className="flex gap-1 rounded-control bg-surface-sunken p-1 border border-border">
            {(
              [
                'ALL',
                'SYSTEM',
                'AGENT_LLM',
                'POLICY_GATE',
                'GATEWAY_WEBHOOK',
                'HUMAN_OPERATOR',
              ] as const
            ).map((act) => (
              <button
                key={act}
                type="button"
                onClick={() => {
                  setFilterActor(act)
                }}
                className={`rounded-control px-2 py-1 text-[11px] font-mono transition-colors cursor-pointer ${
                  filterActor === act
                    ? 'bg-surface text-ink font-semibold shadow-xs border border-border/80'
                    : 'text-ink-muted hover:text-ink'
                }`}
              >
                {act.replace('_', ' ')}
              </button>
            ))}
          </div>
        </CardHeader>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Timestamp</TableHead>
              <TableHead>Event</TableHead>
              <TableHead>Case / Payment</TableHead>
              <TableHead>Actor</TableHead>
              <TableHead>Transition</TableHead>
              <TableHead>Reasoning / Decision</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredEntries.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="py-12 text-center text-xs font-mono text-ink-muted">
                  No audit log entries recorded yet.
                </TableCell>
              </TableRow>
            ) : (
              filteredEntries.map((entry) => (
                <TableRow key={entry.entry_id}>
                  <TableCell className="font-mono text-xs text-ink-muted whitespace-nowrap">
                    {new Date(entry.timestamp).toLocaleString()}
                  </TableCell>
                  <TableCell className="font-mono text-xs font-semibold text-ink">
                    {entry.event_name}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    <span className="text-ink">{entry.case_id}</span>
                    <span className="text-[10px] text-ink-subtle block">{entry.paymentId}</span>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{entry.actor}</Badge>
                  </TableCell>
                  <TableCell className="font-mono text-[11px]">
                    <span className="text-ink-subtle">{entry.from_state || 'START'}</span>
                    <span className="text-ink-muted mx-1">{'->'}</span>
                    <span className="text-ink font-medium">{entry.to_state}</span>
                  </TableCell>
                  <TableCell className="text-xs text-ink max-w-md">
                    {entry.reason}
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
