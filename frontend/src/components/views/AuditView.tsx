'use client'

import React, { useMemo, useState } from 'react'
import {
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  FileText,
  Radio,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
  Zap,
} from 'lucide-react'
import { seedSimulation, type RecoveryCase } from '@/lib/api'
import { Button } from '@/components/ui/button'

interface AuditViewProps {
  cases: RecoveryCase[]
  onRefresh?: () => void
  refreshing?: boolean
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

export function AuditView({
  cases,
  onRefresh,
  refreshing = false,
}: AuditViewProps) {
  const [actionFilter, setActionFilter] = useState<string>('')
  const [entityFilter, setEntityFilter] = useState<string>('')
  const [actorFilter, setActorFilter] = useState<string>('')
  const [searchQuery, setSearchQuery] = useState<string>('')
  const [expandedEntryId, setExpandedEntryId] = useState<string | null>(null)
  const [page, setPage] = useState<number>(1)
  const [isSeeding, setIsSeeding] = useState<boolean>(false)
  const perPage = 15

  // Flatten all case audit trails chronologically
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
      (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    )
  }, [cases])

  // Extract dynamic action and actor lists from real ingested data (NO hardcoding)
  const availableActions = useMemo(() => {
    return Array.from(new Set(allEntries.map((e) => e.event_name))).sort()
  }, [allEntries])

  const availableActors = useMemo(() => {
    return Array.from(new Set(allEntries.map((e) => e.actor))).sort()
  }, [allEntries])

  // Filtered dataset
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
          entry.entry_id.toLowerCase().includes(q)
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

  const formatActionBadge = (eventName: string) => {
    const lower = eventName.toLowerCase()
    if (lower.includes('plan') || lower.includes('ai') || lower.includes('llm')) {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-bold bg-purple-500/15 text-purple-600 border border-purple-500/30">
          <Bot className="h-3 w-3" />
          AI STRATEGY PLAN
        </span>
      )
    }
    if (lower.includes('executed') || lower.includes('dispatch') || lower.includes('retry') || lower.includes('link')) {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-bold bg-emerald-500/15 text-emerald-600 border border-emerald-500/30">
          <Zap className="h-3 w-3" />
          INTERVENTION DISPATCH
        </span>
      )
    }
    if (lower.includes('recovered') || lower.includes('captured')) {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-bold bg-green-500/15 text-recovered border border-green-500/30">
          <CheckCircle2 className="h-3 w-3" />
          PAYMENT RECOVERED
        </span>
      )
    }
    if (lower.includes('escalat') || lower.includes('breach')) {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-bold bg-rose-500/15 text-rose-600 border border-rose-500/30">
          <ShieldAlert className="h-3 w-3" />
          SAFETY ESCALATION
        </span>
      )
    }
    if (lower.includes('holdout')) {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-bold bg-slate-500/15 text-slate-500 border border-slate-500/30">
          <Radio className="h-3 w-3" />
          HOLDOUT CONTROL
        </span>
      )
    }
    if (lower.includes('ingest') || lower.includes('created') || lower.includes('failed')) {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-bold bg-blue-500/15 text-blue-600 border border-blue-500/30">
          <FileText className="h-3 w-3" />
          FAILURE INGESTED
        </span>
      )
    }
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-mono font-medium bg-surface-sunken text-ink border border-border">
        {eventName.replace(/[._]/g, ' ').toUpperCase()}
      </span>
    )
  }

  const formatActorBadge = (actor: string) => {
    switch (actor) {
      case 'AGENT_LLM':
        return { label: 'AI Planner', sub: 'Autonomous Engine', type: 'ai' }
      case 'ORCHESTRATOR':
      case 'SYSTEM':
        return { label: 'System Engine', sub: 'State Machine', type: 'system' }
      case 'POLICY_GATE':
        return { label: 'Policy Gate', sub: 'Invariant Guardrail', type: 'policy' }
      case 'GATEWAY_WEBHOOK':
        return { label: 'Razorpay Webhook', sub: 'Event Relay', type: 'webhook' }
      case 'HUMAN_OPERATOR':
        return { label: 'Ops Operator', sub: 'HITL Reviewer', type: 'human' }
      default:
        return { label: actor.replace('_', ' '), sub: 'System Entity', type: 'default' }
    }
  }

  const handleSearchSubmit = (e: React.SyntheticEvent) => {
    e.preventDefault()
    setPage(1)
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto h-full overflow-y-auto">
      {/* 1. Header with Forensic Tag & Live Refresh */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-ink">
              Operational Forensic Audit Trail
            </h1>
            <span className="text-xs font-mono font-semibold bg-accent-subtle text-accent border border-accent/20 px-2.5 py-0.5 rounded-full">
              Immutable Forensic Log
            </span>
          </div>
          <p className="text-sm text-ink-muted mt-1">
            Tamper-evident record of all AI diagnosis formulations, state transitions, policy evaluations, and payment captures.
          </p>
        </div>

        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-xs font-semibold rounded-xl bg-surface border border-border hover:bg-surface-sunken transition-colors shadow-sm self-start sm:self-auto cursor-pointer"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        )}
      </div>

      {/* 2. Filter Matrix */}
      <div className="bg-surface border border-border rounded-2xl p-4 shadow-sm space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
          {/* Action Filter */}
          <div>
            <label className="text-[11px] font-bold text-ink-muted uppercase tracking-wider block mb-1.5">
              Action Type
            </label>
            <select
              value={actionFilter}
              onChange={(e) => {
                setActionFilter(e.target.value)
                setPage(1)
              }}
              className="w-full bg-surface-sunken border border-border text-ink text-xs rounded-xl px-3 py-2 focus:outline-none focus:ring-1 focus:ring-accent"
            >
              <option value="">All Actions ({allEntries.length.toString()})</option>
              {availableActions.map((act) => (
                <option key={act} value={act}>
                  {act}
                </option>
              ))}
            </select>
          </div>

          {/* Entity Scope Filter */}
          <div>
            <label className="text-[11px] font-bold text-ink-muted uppercase tracking-wider block mb-1.5">
              Entity Scope
            </label>
            <select
              value={entityFilter}
              onChange={(e) => {
                setEntityFilter(e.target.value)
                setPage(1)
              }}
              className="w-full bg-surface-sunken border border-border text-ink text-xs rounded-xl px-3 py-2 focus:outline-none focus:ring-1 focus:ring-accent"
            >
              <option value="">All Entities</option>
              <option value="case">Cases Only</option>
              <option value="payment">Payments Only</option>
            </select>
          </div>

          {/* Actor Role Filter */}
          <div>
            <label className="text-[11px] font-bold text-ink-muted uppercase tracking-wider block mb-1.5">
              Executing Actor
            </label>
            <select
              value={actorFilter}
              onChange={(e) => {
                setActorFilter(e.target.value)
                setPage(1)
              }}
              className="w-full bg-surface-sunken border border-border text-ink text-xs rounded-xl px-3 py-2 focus:outline-none focus:ring-1 focus:ring-accent"
            >
              <option value="">All Actors</option>
              {availableActors.map((act) => (
                <option key={act} value={act}>
                  {act.replace('_', ' ')}
                </option>
              ))}
            </select>
          </div>

          {/* Search Entity ID Form */}
          <form onSubmit={handleSearchSubmit}>
            <label className="text-[11px] font-bold text-ink-muted uppercase tracking-wider block mb-1.5">
              Entity ID Search
            </label>
            <div className="flex gap-1.5">
              <input
                type="text"
                placeholder="e.g. case_... or pay_..."
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value)
                }}
                className="w-full bg-surface-sunken border border-border text-ink text-xs rounded-xl px-3 py-2 focus:outline-none focus:ring-1 focus:ring-accent font-mono"
              />
              <button
                type="submit"
                className="px-3 bg-accent text-white rounded-xl text-xs font-bold hover:bg-accent-hover transition-colors cursor-pointer"
              >
                <Search className="h-3.5 w-3.5" />
              </button>
            </div>
          </form>
        </div>
      </div>

      {/* 3. Audit Log Table */}
      <div className="bg-surface border border-border rounded-2xl overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-surface-sunken/60 border-b border-border text-ink-muted uppercase font-bold text-[10px] tracking-wider">
              <tr>
                <th className="py-3 px-4">Timestamp</th>
                <th className="py-3 px-4">Action</th>
                <th className="py-3 px-4">Entity</th>
                <th className="py-3 px-4">Entity ID</th>
                <th className="py-3 px-4">Actor</th>
                <th className="py-3 px-4">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {paginatedEntries.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-ink-muted">
                    <div className="flex flex-col items-center justify-center gap-3">
                      <p>No audit records match the current filter criteria.</p>
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
                        className="gap-2 text-xs font-mono cursor-pointer"
                      >
                        <Sparkles className="h-3.5 w-3.5 text-accent" />
                        <span>{isSeeding ? 'Seeding Batch...' : 'Seed Recovery Batch'}</span>
                      </Button>
                    </div>
                  </td>
                </tr>
              ) : (
                paginatedEntries.map((entry) => {
                  const isExpanded = expandedEntryId === entry.entry_id
                  const actorInfo = formatActorBadge(entry.actor)

                  return (
                    <React.Fragment key={entry.entry_id}>
                      <tr className="hover:bg-surface-sunken/40 transition-colors">
                        {/* Timestamp */}
                        <td className="py-3.5 px-4 font-mono text-[11px] text-ink-muted whitespace-nowrap">
                          {new Date(entry.timestamp).toLocaleString()}
                        </td>

                        {/* Action Badge */}
                        <td className="py-3.5 px-4 whitespace-nowrap">
                          {formatActionBadge(entry.event_name)}
                        </td>

                        {/* Entity */}
                        <td className="py-3.5 px-4 font-semibold capitalize text-ink">
                          Case Entry
                        </td>

                        {/* Entity ID */}
                        <td className="py-3.5 px-4 font-mono text-[11px] text-ink-muted">
                          #{entry.case_id.slice(0, 10)}...
                        </td>

                        {/* Actor with Floating User Tooltip */}
                        <td className="py-3.5 px-4 whitespace-nowrap">
                          <div className="relative group inline-flex items-center gap-1.5 cursor-pointer">
                            <span className="font-semibold text-ink underline decoration-dotted decoration-ink-muted underline-offset-4">
                              {actorInfo.label}
                            </span>
                            <span className="text-[10px] uppercase font-bold text-ink-muted bg-surface-sunken px-1.5 py-0.5 rounded border border-border">
                              {actorInfo.sub}
                            </span>

                            {/* Floating User / System Tooltip */}
                            <div className="absolute bottom-full left-0 mb-2 hidden group-hover:flex flex-col gap-1 w-64 p-3 bg-surface text-ink rounded-xl border border-border shadow-2xl z-50 animate-in fade-in duration-150 pointer-events-none text-xs">
                              <div className="flex items-center justify-between border-b border-border pb-1.5">
                                <span className="font-bold text-xs text-ink truncate">
                                  {actorInfo.label}
                                </span>
                                <span className="text-[9px] font-mono uppercase font-black px-1.5 py-0.5 rounded bg-accent-subtle text-accent border border-accent/20">
                                  {entry.actor}
                                </span>
                              </div>
                              <div className="text-[11px] space-y-0.5 text-ink-muted pt-0.5">
                                <p>
                                  <strong className="text-ink">Component:</strong> {actorInfo.sub}
                                </p>
                                <p>
                                  <strong className="text-ink">Audit ID:</strong> #{entry.entry_id.slice(0, 12)}
                                </p>
                                <p>
                                  <strong className="text-ink">Case Scope:</strong> #{entry.case_id.slice(0, 8)}
                                </p>
                                {entry.cost_incurred_paise > 0 && (
                                  <p className="text-failed">
                                    <strong className="text-ink">Cost Incurred:</strong> INR {(entry.cost_incurred_paise / 100).toFixed(2)}
                                  </p>
                                )}
                              </div>
                            </div>
                          </div>
                        </td>

                        {/* Details Toggle */}
                        <td className="py-3.5 px-4">
                          <button
                            type="button"
                            onClick={() => {
                              setExpandedEntryId(isExpanded ? null : entry.entry_id)
                            }}
                            className="inline-flex items-center gap-1 text-accent hover:underline font-semibold text-[11px] cursor-pointer"
                          >
                            {isExpanded ? (
                              <>
                                <span>Hide Payload</span>
                                <ChevronUp className="h-3.5 w-3.5" />
                              </>
                            ) : (
                              <>
                                <span>View Payload</span>
                                <ChevronDown className="h-3.5 w-3.5" />
                              </>
                            )}
                          </button>
                        </td>
                      </tr>

                      {/* Expandable Payload Row */}
                      {isExpanded && (
                        <tr className="bg-surface-sunken/40">
                          <td colSpan={6} className="py-3 px-6">
                            <div className="bg-surface border border-border rounded-xl p-3 text-[11px] font-mono overflow-x-auto text-ink space-y-1">
                              <pre>{JSON.stringify(entry.decision_inputs, null, 2)}</pre>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  )
                })
              )}
            </tbody>
          </table>
        </div>

        {/* 4. Pagination Bar */}
        <div className="flex items-center justify-between px-4 py-3 border-t border-border bg-surface-sunken/20">
          <p className="text-xs text-ink-muted font-medium">
            Showing {paginatedEntries.length.toString()} of {total.toString()} audit records
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                setPage((p) => Math.max(1, p - 1))
              }}
              disabled={page <= 1}
              className="p-1.5 rounded-lg border border-border bg-surface hover:bg-surface-sunken text-ink disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="text-xs font-semibold px-2 text-ink">
              Page {page.toString()} of {totalPages.toString()}
            </span>
            <button
              type="button"
              onClick={() => {
                setPage((p) => Math.min(totalPages, p + 1))
              }}
              disabled={page >= totalPages}
              className="p-1.5 rounded-lg border border-border bg-surface hover:bg-surface-sunken text-ink disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
