'use client'

import React, { useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  ArrowUpDown,
  Bot,
  CheckCircle2,
  Eye,
  HelpCircle,
  Lightbulb,
  Percent,
  Phone,
  RefreshCw,
  Route,
  Search,
  ShieldAlert,
  Smartphone,
  UserCheck,
  X,
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { RailBadge } from '@/components/ui/BrandIcons'
import { HighlightMoney } from '@/components/ui/HighlightMoney'
import { SkeletonRow } from '@/components/ui/skeleton'
import { formatCustomerName } from '@/lib/format'

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

type SortField =
  'expected_recoverable_value_paise' | 'amount_paise' | 'created_at'

/** Maps recommended_action text to an icon; unmatched text falls back to
 * the neutral default instead of breaking. */
function recommendedActionDisplay(action: string): {
  Icon: React.ComponentType<{ className?: string }>
  colorClass: string
} {
  const lower = action.toLowerCase()
  if (lower.includes('review')) {
    return { Icon: Eye, colorClass: 'text-failed' }
  }
  if (lower.includes('discount')) {
    return { Icon: Percent, colorClass: 'text-recovered' }
  }
  if (lower.includes('degraded') || lower.includes('alternate rail')) {
    return { Icon: Route, colorClass: 'text-escalated' }
  }
  if (lower.includes('upi')) {
    return { Icon: Smartphone, colorClass: 'text-accent' }
  }
  if (lower.includes('phone') || lower.includes('outreach')) {
    return { Icon: Phone, colorClass: 'text-accent' }
  }
  if (lower.includes('ai recovery plan')) {
    return { Icon: Bot, colorClass: 'text-accent' }
  }
  if (lower.includes('retry')) {
    return { Icon: RefreshCw, colorClass: 'text-accent' }
  }
  return { Icon: Lightbulb, colorClass: 'text-accent' }
}

export function EscalationsQueuePanel({
  onSelectCase,
  onActionComplete,
}: EscalationsQueuePanelProps) {
  const [queue, setQueue] = useState<EscalationQueueItem[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [approvingId, setApprovingId] = useState<string | null>(null)
  const [approvalSuccess, setApprovalSuccess] = useState<string | null>(null)
  const [approvalError, setApprovalError] = useState<string | null>(null)

  const [searchQuery, setSearchQuery] = useState<string>('')
  const [railFilter, setRailFilter] = useState<string>('all')
  const [sortBy, setSortBy] = useState<SortField>(
    'expected_recoverable_value_paise',
  )
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

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
      setApprovalError(null)
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
    } catch (err: unknown) {
      setApprovalError(err instanceof Error ? err.message : 'Approval failed')
      // Row may be stale (case already resolved elsewhere) -- refresh it.
      void fetchQueue()
    } finally {
      setApprovingId(null)
    }
  }

  const rails = useMemo(
    () => Array.from(new Set(queue.map((q) => q.payment_rail))).sort(),
    [queue],
  )

  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    let rows = queue.filter((item) => {
      if (railFilter !== 'all' && item.payment_rail !== railFilter) return false
      if (!q) return true
      return (
        item.case_id.toLowerCase().includes(q) ||
        item.payment_id.toLowerCase().includes(q) ||
        formatCustomerName(item.customer_id).toLowerCase().includes(q) ||
        item.payment_rail.toLowerCase().includes(q) ||
        item.escalation_reason.toLowerCase().includes(q) ||
        item.recommended_action.toLowerCase().includes(q)
      )
    })

    rows = [...rows].sort((a, b) => {
      let diff: number
      if (sortBy === 'created_at') {
        diff =
          new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
      } else {
        diff = a[sortBy] - b[sortBy]
      }
      return sortDir === 'asc' ? diff : -diff
    })
    return rows
  }, [queue, searchQuery, railFilter, sortBy, sortDir])

  const totalEv = queue.reduce(
    (acc, q) => acc + q.expected_recoverable_value_paise,
    0,
  )

  const hasActiveFilters = searchQuery.trim() !== '' || railFilter !== 'all'

  const clearFilters = () => {
    setSearchQuery('')
    setRailFilter('all')
  }

  return (
    <Card className="border-escalated/40 bg-surface">
      <CardHeader className="border-b border-border/60 bg-escalated-subtle/10 p-5 pb-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <ShieldAlert className="h-5 w-5 text-escalated" />
              <CardTitle className="text-lg text-ink">
                Awaiting Approval (EV-Prioritized)
              </CardTitle>
            </div>
            <CardDescription className="mt-1 text-xs">
              Search and filter the operator queue. Surfaces the exact
              root-cause constraint, deterministic policy boundary, and
              recommended operator action.
            </CardDescription>
          </div>

          <div className="flex items-center gap-3 self-start text-xs sm:self-auto">
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

      {approvalError && (
        <p className="border-status-failed/40 bg-status-failed/10 flex items-start gap-2 border-b p-3 text-xs text-ink">
          <AlertTriangle
            className="mt-0.5 h-3.5 w-3.5 shrink-0"
            aria-hidden="true"
          />
          {approvalError}
        </p>
      )}

      <CardContent className="p-0">
        {loading ? (
          <div className="space-y-2 p-4">
            <SkeletonRow />
            <SkeletonRow />
            <SkeletonRow />
          </div>
        ) : queue.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-12 text-center text-xs text-ink-muted">
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
          <div>
            {/* Filter Bar */}
            <div className="flex flex-col gap-3 border-b border-border/60 p-4 md:flex-row md:items-center md:justify-between">
              <div className="relative flex-1 md:max-w-sm">
                <Search className="absolute top-2.5 left-3 h-4 w-4 text-ink-subtle" />
                <input
                  type="text"
                  placeholder="Search case, payment, customer, rail, or reason..."
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value)
                  }}
                  className="w-full rounded-control border border-border bg-surface-sunken py-2 pr-8 pl-9 text-sm text-ink placeholder:text-ink-subtle focus:border-accent focus:outline-hidden"
                />
                {searchQuery && (
                  <button
                    type="button"
                    onClick={() => {
                      setSearchQuery('')
                    }}
                    className="absolute top-2.5 right-2 cursor-pointer text-ink-muted hover:text-ink"
                    aria-label="Clear search"
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <select
                  value={railFilter}
                  onChange={(e) => {
                    setRailFilter(e.target.value)
                  }}
                  aria-label="Filter by payment rail"
                  className="cursor-pointer rounded-control border border-border bg-surface-sunken px-2.5 py-2 text-xs font-medium text-ink focus:border-accent focus:outline-hidden"
                >
                  <option value="all">All rails</option>
                  {rails.map((rail) => (
                    <option key={rail} value={rail}>
                      {rail}
                    </option>
                  ))}
                </select>

                <div className="flex items-center gap-1 rounded-control border border-border bg-surface-sunken px-2 py-1 text-xs">
                  <ArrowUpDown className="h-3 w-3 text-ink-subtle" />
                  <select
                    value={sortBy}
                    onChange={(e) => {
                      setSortBy(e.target.value as SortField)
                    }}
                    aria-label="Sort by field"
                    className="cursor-pointer border-none bg-transparent text-xs text-ink focus:outline-hidden"
                  >
                    <option value="expected_recoverable_value_paise">
                      Expected EV
                    </option>
                    <option value="amount_paise">Face Amount</option>
                    <option value="created_at">Created Time</option>
                  </select>
                  <select
                    value={sortDir}
                    onChange={(e) => {
                      setSortDir(e.target.value as 'asc' | 'desc')
                    }}
                    aria-label="Sort direction"
                    className="cursor-pointer border-none bg-transparent text-xs font-bold text-ink focus:outline-hidden"
                  >
                    <option value="desc">DESC</option>
                    <option value="asc">ASC</option>
                  </select>
                </div>

                {hasActiveFilters && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={clearFilters}
                    className="text-xs text-ink-muted"
                  >
                    Clear
                  </Button>
                )}
              </div>
            </div>

            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[170px]">Case / Payment ID</TableHead>
                  <TableHead>Customer</TableHead>
                  <TableHead>Rail</TableHead>
                  <TableHead className="min-w-[260px]">
                    Why This Needs Human Action
                  </TableHead>
                  <TableHead className="min-w-[200px]">
                    Recommended Action
                  </TableHead>
                  <TableHead className="text-right">
                    Expected Yield (EV)
                  </TableHead>
                  <TableHead className="text-center">Attempts</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={8}
                      className="h-32 text-center text-sm text-ink-muted"
                    >
                      No escalations matched the current search filters.
                    </TableCell>
                  </TableRow>
                ) : (
                  filtered.map((item) => {
                    const isApproving = approvingId === item.case_id
                    const isSuccess = approvalSuccess === item.case_id
                    const winRate = Math.round(
                      item.estimated_recovery_probability * 100,
                    )

                    return (
                      <TableRow
                        key={item.case_id}
                        onClick={() => {
                          if (onSelectCase) onSelectCase(item.case_id)
                        }}
                        className="cursor-pointer align-top transition-colors hover:bg-surface-sunken/60"
                      >
                        {/* Case / Payment */}
                        <TableCell className="text-xs">
                          <div className="flex items-center gap-1.5 font-semibold text-ink">
                            <span className="cursor-pointer text-accent hover:underline">
                              {item.case_id.slice(0, 10)}...
                            </span>
                          </div>
                          <div className="mt-0.5 text-[11px] text-ink-subtle">
                            {item.payment_id}
                          </div>
                          <div className="mt-0.5 text-[11px] text-ink-muted">
                            {new Date(item.created_at).toLocaleDateString()}
                          </div>
                        </TableCell>

                        {/* Customer */}
                        <TableCell className="text-xs text-ink-muted">
                          {formatCustomerName(item.customer_id)}
                        </TableCell>

                        {/* Rail */}
                        <TableCell>
                          <RailBadge rail={item.payment_rail} />
                        </TableCell>

                        {/* Escalation reason - vertical detail */}
                        <TableCell>
                          <div className="flex items-start gap-2 text-xs">
                            <HelpCircle className="mt-0.5 h-4 w-4 shrink-0 text-escalated" />
                            <p className="leading-relaxed text-ink">
                              <HighlightMoney text={item.escalation_reason} />
                            </p>
                          </div>
                        </TableCell>

                        {/* Recommended action - vertical detail */}
                        <TableCell>
                          <div className="flex items-start gap-2 text-xs">
                            {(() => {
                              const { Icon, colorClass } =
                                recommendedActionDisplay(
                                  item.recommended_action,
                                )
                              return (
                                <Icon
                                  className={`mt-0.5 h-4 w-4 shrink-0 ${colorClass}`}
                                />
                              )
                            })()}
                            <div className="space-y-1">
                              <p className="font-semibold text-ink">
                                {item.recommended_action}
                              </p>
                              {item.recommended_discount_bps > 0 && (
                                <Badge
                                  variant="outline"
                                  className="border-accent text-[10px] text-accent"
                                >
                                  +
                                  {(
                                    item.recommended_discount_bps / 100
                                  ).toFixed(0)}
                                  % Discount
                                </Badge>
                              )}
                              <p className="text-[11px] text-ink-subtle">
                                Face {formatINR(item.amount_paise)} @ {winRate}%
                                win rate
                              </p>
                            </div>
                          </div>
                        </TableCell>

                        {/* EV */}
                        <TableCell className="text-right">
                          <span className="money text-sm font-bold text-recovered">
                            {formatINR(item.expected_recoverable_value_paise)}
                          </span>
                        </TableCell>

                        {/* Attempts */}
                        <TableCell className="text-center text-xs text-ink-muted">
                          {item.attempts_count}
                        </TableCell>

                        {/* Actions */}
                        <TableCell className="text-right">
                          <Button
                            size="sm"
                            variant="primary"
                            disabled={isApproving}
                            onClick={(e) => {
                              e.stopPropagation()
                              void handleQuickApprove(item)
                            }}
                            className="h-auto gap-1.5 bg-accent py-2 text-xs text-white hover:bg-accent/90"
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
                                  : 'Approve'}
                            </span>
                          </Button>
                        </TableCell>
                      </TableRow>
                    )
                  })
                )}
              </TableBody>
            </Table>

            {filtered.length > 0 && (
              <div className="border-t border-border/60 px-4 py-2 text-right text-[11px] text-ink-muted">
                Showing {filtered.length.toString()} of{' '}
                {queue.length.toString()} escalation(s)
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
