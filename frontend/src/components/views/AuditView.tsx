'use client'

import React, { useMemo, useState } from 'react'
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  RefreshCw,
  Search,
  Sparkles,
} from 'lucide-react'
import { seedSimulation, type RecoveryCase } from '@/lib/api'
import { Button } from '@/components/ui/button'
import {
  formatCustomerName,
  formatDateTime,
  formatTime,
  humanizeToken,
} from '@/lib/format'

interface AuditViewProps {
  cases: RecoveryCase[]
  onRefresh?: () => void
  refreshing?: boolean
  onSelectCase?: (c: RecoveryCase) => void
}

interface EnrichedAuditEntry {
  entry_id: string
  case_id: string
  payment_id: string
  customer_id: string
  timestamp: string
  event_name: string
  actor: string
  reason: string
  cost_incurred_paise: number
  decision_inputs: Record<string, unknown>
  from_state?: string | null
  to_state?: string | null
}

function actionPillClass(eventName: string): string {
  const lower = eventName.toLowerCase()
  if (lower.includes('plan') || lower.includes('ai') || lower.includes('llm')) {
    return 'audit-pill audit-pill--ai'
  }
  if (
    lower.includes('executed') ||
    lower.includes('dispatch') ||
    lower.includes('retry') ||
    lower.includes('link')
  ) {
    return 'audit-pill audit-pill--action'
  }
  if (lower.includes('recovered') || lower.includes('captured')) {
    return 'audit-pill audit-pill--success'
  }
  if (
    lower.includes('escalat') ||
    lower.includes('breach') ||
    lower.includes('failed')
  ) {
    return 'audit-pill audit-pill--danger'
  }
  return 'audit-pill'
}

function actionLabel(eventName: string): string {
  const lower = eventName.toLowerCase()
  if (lower.includes('plan') || lower.includes('llm')) return 'AI plan'
  if (lower.includes('executed') || lower.includes('dispatch'))
    return 'Dispatch'
  if (lower.includes('recovered') || lower.includes('captured'))
    return 'Recovered'
  if (lower.includes('escalat')) return 'Escalated'
  if (lower.includes('holdout')) return 'Holdout'
  if (lower.includes('ingest') || lower.includes('created')) return 'Ingested'
  return humanizeToken(eventName)
}

function actorLabel(actor: string): string {
  return formatActorBadge(actor).label
}

function formatActorBadge(actor: string): {
  label: string
  sub: string
} {
  switch (actor) {
    case 'AGENT_LLM':
      return { label: 'AI planner', sub: 'Autonomous engine' }
    case 'ORCHESTRATOR':
    case 'SYSTEM':
      return { label: 'System engine', sub: 'State machine' }
    case 'POLICY_GATE':
      return { label: 'Policy gate', sub: 'Invariant guardrail' }
    case 'GATEWAY_WEBHOOK':
      return { label: 'Razorpay webhook', sub: 'Event relay' }
    case 'HUMAN_OPERATOR':
      return { label: 'Ops operator', sub: 'HITL reviewer' }
    default:
      return {
        label: humanizeToken(actor),
        sub: 'System entity',
      }
  }
}

