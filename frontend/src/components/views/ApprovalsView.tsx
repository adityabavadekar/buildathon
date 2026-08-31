'use client'

import React from 'react'
import { ClipboardCheck } from 'lucide-react'
import type { RecoveryCase } from '@/lib/api'
import { EscalationsQueuePanel } from '@/components/recovery/EscalationsQueuePanel'

interface ApprovalsViewProps {
  cases: RecoveryCase[]
  onSelectCase: (caseItem: RecoveryCase) => void
  onActionComplete?: () => void
}

export function ApprovalsView({
  cases,
  onSelectCase,
  onActionComplete,
}: ApprovalsViewProps) {
  const escalatedCount = cases.filter(
    (c) => c.state === 'ESCALATED',
  ).length

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 font-mono text-lg font-semibold tracking-tight text-ink">
            <ClipboardCheck className="h-5 w-5 text-escalated" />
            Awaiting Approval
          </h2>
          <p className="mt-1 text-xs text-ink-subtle">
            Escalated transactions that need an operator decision before the
            engine may act. Only escalated cases appear here.
          </p>
        </div>
        <span className="rounded-control border border-escalated/40 bg-escalated-subtle/10 px-2.5 py-1 font-mono text-xs font-semibold text-escalated">
          {escalatedCount.toString()} escalated
        </span>
      </div>

      <EscalationsQueuePanel
        onSelectCase={(caseId) => {
          const found = cases.find((item) => item.case_id === caseId)
          if (found) onSelectCase(found)
        }}
        onActionComplete={onActionComplete}
      />
    </div>
  )
}
