'use client'

import React from 'react'
import {
  Cpu,
  RotateCcw,
  Server,
} from 'lucide-react'
import type { SystemStatusResponse } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { SkeletonCard } from '@/components/ui/skeleton'

interface StatusViewProps {
  status: SystemStatusResponse | null
  loading: boolean
  onRefresh: () => void
}

function formatUptime(seconds: number): string {
  const hrs = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  const secs = seconds % 60
  if (hrs > 0) return `${hrs.toString()}h ${mins.toString()}m ${secs.toString()}s`
  if (mins > 0) return `${mins.toString()}m ${secs.toString()}s`
  return `${secs.toString()}s`
}

export function StatusView({ status, loading, onRefresh }: StatusViewProps) {
  if (loading || !status) {
    return (
      <div className="space-y-6">
        <SkeletonCard />
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Top Engine Health Bar */}
      <Card className="border-recovered/40 bg-recovered-subtle/10">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <div>
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-recovered animate-pulse" />
              <CardTitle className="text-lg">System Status: {status.system_status}</CardTitle>
            </div>
            <CardDescription className="mt-1">
              All autonomous recovery pipelines, gateway webhooks, and policy guardrails are active
            </CardDescription>
          </div>
          <button
            type="button"
            onClick={onRefresh}
            className="flex items-center gap-1.5 rounded-control bg-surface border border-border px-3 py-1 text-xs font-mono text-ink hover:bg-surface-sunken transition-colors cursor-pointer"
          >
            <RotateCcw className="h-3 w-3" />
            <span>Poll Status</span>
          </button>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-4 sm:grid-cols-4 pt-4 border-t border-border/50">
          <div>
            <span className="text-[11px] font-mono text-ink-muted uppercase block">Process Uptime</span>
            <span className="text-sm font-mono font-semibold text-ink mt-0.5 block">
              {formatUptime(status.uptime_seconds)}
            </span>
          </div>
          <div>
            <span className="text-[11px] font-mono text-ink-muted uppercase block">Active Queue</span>
            <span className="text-sm font-mono font-semibold text-pending mt-0.5 block">
              {status.active_recovery_queue.toString()} cases
            </span>
          </div>
          <div>
            <span className="text-[11px] font-mono text-ink-muted uppercase block">Escalated Queue</span>
            <span className={`text-sm font-mono font-semibold mt-0.5 block ${status.escalated_queue_count > 0 ? 'text-escalated' : 'text-ink'}`}>
              {status.escalated_queue_count.toString()} cases
            </span>
          </div>
          <div>
            <span className="text-[11px] font-mono text-ink-muted uppercase block">Repository Store</span>
            <span className="text-sm font-mono font-semibold text-ink mt-0.5 block">
              {status.database_cases_count.toString()} transactions
            </span>
          </div>
        </CardContent>
      </Card>

      {/* Subsystem Telemetry Cards */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Gateway Subsystem */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Server className="h-4 w-4 text-accent" />
                <CardTitle>Payment Gateway Subsystem</CardTitle>
              </div>
              <Badge variant={status.gateway_integration.authenticated ? 'recovered' : 'pending'}>
                {status.gateway_integration.authenticated ? 'Authenticated' : 'Mock Mode'}
              </Badge>
            </div>
            <CardDescription>Razorpay API & Webhook Ingress health</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 font-mono text-xs">
            <div className="flex justify-between p-2 rounded-control bg-surface-sunken">
              <span className="text-ink-muted">Gateway Provider</span>
              <span className="text-ink font-semibold">{status.gateway_integration.provider} ({status.gateway_integration.mode})</span>
            </div>
            <div className="flex justify-between p-2 rounded-control bg-surface-sunken">
              <span className="text-ink-muted">Key ID</span>
              <span className="text-ink">{status.gateway_integration.key_id || 'Not configured'}</span>
            </div>
            <div className="flex justify-between p-2 rounded-control bg-surface-sunken">
              <span className="text-ink-muted">Webhook Endpoint</span>
              <span className="text-ink">{status.gateway_integration.webhook_endpoint}</span>
            </div>
            <div className="flex justify-between p-2 rounded-control bg-surface-sunken">
              <span className="text-ink-muted">Supported Rails</span>
              <span className="text-ink">{status.gateway_integration.supported_rails.join(', ')}</span>
            </div>
          </CardContent>
        </Card>

        {/* AI & Policy Subsystem */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Cpu className="h-4 w-4 text-accent" />
                <CardTitle>AI Reasoning & Policy Subsystem</CardTitle>
              </div>
              <Badge variant="recovered">Active</Badge>
            </div>
            <CardDescription>LLM orchestration & deterministic fallback telemetry</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 font-mono text-xs">
            <div className="flex justify-between p-2 rounded-control bg-surface-sunken">
              <span className="text-ink-muted">Active Model</span>
              <span className="text-ink font-semibold truncate max-w-xs">{status.llm_engine.active_model}</span>
            </div>
            <div className="flex justify-between p-2 rounded-control bg-surface-sunken">
              <span className="text-ink-muted">Configured Providers</span>
              <span className="text-ink">
                {status.llm_engine.configured_providers.length > 0
                  ? status.llm_engine.configured_providers.join(', ')
                  : 'Offline Rules (Deterministic)'}
              </span>
            </div>
            <div className="flex justify-between p-2 rounded-control bg-surface-sunken">
              <span className="text-ink-muted">Circuit Breaker</span>
              <span className="text-recovered font-semibold">{status.llm_engine.circuit_breaker}</span>
            </div>
            <div className="flex justify-between p-2 rounded-control bg-surface-sunken">
              <span className="text-ink-muted">Deterministic Guardrails</span>
              <span className="text-recovered font-semibold">
                Max {status.policy_enforcement.max_touches_cap.toString()} touches | {status.policy_enforcement.cooldown_hours.toString()}h cooldown | {status.policy_enforcement.holdout_ratio_pct.toString()}% holdout
              </span>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
