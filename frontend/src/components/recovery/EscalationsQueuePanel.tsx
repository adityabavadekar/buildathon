'use client'

import React, { useEffect, useState } from 'react'
import {
  CheckCircle2,
  HelpCircle,
  Lightbulb,
  RefreshCw,
  ShieldAlert,
  UserCheck,
} from 'lucide-react'
import {
  approveCase,
  getEscalationQueue,
  type EscalationQueueItem,
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
import { RailBadge } from '@/components/ui/BrandIcons'
import { SkeletonRow } from '@/components/ui/skeleton'

interface EscalationsQueuePanelProps {
  onSelectCase?: (caseId: string) => void
  onActionComplete?: () => void
}

function formatINR(paise: number): string {
  const rupees = paise / 100
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(rupees)
}

export function EscalationsQueuePanel({
  onSelectCase,
  onActionComplete,
}: EscalationsQueuePanelProps) {
  const [queue, setQueue] = useState<EscalationQueueItem[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [approvingId, setApprovingId] = useState<string | null>(null)
  const [approvalSuccess, setApprovalSuccess] = useState<string | null>(null)

  const fetchQueue = async () => {
    try {
      setLoading(true)
      const data = await getEscalationQueue()
      setQueue(data)
    } catch {
      // Handled gracefully
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let active = true
    const timer = setTimeout(() => {
      if (active) void fetchQueue()
    }, 0)
    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [])

  const handleQuickApprove = async (item: EscalationQueueItem) => {
    try {
      setApprovingId(item.case_id)
      await approveCase(
        item.case_id,
        `Approved recommended operator action: ${item.recommended_action}`,
        item.recommended_discount_bps > 0 ? item.recommended_discount_bps : undefined
      )
      setApprovalSuccess(item.case_id)
      setTimeout(() => {
        setApprovalSuccess(null)
      }, 3000)
      void fetchQueue()
      if (onActionComplete) onActionComplete()
    } finally {
      setApprovingId(null)
    }
  }

  const totalEv = queue.reduce((acc, q) => acc + q.expected_recoverable_value_paise, 0)

  return (
    <Card className="border-escalated/40 bg-surface">
      <CardHeader className="p-5 pb-3 border-b border-border/60 bg-escalated-subtle/10">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <ShieldAlert className="h-5 w-5 text-escalated" />
              <CardTitle className="text-lg font-mono text-ink">
                Operator Escalation Queue (EV-Prioritized)
              </CardTitle>
            </div>
            <CardDescription className="text-xs mt-1">
              Surfaces the exact root-cause constraint, deterministic policy boundary, and recommended operator action.
            </CardDescription>
          </div>

          <div className="flex items-center gap-3 self-start sm:self-auto font-mono text-xs">
            <div className="p-2.5 rounded-control bg-surface border border-border">
              <span className="text-[10px] text-ink-muted block uppercase">Queue Size</span>
              <span className="text-base font-bold text-escalated">
                {queue.length.toString()} Cases
              </span>
            </div>
            <div className="p-2.5 rounded-control bg-recovered/10 border border-recovered/30">
              <span className="text-[10px] text-recovered block uppercase font-semibold">Total Recoverable EV</span>
              <span className="text-base font-bold text-recovered">
                {formatINR(totalEv)}
              </span>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                void fetchQueue()
              }}
              disabled={loading}
              className="h-9 px-3"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="p-0">
        {loading ? (
          <div className="p-4 space-y-2">
            <SkeletonRow />
            <SkeletonRow />
            <SkeletonRow />
          </div>
        ) : queue.length === 0 ? (
          <div className="py-12 text-center text-xs font-mono text-ink-muted flex flex-col items-center justify-center gap-2">
            <CheckCircle2 className="h-8 w-8 text-recovered/60" />
            <p className="font-semibold text-ink">Zero Operator Escalations Pending</p>
            <p className="text-ink-muted">All active failures are being resolved autonomously within deterministic safety bounds.</p>
          </div>
        ) : (
          <div className="divide-y divide-border/60">
            {queue.map((item, idx) => {
              const isApproving = approvingId === item.case_id
              const isSuccess = approvalSuccess === item.case_id

              return (
                <div
                  key={item.case_id}
                  className="p-4 sm:p-5 hover:bg-surface-sunken/40 transition-colors flex flex-col lg:flex-row lg:items-center justify-between gap-4"
                >
                  {/* Left Column: Case Meta & Reason */}
                  <div className="space-y-2 flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
                      <span className="font-bold text-ink bg-surface-sunken px-2 py-0.5 rounded-control border border-border">
                        #{(idx + 1).toString()} EV Ranked
                      </span>
                      <span
                        className="font-bold text-accent hover:underline cursor-pointer"
                        onClick={() => {
                          if (onSelectCase) onSelectCase(item.case_id)
                        }}
                      >
                        {item.case_id.slice(0, 10)}...
                      </span>
                      <RailBadge rail={item.payment_rail} />
                      <span className="text-ink-subtle">{item.payment_id}</span>
                      <span className="text-ink-muted">({item.customer_id})</span>
                    </div>

                    {/* Surfaced Human Reason */}
                    <div className="flex items-start gap-2 bg-escalated-subtle/30 border border-escalated/30 rounded-control p-2.5 text-xs">
                      <HelpCircle className="h-4 w-4 text-escalated shrink-0 mt-0.5" />
                      <div className="space-y-0.5">
                        <span className="font-bold text-escalated uppercase text-[10px] tracking-wider block font-mono">
                          Why This Needs Human Action:
                        </span>
                        <p className="text-ink text-xs leading-relaxed">
                          {item.escalation_reason}
                        </p>
                      </div>
                    </div>

                    {/* Recommended Action */}
                    <div className="flex items-center gap-2 bg-accent/5 border border-accent/20 rounded-control p-2.5 text-xs">
                      <Lightbulb className="h-4 w-4 text-accent shrink-0" />
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-bold text-accent uppercase text-[10px] tracking-wider font-mono">
                          Recommended Action:
                        </span>
                        <span className="text-ink font-semibold">
                          {item.recommended_action}
                        </span>
                        {item.recommended_discount_bps > 0 && (
                          <Badge variant="outline" className="text-[10px] border-accent text-accent">
                            +{(item.recommended_discount_bps / 100).toFixed(0)}% Discount
                          </Badge>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Right Column: Financial EV & Execution CTA */}
                  <div className="flex sm:flex-row lg:flex-col items-end justify-between sm:justify-end gap-3 shrink-0 font-mono border-t lg:border-t-0 pt-3 lg:pt-0">
                    <div className="text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <span className="text-xs text-ink-muted">Expected Yield (EV):</span>
                        <span className="text-base font-bold text-recovered">
                          {formatINR(item.expected_recoverable_value_paise)}
                        </span>
                      </div>
                      <div className="text-[11px] text-ink-subtle">
                        Face: {formatINR(item.amount_paise)} @ {(item.estimated_recovery_probability * 100).toFixed(0)}% win rate
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        variant="primary"
                        disabled={isApproving}
                        onClick={() => {
                          void handleQuickApprove(item)
                        }}
                        className="gap-1.5 text-xs font-mono bg-accent text-white hover:bg-accent/90"
                      >
                        {isApproving ? (
                          <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                        ) : isSuccess ? (
                          <CheckCircle2 className="h-3.5 w-3.5 text-recovered" />
                        ) : (
                          <UserCheck className="h-3.5 w-3.5" />
                        )}
                        <span>{isApproving ? 'Executing...' : isSuccess ? 'Approved!' : 'Approve Action'}</span>
                      </Button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
