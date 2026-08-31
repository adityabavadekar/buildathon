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
        item.recommended_discount_bps > 0
          ? item.recommended_discount_bps
          : undefined,
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

  const totalEv = queue.reduce(
    (acc, q) => acc + q.expected_recoverable_value_paise,
    0,
  )

  return (
    <Card className="border-escalated/40 bg-surface">
      <CardHeader className="border-b border-border/60 bg-escalated-subtle/10 p-5 pb-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <ShieldAlert className="h-5 w-5 text-escalated" />
              <CardTitle className="font-mono text-lg text-ink">
                Operator Escalation Queue (EV-Prioritized)
              </CardTitle>
            </div>
            <CardDescription className="mt-1 text-xs">
              Surfaces the exact root-cause constraint, deterministic policy
              boundary, and recommended operator action.
            </CardDescription>
          </div>

          <div className="flex items-center gap-3 self-start font-mono text-xs sm:self-auto">
            <div className="rounded-control border border-border bg-surface p-2.5">
              <span className="block text-[10px] text-ink-muted uppercase">
                Queue Size
              </span>
              <span className="text-base font-bold text-escalated">
                {queue.length.toString()} Cases
              </span>
            </div>
            <div className="rounded-control border border-recovered/30 bg-recovered/10 p-2.5">
              <span className="block text-[10px] font-semibold text-recovered uppercase">
                Total Recoverable EV
              </span>
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
              <RefreshCw
                className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`}
              />
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="p-0">
        {loading ? (
          <div className="space-y-2 p-4">
            <SkeletonRow />
            <SkeletonRow />
            <SkeletonRow />
          </div>
        ) : queue.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-12 text-center font-mono text-xs text-ink-muted">
            <CheckCircle2 className="h-8 w-8 text-recovered/60" />
            <p className="font-semibold text-ink">
              Zero Operator Escalations Pending
            </p>
            <p className="text-ink-muted">
              All active failures are being resolved autonomously within
              deterministic safety bounds.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-border/60">
            {queue.map((item, idx) => {
              const isApproving = approvingId === item.case_id
              const isSuccess = approvalSuccess === item.case_id

              return (
                <div
                  key={item.case_id}
                  className="flex flex-col justify-between gap-4 p-4 transition-colors hover:bg-surface-sunken/40 sm:p-5 lg:flex-row lg:items-center"
                >
                  {/* Left Column: Case Meta & Reason */}
                  <div className="min-w-0 flex-1 space-y-2">
                    <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
                      <span className="rounded-control border border-border bg-surface-sunken px-2 py-0.5 font-bold text-ink">
                        #{(idx + 1).toString()} EV Ranked
                      </span>
                      <span
                        className="cursor-pointer font-bold text-accent hover:underline"
                        onClick={() => {
                          if (onSelectCase) onSelectCase(item.case_id)
                        }}
                      >
                        {item.case_id.slice(0, 10)}...
                      </span>
                      <RailBadge rail={item.payment_rail} />
                      <span className="text-ink-subtle">{item.payment_id}</span>
                      <span className="text-ink-muted">
                        ({item.customer_id})
                      </span>
                    </div>

                    {/* Surfaced Human Reason */}
                    <div className="flex items-start gap-2 rounded-control border border-escalated/30 bg-escalated-subtle/30 p-2.5 text-xs">
                      <HelpCircle className="mt-0.5 h-4 w-4 shrink-0 text-escalated" />
                      <div className="space-y-0.5">
                        <span className="block font-mono text-[10px] font-bold tracking-wider text-escalated uppercase">
                          Why This Needs Human Action:
                        </span>
                        <p className="text-xs leading-relaxed text-ink">
                          {item.escalation_reason}
                        </p>
                      </div>
                    </div>

                    {/* Recommended Action */}
                    <div className="flex items-center gap-2 rounded-control border border-accent/20 bg-accent/5 p-2.5 text-xs">
                      <Lightbulb className="h-4 w-4 shrink-0 text-accent" />
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-[10px] font-bold tracking-wider text-accent uppercase">
                          Recommended Action:
                        </span>
                        <span className="font-semibold text-ink">
                          {item.recommended_action}
                        </span>
                        {item.recommended_discount_bps > 0 && (
                          <Badge
                            variant="outline"
                            className="border-accent text-[10px] text-accent"
                          >
                            +{(item.recommended_discount_bps / 100).toFixed(0)}%
                            Discount
                          </Badge>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Right Column: Financial EV & Execution CTA */}
                  <div className="flex shrink-0 items-end justify-between gap-3 border-t pt-3 font-mono sm:flex-row sm:justify-end lg:flex-col lg:border-t-0 lg:pt-0">
                    <div className="text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <span className="text-xs text-ink-muted">
                          Expected Yield (EV):
                        </span>
                        <span className="text-base font-bold text-recovered">
                          {formatINR(item.expected_recoverable_value_paise)}
                        </span>
                      </div>
                      <div className="text-[11px] text-ink-subtle">
                        Face: {formatINR(item.amount_paise)} @{' '}
                        {(item.estimated_recovery_probability * 100).toFixed(0)}
                        % win rate
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
                        className="gap-1.5 bg-accent font-mono text-xs text-white hover:bg-accent/90"
                      >
                        {isApproving ? (
                          <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                        ) : isSuccess ? (
                          <CheckCircle2 className="h-3.5 w-3.5 text-recovered" />
                        ) : (
                          <UserCheck className="h-3.5 w-3.5" />
                        )}
                        <span>
                          {isApproving
                            ? 'Executing...'
                            : isSuccess
                              ? 'Approved!'
                              : 'Approve Action'}
                        </span>
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
