'use client'

import React, { useEffect, useState } from 'react'
import {
  CheckCircle2,
  Cpu,
  RotateCcw,
  Server,
  Zap,
} from 'lucide-react'
import {
  testGatewayConnection,
  type GatewayTestResponse,
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
import { RazorpayIcon, RazorpaySymbol, UpiIcon } from '@/components/ui/BrandIcons'
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
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0)
  const [testingGateway, setTestingGateway] = useState<boolean>(false)
  const [gatewayTestResult, setGatewayTestResult] = useState<GatewayTestResponse | null>(null)

  // Live ticking uptime timer incrementing elapsed seconds every 1000ms
  useEffect(() => {
    const timer = setInterval(() => {
      setElapsedSeconds((prev) => prev + 1)
    }, 1000)
    return () => {
      clearInterval(timer)
    }
  }, [])

  const liveUptime = (status?.uptime_seconds ?? 0) + elapsedSeconds

  const handleTestGateway = async () => {
    try {
      setTestingGateway(true)
      const res = await testGatewayConnection()
      setGatewayTestResult(res)
    } catch {
      setGatewayTestResult(null)
    } finally {
      setTestingGateway(false)
    }
  }

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
      {/* View Header with Plain-Language Context */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border pb-4">
        <div>
          <div className="flex items-center gap-2">
            <RazorpaySymbol className="h-5 w-5" />
            <h1 className="text-xl font-bold font-mono text-ink">
              System Subsystems & Operational Health
            </h1>
          </div>
          <p className="text-xs text-ink-muted mt-0.5">
            Real-time health and diagnostics for Razorpay webhooks, AI models, and deterministic policy subsystems.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void handleTestGateway()
            }}
            disabled={testingGateway}
            className="font-mono text-xs flex items-center gap-1.5"
          >
            <Zap className="h-3.5 w-3.5 text-accent" />
            {testingGateway ? 'Probing Gateway...' : 'Test Razorpay Connection'}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={onRefresh}
            className="font-mono text-xs flex items-center gap-1.5"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Gateway Probe Diagnostic Result (if run) */}
      {gatewayTestResult && (
        <Card className="border-accent/40 bg-accent-subtle/10 animate-in fade-in-0 duration-200">
          <CardHeader className="p-4 pb-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-recovered" />
                <CardTitle className="text-sm font-mono font-bold text-ink">
                  Razorpay Gateway Handshake Diagnostic: {gatewayTestResult.status}
                </CardTitle>
              </div>
              <span className="font-mono text-xs text-recovered font-bold">
                {gatewayTestResult.latency_ms.toFixed(1)}ms Latency
              </span>
            </div>
            <CardDescription className="text-xs text-ink mt-0.5">
              {gatewayTestResult.message}
            </CardDescription>
          </CardHeader>
          <CardContent className="p-4 pt-2 grid grid-cols-1 sm:grid-cols-3 gap-3 font-mono text-xs border-t border-border/60">
            <div>
              <span className="text-ink-muted block text-[11px]">Key ID:</span>
              <span className="text-ink font-semibold">{gatewayTestResult.key_id}</span>
            </div>
            <div>
              <span className="text-ink-muted block text-[11px]">HMAC Signature Verification:</span>
              <Badge variant={gatewayTestResult.hmac_ready ? 'recovered' : 'pending'}>
                {gatewayTestResult.hmac_ready ? 'SHA-256 Verified' : 'Dev Simulation'}
              </Badge>
            </div>
            <div>
              <span className="text-ink-muted block text-[11px]">Supported Rails:</span>
              <span className="text-ink font-semibold">{gatewayTestResult.supported_rails.length.toString()} Rails Active</span>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Top Engine Health Bar with Live Ticking Uptime */}
      <Card className="border-recovered/40 bg-recovered-subtle/10">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <div>
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-recovered animate-pulse" />
              <CardTitle className="text-lg">System Status: {status.system_status}</CardTitle>
            </div>
            <CardDescription className="mt-1">
              All autonomous recovery pipelines, gateway webhooks, and policy guardrails are operational
            </CardDescription>
          </div>
          <Badge variant="recovered" className="font-mono">
            {status.environment.toUpperCase()}
          </Badge>
        </CardHeader>
        <CardContent className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-2 font-mono text-xs">
          <div>
            <span className="text-ink-muted block text-[11px]">Live System Uptime</span>
            <span className="text-sm font-semibold text-ink">{formatUptime(liveUptime)}</span>
          </div>
          <div>
            <span className="text-ink-muted block text-[11px]">Active Cases</span>
            <span className="text-sm font-semibold text-ink">{status.database_cases_count.toString()} total</span>
          </div>
          <div>
            <span className="text-ink-muted block text-[11px]">Recovery Queue</span>
            <span className="text-sm font-semibold text-accent">{status.active_recovery_queue.toString()} in-flight</span>
          </div>
          <div>
            <span className="text-ink-muted block text-[11px]">Escalation Queue</span>
            <span className="text-sm font-semibold text-escalated">{status.escalated_queue_count.toString()} pending</span>
          </div>
        </CardContent>
      </Card>

      {/* Subsystem Health Cards */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Gateway Integration */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <RazorpayIcon className="h-5 w-5 rounded-xs" />
                <CardTitle className="text-sm">Razorpay Integration</CardTitle>
              </div>
              <UpiIcon className="h-4 w-4" />
            </div>
            <CardDescription>Webhook ingress & Payment Links API</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 font-mono text-xs">
            <div className="flex justify-between items-center py-1 border-b border-border/60">
              <span className="text-ink-muted">Provider:</span>
              <span className="text-ink font-semibold">{status.gateway_integration.provider}</span>
            </div>
            <div className="flex justify-between items-center py-1 border-b border-border/60">
              <span className="text-ink-muted">Mode:</span>
              <Badge variant="outline">
                {status.gateway_integration.mode}
              </Badge>
            </div>
            <div className="flex justify-between items-center py-1 border-b border-border/60">
              <span className="text-ink-muted">Credentials:</span>
              <Badge variant={status.gateway_integration.authenticated ? 'recovered' : 'outline'}>
                {status.gateway_integration.authenticated ? 'Configured' : 'Offline Mock'}
              </Badge>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-ink-muted">Target URL:</span>
              <span className="text-[10px] text-ink-subtle truncate max-w-[140px]" title={status.gateway_integration.webhook_endpoint}>
                {status.gateway_integration.webhook_endpoint}
              </span>
            </div>
          </CardContent>
        </Card>

        {/* LLM Engine */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Cpu className="h-4 w-4 text-accent" />
              <CardTitle className="text-sm">LLM Reasoning Engine</CardTitle>
            </div>
            <CardDescription>Contextual failure diagnosis model</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 font-mono text-xs">
            <div className="flex justify-between items-center py-1 border-b border-border/60">
              <span className="text-ink-muted">Circuit Breaker:</span>
              <Badge variant="recovered">{status.llm_engine.circuit_breaker}</Badge>
            </div>
            <div className="flex justify-between items-center py-1 border-b border-border/60">
              <span className="text-ink-muted">Active Model:</span>
              <span className="text-accent text-[11px] font-semibold truncate max-w-[140px]" title={status.llm_engine.active_model}>
                {status.llm_engine.active_model}
              </span>
            </div>
            <div className="flex justify-between items-center py-1 border-b border-border/60">
              <span className="text-ink-muted">Deterministic Fallback:</span>
              <Badge variant="recovered">Active</Badge>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-ink-muted">Configured:</span>
              <span className="text-[10px] text-ink-subtle">
                {status.llm_engine.configured_providers.join(', ') || 'Rule Fallback'}
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Policy Engine */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Server className="h-4 w-4 text-recovered" />
              <CardTitle className="text-sm">Policy & Safety Gates</CardTitle>
            </div>
            <CardDescription>Deterministic execution constraints</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 font-mono text-xs">
            <div className="flex justify-between items-center py-1 border-b border-border/60">
              <span className="text-ink-muted">Max Touch Limit:</span>
              <span className="text-ink font-semibold">{status.policy_enforcement.max_touches_cap} touches</span>
            </div>
            <div className="flex justify-between items-center py-1 border-b border-border/60">
              <span className="text-ink-muted">Touch Cooldown:</span>
              <span className="text-ink font-semibold">{status.policy_enforcement.cooldown_hours}h</span>
            </div>
            <div className="flex justify-between items-center py-1 border-b border-border/60">
              <span className="text-ink-muted">Max Discount:</span>
              <span className="text-ink font-semibold">{(status.policy_enforcement.discount_cap_bps / 100).toFixed(0)}% ({status.policy_enforcement.discount_cap_bps} bps)</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-ink-muted">Holdout Control:</span>
              <span className="text-recovered font-semibold">{status.policy_enforcement.holdout_ratio_pct}% arm</span>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
