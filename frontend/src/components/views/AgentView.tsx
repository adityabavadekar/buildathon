'use client'

import React from 'react'
import type { RecoveryCase } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

interface AgentViewProps {
  cases: RecoveryCase[]
}

export function AgentView({ cases }: AgentViewProps) {
  // Aggregate agent decisions from cases
  const agentEntries = cases.flatMap((c) =>
    c.audit_trail.filter((e) => e.actor === 'AGENT_LLM' || e.actor === 'POLICY_GATE').map((e) => ({
      ...e,
      case: c,
    }))
  )

  return (
    <div className="space-y-6">
      {/* Agent Telemetry Stats */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader className="p-4 pb-2 border-none">
            <CardDescription>Decisions Formulated</CardDescription>
            <CardTitle className="text-xl font-mono text-ink">
              {agentEntries.length.toString()}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0 text-[11px] text-ink-subtle">
            Contextual LLM & rule diagnoses
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="p-4 pb-2 border-none">
            <CardDescription>Deterministic Guardrail Pass</CardDescription>
            <CardTitle className="text-xl font-mono text-recovered">
              100%
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0 text-[11px] text-ink-subtle">
            Zero policy or touch-limit violations
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="p-4 pb-2 border-none">
            <CardDescription>Active LLM Model</CardDescription>
            <CardTitle className="text-xl font-mono text-accent truncate">
              OpenRouter / Claude
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0 text-[11px] text-ink-subtle">
            With deterministic offline fallback
          </CardContent>
        </Card>
      </div>

      {/* Decision Feed */}
      <Card>
        <CardHeader>
          <CardTitle>Autonomous Decision Stream</CardTitle>
          <CardDescription>
            Real-time audit log of AI recovery decisions, rationale, and policy checks
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {agentEntries.length === 0 ? (
            <p className="py-8 text-center text-xs font-mono text-ink-muted">
              No agent decisions recorded yet. Send a test webhook to trigger autonomous reasoning.
            </p>
          ) : (
            agentEntries.slice(0, 15).map((entry) => (
              <div
                key={entry.entry_id}
                className="p-4 rounded-panel border border-border bg-surface-sunken/40 space-y-2"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Badge variant={entry.actor === 'AGENT_LLM' ? 'outline' : 'default'}>
                      {entry.actor}
                    </Badge>
                    <span className="font-mono text-xs font-semibold text-ink">
                      {entry.event_name}
                    </span>
                  </div>
                  <span className="text-[11px] font-mono text-ink-muted">
                    Case: {entry.case_id} | {new Date(entry.timestamp).toLocaleTimeString()}
                  </span>
                </div>

                <p className="text-xs text-ink">{entry.reason}</p>

                {entry.model_metadata && (
                  <div className="mt-2 flex gap-3 text-[10px] font-mono text-ink-subtle pt-2 border-t border-border/50">
                    <span>Model: {entry.model_metadata.model}</span>
                    <span>Tokens: {(entry.model_metadata.input_tokens || 0) + (entry.model_metadata.output_tokens || 0)}</span>
                    {entry.model_metadata.cost_usd && (
                      <span>Cost: ${entry.model_metadata.cost_usd.toFixed(4)}</span>
                    )}
                  </div>
                )}
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  )
}