export function AuditView({
  cases,
  onRefresh,
  refreshing = false,
  onSelectCase,
}: AuditViewProps) {
  const [actionFilter, setActionFilter] = useState<string>('')
  const [entityFilter, setEntityFilter] = useState<string>('')
  const [actorFilter, setActorFilter] = useState<string>('')
  const [searchQuery, setSearchQuery] = useState<string>('')
  const [expandedEntryId, setExpandedEntryId] = useState<string | null>(null)
  const [page, setPage] = useState<number>(1)
  const [isSeeding, setIsSeeding] = useState<boolean>(false)
  const perPage = 25

  const allEntries: EnrichedAuditEntry[] = useMemo(() => {
    const list: EnrichedAuditEntry[] = []
    for (const c of cases) {
      for (const e of c.audit_trail) {
        list.push({
          entry_id: e.entry_id,
          case_id: c.case_id,
          payment_id: c.failure_event.payment_id,
          customer_id: c.failure_event.customer_id,
          timestamp: e.timestamp,
          event_name: e.event_name,
          actor: e.actor,
          reason: (e.notes ?? e.reason) || '',
          cost_incurred_paise: e.cost_incurred_paise,
          decision_inputs: e.decision_inputs,
          from_state: e.from_state,
          to_state: e.to_state,
        })
      }
    }
    return list.sort(
      (a, b) =>
        new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
    )
  }, [cases])

  const availableActions = useMemo(
    () => Array.from(new Set(allEntries.map((e) => e.event_name))).sort(),
    [allEntries],
  )

  const casesById = useMemo(() => {
    const map = new Map<string, RecoveryCase>()
    for (const c of cases) map.set(c.case_id, c)
    return map
  }, [cases])

  const openCase = (caseId: string) => {
    const c = casesById.get(caseId)
    if (c && onSelectCase) onSelectCase(c)
  }

  const availableActors = useMemo(
    () => Array.from(new Set(allEntries.map((e) => e.actor))).sort(),
    [allEntries],
  )

  const filteredEntries = useMemo(() => {
    return allEntries.filter((entry) => {
      if (actionFilter && entry.event_name !== actionFilter) return false
      if (actorFilter && entry.actor !== actorFilter) return false
      if (entityFilter === 'case' && !entry.case_id) return false
      if (entityFilter === 'payment' && !entry.payment_id) return false

      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim()
        const matchId =
          entry.case_id.toLowerCase().includes(q) ||
          entry.payment_id.toLowerCase().includes(q) ||
          entry.customer_id.toLowerCase().includes(q) ||
          entry.entry_id.toLowerCase().includes(q) ||
          entry.reason.toLowerCase().includes(q)
        if (!matchId) return false
      }
      return true
    })
  }, [allEntries, actionFilter, actorFilter, entityFilter, searchQuery])

  const total = filteredEntries.length
  const totalPages = Math.ceil(total / perPage) || 1
  const paginatedEntries = useMemo(() => {
    const start = (page - 1) * perPage
    return filteredEntries.slice(start, start + perPage)
  }, [filteredEntries, page, perPage])

  const handleSearchSubmit = (e: React.SyntheticEvent) => {
    e.preventDefault()
    setPage(1)
  }

  return (
    <div className="h-full w-full min-w-0 space-y-5 overflow-y-auto">
      <div className="flex flex-col justify-between gap-3 border-b border-border pb-4 sm:flex-row sm:items-end">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">
            Audit Log
          </h1>
          <p className="mt-1 text-sm text-ink-muted">
            Immutable record of state changes, policy checks, outreach, and
            payment outcomes.
          </p>
        </div>

        {onRefresh ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onRefresh}
            disabled={refreshing}
            className="gap-2 self-start sm:self-auto"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`}
            />
            Refresh
          </Button>
        ) : null}
      </div>

      <div className="grid grid-cols-1 gap-3 rounded-panel border border-border bg-surface p-3 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-ink-muted">
            Action
          </label>
          <select
            value={actionFilter}
            onChange={(e) => {
              setActionFilter(e.target.value)
              setPage(1)
            }}
            className="field-input text-sm"
          >
            <option value="">All ({allEntries.length.toString()})</option>
            {availableActions.map((act) => (
              <option key={act} value={act}>
                {actionLabel(act)}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-ink-muted">
            Entity
          </label>
          <select
            value={entityFilter}
            onChange={(e) => {
              setEntityFilter(e.target.value)
              setPage(1)
            }}
            className="field-input text-sm"
          >
            <option value="">All entities</option>
            <option value="case">Cases</option>
            <option value="payment">Payments</option>
          </select>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-ink-muted">
            Actor
          </label>
          <select
            value={actorFilter}
            onChange={(e) => {
              setActorFilter(e.target.value)
              setPage(1)
            }}
            className="field-input text-sm"
          >
            <option value="">All actors</option>
            {availableActors.map((act) => (
              <option key={act} value={act}>
                {actorLabel(act)}
              </option>
            ))}
          </select>
        </div>

        <form onSubmit={handleSearchSubmit}>
          <label className="mb-1 block text-xs font-medium text-ink-muted">
            Search
          </label>
          <div className="flex gap-1.5">
            <input
              type="text"
              placeholder="Case, payment, customer..."
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value)
              }}
              className="field-input text-sm"
            />
            <Button type="submit" size="sm" variant="primary" className="px-3">
              <Search className="h-3.5 w-3.5" />
            </Button>
          </div>
        </form>
      </div>

      <div className="data-table-shell">
        <div className="overflow-x-auto">
          <table className="data-table w-full text-left">
            <thead className="audit-table-head">
              <tr>
                <th>Time</th>
                <th>Action</th>
                <th>Case / Payment</th>
                <th>Actor</th>
                <th>Summary</th>
                <th className="w-16 text-right">More</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50 bg-surface">
              {paginatedEntries.length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-4 py-10 text-center text-sm text-ink-muted"
                  >
                    <div className="flex flex-col items-center gap-3">
                      <p>No audit records match the current filters.</p>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={isSeeding}
                        onClick={() => {
                          setIsSeeding(true)
                          void seedSimulation(30, true)
                            .then(() => {
                              if (onRefresh) onRefresh()
                            })
                            .finally(() => {
                              setIsSeeding(false)
                            })
                        }}
                        className="gap-2"
                      >
                        <Sparkles className="h-3.5 w-3.5 text-accent" />
                        <span>
                          {isSeeding ? 'Seeding...' : 'Seed recovery batch'}
                        </span>
                      </Button>
                    </div>
                  </td>
                </tr>
              ) : (
                paginatedEntries.map((entry) => {
                  const isExpanded = expandedEntryId === entry.entry_id
                  const actorInfo = formatActorBadge(entry.actor)
                  const stateTransition =
                    entry.from_state && entry.to_state
                      ? `${entry.from_state} -> ${entry.to_state}`
                      : null

                  return (
                    <React.Fragment key={entry.entry_id}>
                      <tr
                        className="audit-row audit-row-compact cursor-pointer transition-colors"
                        onClick={() => {
                          setExpandedEntryId(isExpanded ? null : entry.entry_id)
                        }}
                      >
                        <td className="whitespace-nowrap text-ink-muted">
                          <div className="font-medium text-ink">
                            {formatTime(entry.timestamp)}
                          </div>
                          <div className="text-[11px]">
                            {formatDateTime(entry.timestamp).split(',')[0]}
                          </div>
                        </td>

                        <td>
                          <span className={actionPillClass(entry.event_name)}>
                            {actionLabel(entry.event_name)}
                          </span>
                        </td>

                        <td className="min-w-[10rem]">
                          <div className="font-medium text-ink">
                            {onSelectCase && casesById.has(entry.case_id) ? (
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  openCase(entry.case_id)
                                }}
                                className="font-mono text-xs text-accent underline decoration-accent/40 underline-offset-2 hover:decoration-accent"
                                title="Open case detail"
                              >
                                {entry.case_id}
                              </button>
                            ) : (
                              <span className="font-mono text-xs text-ink">
                                {entry.case_id}
                              </span>
                            )}
                          </div>
                          <div className="group/case relative font-mono text-[11px] text-ink-muted">
                            {onSelectCase && casesById.has(entry.case_id) ? (
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  openCase(entry.case_id)
                                }}
                                className="max-w-[12rem] truncate text-left text-accent underline decoration-accent/40 underline-offset-2 hover:decoration-accent"
                                title="Open case detail"
                              >
                                {entry.payment_id}
                              </button>
                            ) : (
                              entry.payment_id
                            )}
                          </div>
                        </td>

                        <td className="whitespace-nowrap text-ink">
                          <div className="group/actor relative inline-flex cursor-default items-center gap-1.5">
                            <span className="font-medium text-ink underline decoration-ink-muted decoration-dotted underline-offset-4">
                              {actorInfo.label}
                            </span>
                            <span className="rounded border border-border bg-surface-sunken px-1.5 py-0.5 text-[10px] font-semibold text-ink-muted uppercase">
                              {actorInfo.sub}
                            </span>

                            <div className="pointer-events-none absolute bottom-full left-0 z-50 mb-2 hidden w-64 flex-col gap-1 rounded-panel border border-border bg-surface p-3 text-xs text-ink shadow-lg group-hover/actor:flex">
                              <div className="flex items-center justify-between border-b border-border pb-1.5">
                                <span className="truncate text-xs font-semibold text-ink">
                                  {actorInfo.label}
                                </span>
                                <span className="rounded border border-accent/20 bg-accent-subtle px-1.5 py-0.5 font-mono text-[9px] font-bold text-accent uppercase">
                                  {entry.actor}
                                </span>
                              </div>
                              <div className="space-y-0.5 pt-0.5 text-[11px] text-ink-muted">
                                <p>
                                  <strong className="text-ink">
                                    Component:
                                  </strong>{' '}
                                  {actorInfo.sub}
                                </p>
                                <p>
                                  <strong className="text-ink">
                                    Audit ID:
                                  </strong>{' '}
                                  {entry.entry_id.slice(0, 12)}
                                </p>
                                <p>
                                  <strong className="text-ink">
                                    Case scope:
                                  </strong>{' '}
                                  {entry.case_id.slice(0, 8)}
                                </p>
                                {entry.cost_incurred_paise > 0 ? (
                                  <p className="text-failed">
                                    <strong className="text-ink">
                                      Cost incurred:
                                    </strong>{' '}
                                    INR{' '}
                                    {(entry.cost_incurred_paise / 100).toFixed(
                                      2,
                                    )}
                                  </p>
                                ) : null}
                              </div>
                            </div>
                          </div>
                        </td>

                        <td className="max-w-md">
                          <p className="line-clamp-2 text-[13px] text-ink-muted">
                            {entry.reason ||
                              stateTransition ||
                              entry.event_name}
                          </p>
                          {entry.cost_incurred_paise > 0 ? (
                            <p className="mt-0.5 text-[11px] font-medium text-failed">
                              Cost INR{' '}
                              {(entry.cost_incurred_paise / 100).toFixed(2)}
                            </p>
                          ) : null}
                        </td>

                        <td className="text-right">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation()
                              setExpandedEntryId(
                                isExpanded ? null : entry.entry_id,
                              )
                            }}
                            className="inline-flex cursor-pointer items-center gap-0.5 text-xs font-medium text-accent hover:underline"
                          >
                            {isExpanded ? (
                              <>
                                Hide
                                <ChevronUp className="h-3.5 w-3.5" />
                              </>
                            ) : (
                              <>
                                View
                                <ChevronDown className="h-3.5 w-3.5" />
                              </>
                            )}
                          </button>
                        </td>
                      </tr>

                      {isExpanded ? (
                        <tr className="bg-surface-sunken/50">
                          <td colSpan={6} className="px-3 py-2">
                            <div className="rounded-control border border-border bg-surface p-3 text-xs text-ink">
                              <div className="mb-2 grid gap-2 sm:grid-cols-3">
                                <div>
                                  <span className="text-ink-muted">
                                    Customer
                                  </span>
                                  <p className="font-medium">
                                    {formatCustomerName(entry.customer_id)}
                                  </p>
                                </div>
                                <div>
                                  <span className="text-ink-muted">
                                    Audit ID
                                  </span>
                                  <p className="font-mono text-[11px] break-all">
                                    {entry.entry_id}
                                  </p>
                                </div>
                                <div>
                                  <span className="text-ink-muted">
                                    Transition
                                  </span>
                                  <p className="font-medium">
                                    {stateTransition ?? 'N/A'}
                                  </p>
                                </div>
                              </div>
                              {onSelectCase && casesById.has(entry.case_id) ? (
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    openCase(entry.case_id)
                                  }}
                                  className="mb-2 inline-flex items-center gap-1 text-xs font-medium text-accent underline decoration-accent/40 underline-offset-2 hover:decoration-accent"
                                >
                                  Open full transaction
                                  <ChevronRight className="h-3 w-3" />
                                </button>
                              ) : null}
                              <pre className="overflow-x-auto rounded-control bg-surface-sunken p-2 text-[11px] text-ink-muted">
                                {JSON.stringify(entry.decision_inputs, null, 2)}
                              </pre>
                            </div>
                          </td>
                        </tr>
                      ) : null}
                    </React.Fragment>
                  )
                })
              )}
            </tbody>
          </table>
        </div>

        <div className="flex items-center justify-between border-t border-border bg-surface-sunken/30 px-3 py-2">
          <p className="text-xs text-ink-muted">
            Showing {paginatedEntries.length.toString()} of {total.toString()}{' '}
            records
          </p>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="px-2"
              onClick={() => {
                setPage((p) => Math.max(1, p - 1))
              }}
              disabled={page <= 1}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="text-xs font-medium text-ink">
              {page.toString()} / {totalPages.toString()}
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="px-2"
              onClick={() => {
                setPage((p) => Math.min(totalPages, p + 1))
              }}
              disabled={page >= totalPages}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
