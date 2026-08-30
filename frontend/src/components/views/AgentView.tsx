'use client'

import React, { useEffect, useState } from 'react'
import {
  Brain,
  Cpu,
  ShieldCheck,
} from 'lucide-react'
import {
  getSettings,
  type RecoveryCase,
  type SystemSettingsResponse,
} from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { GlossaryTerm } from '@/components/ui/GlossaryTerm'

interface AgentViewProps {
  cases: RecoveryCase[]
}

export function AgentView({ cases }: AgentViewProps) {
  const [settings, setSettings] = useState<SystemSettingsResponse | null>(null)

  useEffect(() => {
    getSettings().then(setSettings).catch(() => null)
  }, [])

  // Aggregate agent decisions from cases
  const agentEntries = cases.flatMap((c) =>
    c.audit_trail
      .filter((e) => e.actor === 'AGENT_LLM' || e.actor === 'POLICY_GATE')
      .map((e) => ({
        ...e,
        parentCase: c,
      }))
  )

  // Compute actual guardrail pass rate dynamically
  const policyGateEntries = cases.flatMap((c) =>
    c.audit_trail.filter((e) => e.actor === 'POLICY_GATE')
  )
  const blockedEntries = policyGateEntries.filter(
    (e) =>
      e.to_state === 'ESCALATED' ||
      (e.reason && e.reason.toLowerCase().includes('blocked'))
  )
  const guardrailPassRate =
    policyGateEntries.length > 0
      ? `${Math.round(
          ((policyGateEntries.length - blockedEntries.length) /
            policyGateEntries.length) *
            100
        ).toString()}%`
      : '100%'

  const activeModelName =
    settings?.active_llm_model ||
    agentEntries.find((e) => e.model_metadata?.model)?.model_metadata?.model ||
    'Rule Engine / Deterministic Fallback'

  return (
    <div className="space-y-6">
      {/* View Header with Plain-Language Context */}
      <div className="border-b border-border pb-4">
        <h1 className="text-2xl font-bold font-mono text-ink">
          Autonomous Decision Stream
        </h1>
        <p className="text-sm text-ink-muted mt-0.5">
          Why the engine chose each recovery move, including the raw AI rationale, confidence score, and model used.
        </p>
      </div>

      {/* Agent Telemetry Stats with Filled Semantic Icons */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card className="hover:border-accent/40 transition-colors">
          <CardHeader className="p-5 pb-2 border-none">
            <div className="flex items-center justify-between">
              <CardDescription className="text-xs font-semibold text-ink-muted">
                Decisions Formulated
              </CardDescription>
              <div className="p-2 rounded-control bg-accent/15 text-accent">
                <Brain className="h-4 w-4" />
              </div>
            </div>
            <CardTitle className="text-3xl font-mono font-bold tabular-nums text-ink mt-1">
              {agentEntries.length.toString()}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-5 pt-0 text-xs text-ink-subtle">
            Contextual LLM & rule diagnoses across cohorts
          </CardContent>
        </Card>

        <Card className="border-recovered/30 bg-recovered/5 hover:border-recovered/60 transition-colors">
          <CardHeader className="p-5 pb-2 border-none">
            <div className="flex items-center justify-between">
              <CardDescription className="text-xs font-semibold text-ink-muted">
                <GlossaryTerm termKey="POLICY_GATE" showIcon={false}>
                  Deterministic Guardrail Pass
                </GlossaryTerm>
              </CardDescription>
              <div className="p-2 rounded-control bg-recovered/20 text-recovered">
                <ShieldCheck className="h-4 w-4" />
              </div>
            </div>
            <CardTitle className="text-3xl font-mono font-bold tabular-nums text-recovered mt-1">
              {guardrailPassRate}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-5 pt-0 text-xs text-ink-subtle">
            Strict policy evaluation before tool execution
          </CardContent>
        </Card>

        <Card className="hover:border-border-strong transition-colors">
          <CardHeader className="p-5 pb-2 border-none">
            <div className="flex items-center justify-between">
              <CardDescription className="text-xs font-semibold text-ink-muted">
                Active Reasoning Model
              </CardDescription>
              <div className="p-2 rounded-control bg-accent/15 text-accent">
                <Cpu className="h-4 w-4" />
              </div>
            </div>
            <CardTitle className="text-xl font-mono font-bold text-ink mt-1 truncate" title={activeModelName}>
              {activeModelName}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-5 pt-0 text-xs text-ink-subtle">
            Primary provider:{' '}
            <span className="font-semibold uppercase text-ink">
              {settings?.primary_llm_provider || 'deterministic'}
            </span>
          </CardContent>
        </Card>
      </div>

      {/* Decision Stream Feed */}
      <Card>
        <CardHeader>
          <CardTitle>Audited Agent Reasoning Feed</CardTitle>
          <CardDescription className="text-sm">
            Live chronological trace of LLM prompt outputs, confidence levels, and state transitions
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {agentEntries.length === 0 ? (
              <p className="py-8 text-center text-xs font-mono text-ink-muted">
                No agent decisions recorded yet. Seed a batch to observe real-time strategy planning.
              </p>
            ) : (
              agentEntries.slice(0, 15).map((entry, i) => {
                const timestampStr = entry.created_at ?? entry.timestamp
                const dateObj = new Date(timestampStr)
                const timeFormatted = isNaN(dateObj.getTime()) ? '' : dateObj.toLocaleTimeString()

                return (
                  <div
                    key={`${entry.case_id}-${timestampStr}-${i.toString()}`}
                    className="rounded-panel border border-border p-4 space-y-2 bg-surface-sunken/40 hover:bg-surface-sunken transition-colors"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-bold text-accent">
                          {entry.case_id}
                        </span>
                        <Badge variant="outline" className="font-mono text-[10px]">
                          {entry.parentCase.failure_event.payment_rail}
                        </Badge>
                        <Badge
                          variant={
                            entry.actor === 'AGENT_LLM' ? 'default' : 'outline'
                          }
                        >
                          {entry.actor}
                        </Badge>
                      </div>
                      <span className="font-mono text-[11px] text-ink-muted">
                        {timeFormatted}
                      </span>
                    </div>

                    <p className="text-xs text-ink leading-relaxed">
                      {entry.notes || entry.reason || 'Decision evaluated'}
                    </p>

                    {entry.model_metadata && (
                      <div className="flex flex-wrap items-center gap-3 pt-2 font-mono text-[11px] text-ink-subtle border-t border-border/60">
                        <span>Model: {entry.model_metadata.model}</span>
                        {entry.model_metadata.latency_ms !== undefined && (
                          <span className="text-accent font-semibold">
                            Latency: {entry.model_metadata.latency_ms.toFixed(1)}ms
                          </span>
                        )}
                        <span>
                          Tokens: in={(entry.model_metadata.input_tokens ?? 0).toString()}, out=
                          {(entry.model_metadata.output_tokens ?? 0).toString()}
                        </span>
                        {entry.model_metadata.cost_usd !== undefined && (
                          <span>
                            Cost: ${entry.model_metadata.cost_usd.toFixed(5)}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                )
              })
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
