'use client'

import React, { useEffect, useState } from 'react'
import { CheckCircle2, Cpu, RotateCcw, Server, Zap } from 'lucide-react'
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
import {
  RazorpayIcon,
  RazorpaySymbol,
  UpiIcon,
} from '@/components/ui/BrandIcons'
import { SkeletonCard } from '@/components/ui/skeleton'
import { llmProviderLabel } from '@/lib/constants'

interface StatusViewProps {
  status: SystemStatusResponse | null
  loading: boolean
  onRefresh: () => void
  showPageHeader?: boolean
}

function formatUptime(seconds: number): string {
  const hrs = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  const secs = seconds % 60
  if (hrs > 0)
    return `${hrs.toString()}h ${mins.toString()}m ${secs.toString()}s`
  if (mins > 0) return `${mins.toString()}m ${secs.toString()}s`
  return `${secs.toString()}s`
}

export function StatusView({
  status,
  loading,
  onRefresh,
  showPageHeader = true,
}: StatusViewProps) {
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0)
  const [testingGateway, setTestingGateway] = useState<boolean>(false)
  const [gatewayTestResult, setGatewayTestResult] =
    useState<GatewayTestResponse | null>(null)

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
      {showPageHeader ? (
        <div className="flex flex-col justify-between gap-3 border-b border-border pb-4 sm:flex-row sm:items-center">
          <div>
            <div className="flex items-center gap-2">
              <RazorpaySymbol className="h-5 w-5" />
              <h1 className="text-xl font-bold text-ink">
                System Subsystems & Operational Health
              </h1>
            </div>
            <p className="mt-0.5 text-xs text-ink-muted">
              Real-time health and diagnostics for Razorpay webhooks, AI models,
              and deterministic policy subsystems.
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
              className="flex items-center gap-1.5 text-xs"
            >
              <Zap className="h-3.5 w-3.5 text-accent" />
              {testingGateway
                ? 'Probing Gateway...'
                : 'Test Razorpay Connection'}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={onRefresh}
              className="flex items-center gap-1.5 text-xs"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Refresh
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-end">
          <Button
            variant="outline"
            size="sm"
            onClick={onRefresh}
            className="flex items-center gap-1.5 text-xs"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        </div>
      )}

      {/* Gateway Probe Diagnostic Result (if run) */}
      {gatewayTestResult && (
        <Card className="animate-in fade-in-0 border-accent/40 bg-accent-subtle/10 duration-200">
          <CardHeader className="p-4 pb-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-recovered" />
                <CardTitle className="text-sm font-bold text-ink">
                  Razorpay Gateway Handshake Diagnostic:{' '}
                  {gatewayTestResult.status}
                </CardTitle>
              </div>
              <span className="text-xs font-bold text-recovered">
                {gatewayTestResult.latency_ms.toFixed(1)}ms Latency
              </span>
            </div>
            <CardDescription className="mt-0.5 text-xs text-ink">
              {gatewayTestResult.message}
            </CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-3 border-t border-border/60 p-4 pt-2 text-xs sm:grid-cols-3">
            <div>
              <span className="block text-[11px] text-ink-muted">Key ID:</span>
              <span className="font-semibold text-ink">
                {gatewayTestResult.key_id}
              </span>
            </div>
            <div>
              <span className="block text-[11px] text-ink-muted">
                Webhook Security:
              </span>
              <Badge
                variant={gatewayTestResult.hmac_ready ? 'recovered' : 'pending'}
              >
                {gatewayTestResult.hmac_ready ? 'Verified' : 'Dev Simulation'}
              </Badge>
            </div>
            <div>
              <span className="block text-[11px] text-ink-muted">
                Supported Rails:
              </span>
              <span className="font-semibold text-ink">
                {gatewayTestResult.supported_rails.length.toString()} Rails
                Active
              </span>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Top Engine Health Bar with Live Ticking Uptime */}
      <Card className="border-recovered/40 bg-recovered-subtle/10">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <div>
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-recovered" />
              <CardTitle className="text-lg">
                System Status: {status.system_status}
              </CardTitle>
            </div>
            <CardDescription className="mt-1">
              All autonomous recovery pipelines, gateway webhooks, and policy
              guardrails are operational
            </CardDescription>
          </div>
          <Badge variant="recovered">{status.environment.toUpperCase()}</Badge>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-4 pt-2 text-xs sm:grid-cols-4">
          <div>
            <span className="block text-[11px] text-ink-muted">
              Live System Uptime
            </span>
            <span className="text-sm font-semibold text-ink">
              {formatUptime(liveUptime)}
            </span>
          </div>
          <div>
            <span className="block text-[11px] text-ink-muted">
              Active Cases
            </span>
            <span className="text-sm font-semibold text-ink">
              {status.database_cases_count.toString()} total
            </span>
          </div>
          <div>
            <span className="block text-[11px] text-ink-muted">
              Recovery Queue
            </span>
            <span className="text-sm font-semibold text-accent">
              {status.active_recovery_queue.toString()} in-flight
            </span>
          </div>
          <div>
            <span className="block text-[11px] text-ink-muted">
              Escalation Queue
            </span>
            <span className="text-sm font-semibold text-escalated">
              {status.escalated_queue_count.toString()} pending
            </span>
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
            <CardDescription>
              Webhook ingress & Payment Links API
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-xs">
            <div className="flex items-center justify-between border-b border-border/60 py-1">
              <span className="text-ink-muted">Provider:</span>
              <span className="font-semibold text-ink">
                {status.gateway_integration.provider}
              </span>
            </div>
            <div className="flex items-center justify-between border-b border-border/60 py-1">
              <span className="text-ink-muted">Mode:</span>
              <Badge variant="outline">{status.gateway_integration.mode}</Badge>
            </div>
            <div className="flex items-center justify-between border-b border-border/60 py-1">
              <span className="text-ink-muted">Credentials:</span>
              <Badge
                variant={
                  status.gateway_integration.authenticated
                    ? 'recovered'
                    : 'outline'
                }
              >
                {status.gateway_integration.authenticated
                  ? 'Configured'
                  : 'Offline Mock'}
              </Badge>
            </div>
            <div className="flex items-center justify-between py-1">
              <span className="text-ink-muted">Target URL:</span>
              <span
                className="max-w-[140px] truncate text-[10px] text-ink-subtle"
                title={status.gateway_integration.webhook_endpoint}
              >
                {status.gateway_integration.webhook_endpoint}
              </span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Cpu className="h-4 w-4 text-accent" />
              <CardTitle className="text-sm">Diagnosis engine</CardTitle>
            </div>
            <CardDescription>
              What is deciding each recovery plan
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-xs">
            {!status.llm_engine.deterministic_fallback_active &&
            status.llm_engine.active_model ? (
              <>
                <div className="flex items-center justify-between border-b border-border/60 py-1">
                  <span className="text-ink-muted">Deciding with</span>
                  <span
                    className="max-w-[180px] truncate text-[11px] font-semibold text-accent"
                    title={status.llm_engine.active_model}
                  >
                    {llmProviderLabel(status.llm_engine.active_provider)}
                  </span>
                </div>
                <div className="flex items-center justify-between py-1">
                  <span className="text-ink-muted">If the model fails</span>
                  <Badge variant="recovered">Falls back to rules</Badge>
                </div>
              </>
            ) : (
              <div className="flex items-center justify-between py-1">
                <span className="text-ink-muted">Deciding with</span>
                <Badge variant="pending">Built-in rules</Badge>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Policy Engine */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Server className="h-4 w-4 text-recovered" />
              <CardTitle className="text-sm">Policy & Safety Gates</CardTitle>
            </div>
            <CardDescription>
              Deterministic execution constraints
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-xs">
            <div className="flex items-center justify-between border-b border-border/60 py-1">
              <span className="text-ink-muted">Max Attempt Limit:</span>
              <span className="font-semibold text-ink">
                {status.policy_enforcement.max_attempts_cap} attempts
              </span>
            </div>
            <div className="flex items-center justify-between border-b border-border/60 py-1">
              <span className="text-ink-muted">Attempt Cooldown:</span>
              <span className="font-semibold text-ink">
                {status.policy_enforcement.cooldown_hours}h
              </span>
            </div>
            <div className="flex items-center justify-between border-b border-border/60 py-1">
              <span className="text-ink-muted">Max Discount:</span>
              <span className="font-semibold text-ink">
                {(status.policy_enforcement.discount_cap_bps / 100).toFixed(0)}%
                ({status.policy_enforcement.discount_cap_bps} bps)
              </span>
            </div>
            <div className="flex items-center justify-between py-1">
              <span className="text-ink-muted">Holdout Control:</span>
              <span className="font-semibold text-recovered">
                {status.policy_enforcement.holdout_ratio_pct}% arm
              </span>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
