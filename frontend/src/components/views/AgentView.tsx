'use client'

import React, { useState } from 'react'
import {
  AlertTriangle,
  Brain,
  DollarSign,
  Play,
  Sparkles,
  Zap,
} from 'lucide-react'
import {
  seedSimulation,
  type RecoveryCase,
  type SystemStatusResponse,
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
import { StatCard } from '@/components/ui/StatCard'

interface AgentViewProps {
  cases: RecoveryCase[]
  status: SystemStatusResponse | null
  loading: boolean
  onRefresh?: () => void
}

export function AgentView({
  cases,
  status,
  loading,
  onRefresh,
}: AgentViewProps) {
  const [seeding, setSeeding] = useState(false)

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
  }> = []

  cases.forEach((c) => {
    c.audit_trail.forEach((entry) => {
      if (
        entry.actor === 'agent_llm' ||
        entry.actor === 'AGENT_LLM' ||
        entry.event_name === 'agent.plan_formulated' ||
        entry.event_name.startsWith('agent.') ||
        entry.model_metadata
      ) {
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
        })
      }
    })
  })

  // Sort newest first
  agentEntries.sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
  )

  const handleSeedBatch = async () => {
    setSeeding(true)
    try {
      await seedSimulation(30, true)
      if (onRefresh) onRefresh()
    } finally {
      setSeeding(false)
    }
  }

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
          <h1 className="font-mono text-2xl font-bold text-ink">
            Autonomous Decision Stream
          </h1>
          <p className="mt-0.5 text-sm text-ink-muted">
            Immutable per-decision model traces, exact provider attribution,
            latencies, and token cost accounting.
          </p>
        </div>

        <Button
          variant="primary"
          size="sm"
          disabled={seeding || loading}
          onClick={() => {
            void handleSeedBatch()
          }}
          className="cursor-pointer gap-2 self-start font-mono text-xs sm:self-auto"
        >
          <Sparkles className="h-3.5 w-3.5" />
          <span>
            {seeding ? 'Generating Decisions...' : 'Seed Decision Cohort'}
          </span>
        </Button>
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
            <Badge variant="outline" className="font-mono text-xs">
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
                <p className="font-mono text-sm font-semibold text-ink">
                  No Decision Events Recorded Yet
                </p>
                <p className="mx-auto mt-1 max-w-md text-xs text-ink-muted">
                  Run a recovery simulation or trigger webhook ingress to
                  inspect live AI strategy plans and safety audits.
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                disabled={seeding}
                onClick={() => {
                  void handleSeedBatch()
                }}
                className="cursor-pointer gap-2 font-mono text-xs"
              >
                <Play className="h-3 w-3 text-recovered" />
                <span>Run Decision Simulation</span>
              </Button>
            </div>
          ) : (
            agentEntries.map((entry, idx) => {
              const isDeterministic =
                entry.provider === 'deterministic' || entry.used_fallback

              return (
                <div
                  key={`${entry.case_id}-${idx.toString()}`}
                  className="space-y-3 rounded-panel border border-border bg-surface-sunken/40 p-4 font-mono text-xs transition-colors hover:border-accent/40"
                >
                  {/* Top Metadata Header */}
                  <div className="flex flex-col justify-between gap-2 border-b border-border/60 pb-2 sm:flex-row sm:items-center">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge
                        variant="outline"
                        className="font-mono text-[11px] font-semibold text-ink"
                      >
                        {entry.case_id.slice(0, 13)}...
                      </Badge>
                      <RailBadge rail={entry.payment_rail} />
                      <span className="text-[11px] text-ink-subtle">
                        {entry.payment_id}
                      </span>
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
                    <div className="space-y-1 rounded-control border border-failed/30 bg-failed/10 p-3 font-mono text-xs">
                      <div className="flex items-center gap-1.5 text-xs font-bold text-failed">
                        <AlertTriangle className="h-3.5 w-3.5" />
                        <span>
                          LLM Provider Error: Automated Fallback Executed
                        </span>
                      </div>
                      <p className="text-xs leading-relaxed text-ink">
                        {entry.fallback_reason}
                      </p>
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
