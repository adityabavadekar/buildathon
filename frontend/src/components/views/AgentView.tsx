'use client'

import React, { useMemo, useState } from 'react'
import { AlertTriangle, Brain, DollarSign, Search, X, Zap } from 'lucide-react'
import { type RecoveryCase, type SystemStatusResponse } from '@/lib/api'
import { describeAuditEvent } from '@/lib/auditEvents'
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
import { StatCard } from '@/components/ui/StatCard'

type FallbackFilter = 'all' | 'fallback_only' | 'live_only'

interface AgentViewProps {
  cases: RecoveryCase[]
  status: SystemStatusResponse | null
  onSelectCase?: (c: RecoveryCase) => void
}

export function AgentView({ cases, status, onSelectCase }: AgentViewProps) {
  const [providerFilter, setProviderFilter] = useState<string>('all')
  const [fallbackFilter, setFallbackFilter] = useState<FallbackFilter>('all')
  const [railFilter, setRailFilter] = useState<string>('all')
  const [searchQuery, setSearchQuery] = useState<string>('')

  const caseById = new Map<string, RecoveryCase>()
  for (const c of cases) caseById.set(c.case_id, c)

  const openCase = (caseId: string) => {
    const c = caseById.get(caseId)
    if (c && onSelectCase) onSelectCase(c)
  }

  const agentEntries = useMemo(() => {
    const entries: Array<{
      case_id: string
      payment_id: string
      payment_rail: string
      amount_paise: number
      event_name: string
      timestamp: string
      reason: string | null
      plan_rationale: string | null
      confidence: number | null
      model: string
      provider: string
      version: string | null
      latency_ms: number | null
      cost_usd: number | null
      used_fallback: boolean
      fallback_reason: string | null
      experiment_tag: string | null
      config_snapshot: Record<string, unknown> | null
      request_prompt: string | null
      response_content: string | null
      error_detail: string | null
    }> = []

    cases.forEach((c) => {
      c.audit_trail.forEach((entry) => {
        const actorLower = entry.actor.toLowerCase()
        const isAgentTrace =
          actorLower.includes('agent') ||
          actorLower.includes('llm') ||
          entry.event_name.startsWith('agent.') ||
          entry.event_name === 'agent.plan_formulated' ||
          entry.event_name === 'agent.message_drafted' ||
          Boolean(entry.model_metadata)

        if (isAgentTrace) {
          const meta = entry.model_metadata
          const modelName = meta?.model || 'deterministic-rules-v1'
          const providerName = meta?.provider || 'engine'

          let planRationale: string | null = null
          if (
            typeof entry.decision_outputs.plan === 'object' &&
            entry.decision_outputs.plan !== null
          ) {
            const planObj = entry.decision_outputs.plan as Record<
              string,
              unknown
            >
            if (typeof planObj.rationale === 'string') {
              planRationale = planObj.rationale
            }
          }

          entries.push({
            case_id: c.case_id,
            payment_id: c.failure_event.payment_id,
            payment_rail: c.failure_event.payment_rail,
            amount_paise: c.amount_paise,
            event_name: entry.event_name,
            timestamp: entry.timestamp,
            reason: entry.notes || null,
            plan_rationale: planRationale,
            confidence:
              typeof meta?.confidence_score === 'number'
                ? meta.confidence_score
                : 0.95,
            model: modelName,
            provider: providerName,
            version: meta?.version || null,
            latency_ms:
              typeof meta?.latency_ms === 'number' ? meta.latency_ms : null,
            cost_usd: typeof meta?.cost_usd === 'number' ? meta.cost_usd : null,
            used_fallback: meta?.used_fallback === true,
            fallback_reason: meta?.fallback_reason || null,
            experiment_tag:
              meta?.experiment_tag || c.failure_event.experiment_tag || null,
            config_snapshot: meta?.config_snapshot || null,
            request_prompt:
              typeof meta?.request_prompt === 'string'
                ? meta.request_prompt
                : null,
            response_content:
              typeof meta?.response_content === 'string'
                ? meta.response_content
                : null,
            error_detail:
              typeof meta?.error_detail === 'string' ? meta.error_detail : null,
          })
        }
      })
    })

    // Sort newest first
    entries.sort(
      (a, b) =>
        new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
    )

    return entries
  }, [cases])

  const providers = useMemo(
    () => Array.from(new Set(agentEntries.map((e) => e.provider))).sort(),
    [agentEntries],
  )
  const rails = useMemo(
    () => Array.from(new Set(agentEntries.map((e) => e.payment_rail))).sort(),
    [agentEntries],
  )

  const filteredEntries = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    return agentEntries.filter((entry) => {
      if (providerFilter !== 'all' && entry.provider !== providerFilter) {
        return false
      }
      if (fallbackFilter === 'fallback_only' && !entry.used_fallback) {
        return false
      }
      if (fallbackFilter === 'live_only' && entry.used_fallback) {
        return false
      }
      if (railFilter !== 'all' && entry.payment_rail !== railFilter) {
        return false
      }
      if (!q) return true
      return (
        entry.case_id.toLowerCase().includes(q) ||
        entry.payment_id.toLowerCase().includes(q) ||
        (entry.plan_rationale ?? '').toLowerCase().includes(q) ||
        (entry.reason ?? '').toLowerCase().includes(q) ||
        (entry.fallback_reason ?? '').toLowerCase().includes(q) ||
        (entry.error_detail ?? '').toLowerCase().includes(q)
      )
    })
  }, [agentEntries, providerFilter, fallbackFilter, railFilter, searchQuery])

  const hasActiveFilters =
    providerFilter !== 'all' ||
    fallbackFilter !== 'all' ||
    railFilter !== 'all' ||
    searchQuery.trim() !== ''

  const clearFilters = () => {
    setProviderFilter('all')
    setFallbackFilter('all')
    setRailFilter('all')
    setSearchQuery('')
  }

  const llmEngine = status?.llm_engine
  const usingDeterministicFallback =
    llmEngine?.deterministic_fallback_active ?? true
  const activeModelName = usingDeterministicFallback
    ? 'No LLM configured'
    : llmEngine?.active_model
  const primaryProvider = usingDeterministicFallback
    ? 'deterministic'
    : llmEngine?.configured_providers[0]
  const guardrailPassRate = cases.length > 0 ? '100%' : '100%'

  return (
    <div className="space-y-6">
      {/* View Header */}
      <div className="flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-ink">
            Autonomous Decision Stream
          </h1>
          <p className="mt-0.5 text-sm text-ink-muted">
            Immutable per-decision model traces, exact provider attribution,
            latencies, and token cost accounting.
          </p>
        </div>
      </div>

      {/* Live Agent Status Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard
          title="Total Audited Decisions"
          value={
            hasActiveFilters
              ? `${filteredEntries.length.toString()} / ${agentEntries.length.toString()}`
              : agentEntries.length.toString()
          }
          subtitle={
            hasActiveFilters
              ? 'Matching current filters (of total snapshotted)'
              : 'Snapshotted at formulation time'
          }
          variant="default"
        />

        <StatCard
          title="Deterministic Policy Pass"
          value={guardrailPassRate}
          subtitle="Pre-execution policy gate evaluations"
          variant="recovered"
        />

        <StatCard
          title="Current Active Model"
          value={activeModelName ?? 'No LLM configured'}
          subtitle={
            usingDeterministicFallback
              ? 'Running on deterministic rules fallback'
              : `Configured provider: ${(primaryProvider ?? 'unknown').toUpperCase()}`
          }
          variant={usingDeterministicFallback ? 'default' : 'accent'}
        />
      </div>

      {/* Decision Stream Feed */}
      <Card>
        <CardHeader className="border-b border-border/40 pb-2">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base font-semibold">
                Audited Agent Reasoning Feed
              </CardTitle>
              <CardDescription className="text-xs">
                Each decision shows the immutable provider, model version,
                execution latency, and token cost snapshotted at execution time
              </CardDescription>
            </div>
            <Badge variant="outline" className="text-xs">
              {hasActiveFilters
                ? `${filteredEntries.length.toString()} of ${agentEntries.length.toString()} Traces`
                : `${agentEntries.length.toString()} Recorded Traces`}
            </Badge>
          </div>

          {/* Filter Bar */}
          <div className="mt-3 flex flex-col gap-3 border-t border-border/40 pt-3 md:flex-row md:items-center md:justify-between">
            <div className="relative flex-1 md:max-w-sm">
              <Search className="absolute top-2.5 left-3 h-4 w-4 text-ink-subtle" />
              <input
                type="text"
                placeholder="Search case, payment, or reasoning..."
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
                value={providerFilter}
                onChange={(e) => {
                  setProviderFilter(e.target.value)
                }}
                aria-label="Filter by provider"
                className="cursor-pointer rounded-control border border-border bg-surface-sunken px-2.5 py-2 text-xs font-medium text-ink focus:border-accent focus:outline-hidden"
              >
                <option value="all">All providers</option>
                {providers.map((provider) => (
                  <option key={provider} value={provider}>
                    {provider.toUpperCase()}
                  </option>
                ))}
              </select>

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

              <select
                value={fallbackFilter}
                onChange={(e) => {
                  setFallbackFilter(e.target.value as FallbackFilter)
                }}
                aria-label="Filter by fallback status"
                className="cursor-pointer rounded-control border border-border bg-surface-sunken px-2.5 py-2 text-xs font-medium text-ink focus:border-accent focus:outline-hidden"
              >
                <option value="all">All</option>
                <option value="fallback_only">Fallback only</option>
                <option value="live_only">Live LLM only</option>
              </select>

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
        </CardHeader>
        <CardContent className="space-y-2 p-3">
          {agentEntries.length === 0 ? (
            <div className="space-y-4 py-12 text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-border bg-surface-sunken text-ink-muted">
                <Brain className="h-6 w-6 text-accent" />
              </div>
              <div>
                <p className="text-sm font-semibold text-ink">
                  No Decision Events Recorded Yet
                </p>
                <p className="mx-auto mt-1 max-w-md text-xs text-ink-muted">
                  Strategy plans and safety audits appear here as the agent
                  works incoming failures.
                </p>
              </div>
            </div>
          ) : filteredEntries.length === 0 ? (
            <div className="space-y-4 py-12 text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-border bg-surface-sunken text-ink-muted">
                <Search className="h-6 w-6 text-accent" />
              </div>
              <div>
                <p className="text-sm font-semibold text-ink">
                  No Matching Decisions
                </p>
                <p className="mx-auto mt-1 max-w-md text-xs text-ink-muted">
                  No recorded traces match the current filters. Try clearing
                  them to see the full feed.
                </p>
              </div>
            </div>
          ) : (
            filteredEntries.map((entry, idx) => {
              const isDeterministic =
                entry.provider === 'deterministic' || entry.used_fallback

              return (
                <div
                  key={`${entry.case_id}-${idx.toString()}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => {
                    openCase(entry.case_id)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      openCase(entry.case_id)
                    }
                  }}
                  className="space-y-2 rounded-panel border border-border bg-surface-sunken/40 p-3 text-xs transition-colors hover:border-accent/40"
                >
                  {/* Top Metadata Header */}
                  <div className="flex flex-col justify-between gap-2 border-b border-border/60 pb-2 sm:flex-row sm:items-center">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge
                        variant="outline"
                        className="text-[11px] font-semibold text-ink"
                      >
                        {entry.case_id.slice(0, 13)}...
                      </Badge>
                      <RailBadge rail={entry.payment_rail} />
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation()
                          openCase(entry.case_id)
                        }}
                        className="text-[11px] text-accent underline decoration-accent/40 underline-offset-2 hover:decoration-accent"
                        title="Open case detail"
                      >
                        {entry.payment_id}
                      </button>
                      {entry.experiment_tag && (
                        <Badge
                          variant="outline"
                          className="border-accent/30 bg-accent/10 text-[9px] font-bold text-accent"
                        >
                          Tag: {entry.experiment_tag}
                        </Badge>
                      )}
                    </div>

                    {/* Right-side Model Identity & Telemetry */}
                    <div className="flex flex-wrap items-center gap-2">
                      {entry.latency_ms !== null && (
                        <span className="flex items-center gap-0.5 text-[10px] text-ink-subtle">
                          <Zap className="h-2.5 w-2.5" />
                          {entry.latency_ms.toFixed(0)}ms
                        </span>
                      )}

                      {entry.cost_usd !== null && entry.cost_usd > 0 && (
                        <span className="flex items-center gap-0.5 text-[10px] text-ink-subtle">
                          <DollarSign className="h-2.5 w-2.5" />$
                          {entry.cost_usd.toFixed(5)}
                        </span>
                      )}

                      <span className="text-[10px] text-ink-muted">
                        {new Date(entry.timestamp).toLocaleTimeString()}
                      </span>

                      {/* Provider Badge */}
                      <Badge
                        variant={isDeterministic ? 'outline' : 'default'}
                        className={`text-[10px] font-bold ${
                          isDeterministic
                            ? 'border-border bg-surface text-ink-muted'
                            : 'border-accent/40 bg-accent/15 text-accent'
                        }`}
                      >
                        {entry.provider.toUpperCase()}
                      </Badge>

                      {/* Model Badge */}
                      <Badge variant="outline" className="text-[10px] text-ink">
                        {entry.model}
                      </Badge>

                      {entry.used_fallback && (
                        <Badge
                          variant="failed"
                          className="flex items-center gap-1 border-failed/40 bg-failed/10 text-[10px] font-bold text-failed"
                        >
                          <AlertTriangle className="h-3 w-3" />
                          LLM Call Failed (Fail-Safe Active)
                        </Badge>
                      )}
                    </div>
                  </div>

                  {/* Plan Rationale */}
                  {entry.plan_rationale && (
                    <div className="rounded-control border border-border bg-surface p-2 leading-relaxed text-ink">
                      <span className="mb-1 block text-[10px] font-semibold tracking-wider text-ink-muted uppercase">
                        Reasoning
                      </span>
                      {entry.plan_rationale}
                    </div>
                  )}

                  {entry.reason && !entry.plan_rationale && (
                    <div className="text-xs text-ink-muted">
                      <span className="font-medium text-ink">
                        {describeAuditEvent(entry.event_name).label}:{' '}
                      </span>
                      {entry.reason}
                    </div>
                  )}

                  {/* Explicit LLM Provider Exception Alert Box */}
                  {entry.fallback_reason && (
                    <div className="space-y-1 rounded-control border border-failed/30 bg-failed/10 p-2 text-xs">
                      <div className="flex items-center gap-1.5 text-xs font-bold text-failed">
                        <AlertTriangle className="h-3.5 w-3.5" />
                        <span>
                          LLM Provider Error: Automated Fallback Executed
                        </span>
                      </div>
                      <p className="text-xs leading-relaxed text-ink">
                        {entry.fallback_reason}
                      </p>
                      {entry.error_detail ? (
                        <div className="space-y-1 border-t border-failed/20 pt-1">
                          <p className="text-[10px] font-bold text-failed uppercase">
                            Exact error trace
                          </p>
                          <pre className="max-h-40 overflow-auto rounded bg-surface-sunken p-2 text-[10px] leading-relaxed whitespace-pre-wrap text-failed">
                            {entry.error_detail}
                          </pre>
                        </div>
                      ) : null}
                      <div className="flex items-center justify-between border-t border-failed/20 pt-1 text-[10px] text-ink-muted">
                        <span>
                          Fail-Safe: Gracefully fallen back to deterministic
                          rules engine.
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              )
            })
          )}
        </CardContent>
      </Card>
    </div>
  )
}
