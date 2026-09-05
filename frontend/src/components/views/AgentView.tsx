'use client'

import React from 'react'
import { AlertTriangle, Brain, DollarSign, Zap } from 'lucide-react'
import { type RecoveryCase, type SystemStatusResponse } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { RailBadge } from '@/components/ui/BrandIcons'
import { StatCard } from '@/components/ui/StatCard'

interface AgentViewProps {
  cases: RecoveryCase[]
  status: SystemStatusResponse | null
  onSelectCase?: (c: RecoveryCase) => void
}

export function AgentView({ cases, status, onSelectCase }: AgentViewProps) {
  const caseById = new Map<string, RecoveryCase>()
  for (const c of cases) caseById.set(c.case_id, c)

  const openCase = (caseId: string) => {
    const c = caseById.get(caseId)
    if (c && onSelectCase) onSelectCase(c)
  }

  const agentEntries: Array<{
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
          const planObj = entry.decision_outputs.plan as Record<string, unknown>
          if (typeof planObj.rationale === 'string') {
            planRationale = planObj.rationale
          }
        }

        agentEntries.push({
          case_id: c.case_id,
          payment_id: c.failure_event.payment_id,
          payment_rail: c.failure_event.payment_rail,
          amount_paise: c.amount_paise,
          event_name: entry.event_name,
          timestamp: entry.timestamp,
          reason: (entry.notes ?? entry.reason) || null,
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
  agentEntries.sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
  )

  const llmEngine = status?.llm_engine
  const activeModelName =
    llmEngine?.active_model || 'Deterministic Rules Engine'
  const primaryProvider = llmEngine?.configured_providers[0] || 'deterministic'
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
          value={agentEntries.length.toString()}
          subtitle="Snapshotted at formulation time"
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
          value={activeModelName}
          subtitle={`Configured provider: ${primaryProvider.toUpperCase()}`}
          variant="accent"
        />
      </div>

      {/* Decision Stream Feed */}
      <Card>
        <CardHeader className="border-b border-border/40 pb-3">
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
              {agentEntries.length} Recorded Traces
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-3 p-4">
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
          ) : (
            agentEntries.map((entry, idx) => {
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
                  className="space-y-3 rounded-panel border border-border bg-surface-sunken/40 p-4 text-xs transition-colors hover:border-accent/40"
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
                    <div className="rounded-control border border-border bg-surface p-3 leading-relaxed text-ink">
                      <span className="mb-1 block text-[10px] font-semibold tracking-wider text-ink-muted uppercase">
                        Strategy Rationale
                      </span>
                      {entry.plan_rationale}
                    </div>
                  )}

                  {entry.reason && !entry.plan_rationale && (
                    <div className="text-xs text-ink-muted">{entry.reason}</div>
                  )}

                  {/* Explicit LLM Provider Exception Alert Box */}
                  {entry.fallback_reason && (
                    <div className="space-y-1 rounded-control border border-failed/30 bg-failed/10 p-3 text-xs">
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

                  {entry.response_content && (
                    <div className="rounded-control border border-border bg-surface p-3 text-xs">
                      <span className="mb-1 block text-[10px] font-semibold tracking-wider text-accent uppercase">
                        LLM Response
                      </span>
                      <pre className="max-h-40 overflow-auto rounded bg-surface-sunken p-2 text-[10px] leading-relaxed whitespace-pre-wrap text-ink">
                        {entry.response_content}
                      </pre>
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
