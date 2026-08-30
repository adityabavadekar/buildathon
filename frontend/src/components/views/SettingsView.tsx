'use client'

import React, { useEffect, useState } from 'react'
import {
  ArrowDown,
  ArrowUp,
  Check,
  CheckCircle2,
  Coins,
  Cpu,
  RefreshCw,
  Server,
  Zap,
} from 'lucide-react'
import {
  getLlmConfig,
  getLlmReport,
  testGatewayConnection,
  updateLlmConfig,
  type GatewayTestResponse,
  type LLMReportResponse,
  type LLMSettingsState,
  type SystemSettingsResponse,
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

interface SettingsViewProps {
  settings: SystemSettingsResponse | null
  loading: boolean
}

export function SettingsView({ settings, loading }: SettingsViewProps) {
  const [testingGateway, setTestingGateway] = useState<boolean>(false)
  const [gatewayTestResult, setGatewayTestResult] = useState<GatewayTestResponse | null>(null)

  const [llmConfig, setLlmConfig] = useState<LLMSettingsState | null>(null)
  const [llmReport, setLlmReport] = useState<LLMReportResponse | null>(null)
  const [savingConfig, setSavingConfig] = useState<boolean>(false)
  const [saveSuccess, setSaveSuccess] = useState<boolean>(false)

  useEffect(() => {
    getLlmConfig()
      .then(setLlmConfig)
      .catch(() => null)
    getLlmReport()
      .then(setLlmReport)
      .catch(() => null)
  }, [])

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

  const handleToggleProvider = (name: string) => {
    if (!llmConfig) return
    const updated = {
      ...llmConfig,
      providers: llmConfig.providers.map((p) =>
        p.name === name ? { ...p, enabled: !p.enabled } : p
      ),
    }
    setLlmConfig(updated)
  }

  const handleMovePriority = (index: number, direction: 'up' | 'down') => {
    if (!llmConfig) return
    const newIdx = direction === 'up' ? index - 1 : index + 1
    if (newIdx < 0 || newIdx >= llmConfig.providers.length) return

    const providers = [...llmConfig.providers]
    const item = providers[index]
    if (!item) return
    providers.splice(index, 1)
    providers.splice(newIdx, 0, item)

    const reIndexed = providers.map((p, idx) => ({ ...p, priority: idx + 1 }))
    setLlmConfig({ ...llmConfig, providers: reIndexed })
  }

  const handleSelectModel = (providerName: string, model: string) => {
    if (!llmConfig) return
    const updated = {
      ...llmConfig,
      providers: llmConfig.providers.map((p) =>
        p.name === providerName ? { ...p, active_model: model } : p
      ),
    }
    setLlmConfig(updated)
  }

  const handleSaveLLMConfig = async () => {
    if (!llmConfig) return
    try {
      setSavingConfig(true)
      const saved = await updateLlmConfig(llmConfig)
      setLlmConfig(saved)
      setSaveSuccess(true)
      setTimeout(() => {
        setSaveSuccess(false)
      }, 3000)
    } finally {
      setSavingConfig(false)
    }
  }

  if (loading || !settings) {
    return <SkeletonCard />
  }

  return (
    <div className="space-y-6">
      {/* View Header with Plain-Language Context */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border pb-4">
        <div>
          <div className="flex items-center gap-2">
            <RazorpaySymbol className="h-6 w-6" />
            <h1 className="text-2xl font-bold font-mono text-ink">
              Merchant Settings & LLM Configuration
            </h1>
          </div>
          <p className="text-sm text-ink-muted mt-0.5">
            Razorpay merchant profile, dynamic AI provider fallback chain, and historical token cost reporting.
          </p>
        </div>
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
      </div>

      {/* Gateway Probe Diagnostic Card */}
      {gatewayTestResult && (
        <Card className="border-accent/40 bg-accent-subtle/10 animate-in fade-in-0 duration-200">
          <CardHeader className="p-5 pb-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-recovered" />
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
          <CardContent className="p-5 pt-2 grid grid-cols-1 sm:grid-cols-3 gap-3 font-mono text-xs border-t border-border/60">
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
              <span className="text-ink font-semibold">{gatewayTestResult.supported_rails.length.toString()} Rails Configured</span>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Merchant Profile & Account Overview */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div className="flex items-center gap-2.5">
            <RazorpayIcon className="h-6 w-6 rounded-xs" />
            <div>
              <CardTitle>Razorpay Merchant Profile</CardTitle>
              <CardDescription className="text-xs">
                Live gateway account details, settlement cycle, and webhook integration
              </CardDescription>
            </div>
          </div>
          <Badge variant="recovered">Active Merchant</Badge>
        </CardHeader>
        <CardContent className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 font-mono text-xs pt-2">
          <div className="p-3 rounded-control bg-surface-sunken border border-border">
            <span className="text-ink-muted block text-[11px]">Merchant ID</span>
            <span className="text-ink font-bold text-sm">merch_rzp_prod_01</span>
          </div>
          <div className="p-3 rounded-control bg-surface-sunken border border-border">
            <span className="text-ink-muted block text-[11px]">Default Currency</span>
            <span className="text-ink font-bold text-sm">INR (Minor units: paise)</span>
          </div>
          <div className="p-3 rounded-control bg-surface-sunken border border-border">
            <span className="text-ink-muted block text-[11px]">Settlement Schedule</span>
            <span className="text-ink font-bold text-sm">T+1 Rolling Daily</span>
          </div>
          <div className="p-3 rounded-control bg-surface-sunken border border-border">
            <span className="text-ink-muted block text-[11px]">Account Tier</span>
            <span className="text-accent font-bold text-sm">Standard (Track 3)</span>
          </div>
        </CardContent>
      </Card>

      {/* Webhook Ingress Configuration */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Server className="h-4 w-4 text-accent" />
              <CardTitle>Razorpay Webhook Ingress Endpoint</CardTitle>
            </div>
            <UpiIcon className="h-4 w-4" />
          </div>
          <CardDescription className="text-xs">
            Configure this target URL inside your Razorpay Merchant Dashboard under Settings &gt; Webhooks
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-xs font-mono text-ink-muted uppercase block mb-1">
              Webhook Ingress URL
            </label>
            <div className="flex items-center gap-2">
              <input
                type="text"
                readOnly
                value={settings.webhook_ingress_url}
                className="flex-1 rounded-control bg-surface-sunken border border-border px-3 py-2 text-xs font-mono text-ink select-all"
              />
            </div>
            <div className="mt-2 flex items-center gap-2">
              <span className="text-[11px] font-mono text-ink-subtle">
                HMAC-SHA256 Secret Verification:
              </span>
              <Badge variant={settings.webhook_secret_configured ? 'recovered' : 'pending'}>
                {settings.webhook_secret_configured ? 'Active (SHA-256)' : 'Unset (Dev Fallback)'}
              </Badge>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Dynamic LLM Provider Fallback Hierarchy */}
      <Card>
        <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <Cpu className="h-4 w-4 text-accent" />
              <CardTitle>AI Reasoning Engine & Provider Fallback Priority</CardTitle>
            </div>
            <CardDescription className="text-xs">
              Reorder fallback hierarchy, toggle providers, and select active models. Persisted to disk.
            </CardDescription>
          </div>
          <Button
            size="sm"
            onClick={() => {
              void handleSaveLLMConfig()
            }}
            disabled={savingConfig}
            className="font-mono text-xs flex items-center gap-1.5"
          >
            {saveSuccess ? (
              <>
                <Check className="h-3.5 w-3.5 text-white" />
                <span>Saved to Disk!</span>
              </>
            ) : (
              <>
                <RefreshCw className={`h-3.5 w-3.5 ${savingConfig ? 'animate-spin' : ''}`} />
                <span>{savingConfig ? 'Saving...' : 'Save LLM Settings'}</span>
              </>
            )}
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          {llmConfig?.providers.map((provider, idx) => (
            <div
              key={provider.name}
              className={`p-4 rounded-panel border flex flex-col sm:flex-row sm:items-center justify-between gap-3 transition-colors ${
                provider.enabled
                  ? 'border-border bg-surface-sunken/40'
                  : 'border-border/40 bg-surface-sunken/10 opacity-60'
              }`}
            >
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-bold text-accent">
                    #{provider.priority.toString()}
                  </span>
                  <span className="font-mono text-xs font-semibold text-ink">
                    {provider.label}
                  </span>
                  <Badge variant={provider.has_api_key ? 'recovered' : 'outline'} className="text-[10px]">
                    {provider.has_api_key ? 'API Key Configured' : 'No Key'}
                  </Badge>
                </div>

                {/* Model Selector */}
                <div className="flex items-center gap-2 pt-1 font-mono text-xs">
                  <span className="text-ink-muted text-[11px]">Active Model:</span>
                  <select
                    value={provider.active_model}
                    onChange={(e) => {
                      handleSelectModel(provider.name, e.target.value)
                    }}
                    disabled={!provider.enabled}
                    className="rounded-control border border-border bg-surface px-2 py-1 text-xs font-mono text-ink focus:outline-none"
                  >
                    {provider.available_models.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Actions: Priority Reorder & Enable Toggle */}
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={idx === 0}
                  onClick={() => {
                    handleMovePriority(idx, 'up')
                  }}
                  className="h-7 w-7 p-0"
                  title="Move Priority Up"
                >
                  <ArrowUp className="h-3 w-3" />
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={idx === (llmConfig.providers.length - 1)}
                  onClick={() => {
                    handleMovePriority(idx, 'down')
                  }}
                  className="h-7 w-7 p-0"
                  title="Move Priority Down"
                >
                  <ArrowDown className="h-3 w-3" />
                </Button>
                <Button
                  variant={provider.enabled ? 'primary' : 'outline'}
                  size="sm"
                  onClick={() => {
                    handleToggleProvider(provider.name)
                  }}
                  className="h-7 font-mono text-xs"
                >
                  {provider.enabled ? 'Enabled' : 'Disabled'}
                </Button>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Historical LLM Token, Latency & Cost Report */}
      {llmReport && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Coins className="h-4 w-4 text-recovered" />
              <CardTitle>Historical LLM Token, Latency & Cost Report</CardTitle>
            </div>
            <CardDescription className="text-xs">
              Audit log aggregation across all AI failure diagnoses, dunning message generation, and token expenditures
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Aggregate Metrics */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 font-mono text-xs">
              <div className="p-3 rounded-control bg-surface-sunken border border-border">
                <span className="text-ink-muted block text-[11px]">Total AI Invocations</span>
                <span className="text-ink font-bold text-base">{llmReport.total_calls.toString()} calls</span>
              </div>
              <div className="p-3 rounded-control bg-surface-sunken border border-border">
                <span className="text-ink-muted block text-[11px]">Total Tokens In/Out</span>
                <span className="text-ink font-bold text-base">
                  {llmReport.total_input_tokens.toString()} / {llmReport.total_output_tokens.toString()}
                </span>
              </div>
              <div className="p-3 rounded-control bg-surface-sunken border border-border">
                <span className="text-ink-muted block text-[11px]">Average Latency</span>
                <span className="text-accent font-bold text-base">{llmReport.average_latency_ms.toFixed(1)}ms</span>
              </div>
              <div className="p-3 rounded-control bg-surface-sunken border border-recovered/40">
                <span className="text-recovered block text-[11px]">Total LLM Cost</span>
                <span className="text-recovered font-bold text-base">${llmReport.total_cost_usd.toFixed(4)} USD</span>
              </div>
            </div>

            {/* Model Breakdown Table */}
            {llmReport.model_breakdown.length > 0 && (
              <div className="overflow-x-auto border border-border rounded-control">
                <table className="w-full text-xs font-mono">
                  <thead className="bg-surface-sunken border-b border-border text-ink-muted">
                    <tr>
                      <th className="p-2.5 text-left">Model Name</th>
                      <th className="p-2.5 text-left">Provider</th>
                      <th className="p-2.5 text-right">Invocations</th>
                      <th className="p-2.5 text-right">Input Tokens</th>
                      <th className="p-2.5 text-right">Output Tokens</th>
                      <th className="p-2.5 text-right">Avg Latency</th>
                      <th className="p-2.5 text-right">Cost (USD)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {llmReport.model_breakdown.map((row) => (
                      <tr key={row.model} className="hover:bg-surface-sunken/40">
                        <td className="p-2.5 font-semibold text-ink truncate max-w-[200px]" title={row.model}>
                          {row.model}
                        </td>
                        <td className="p-2.5 uppercase text-ink-muted">{row.provider}</td>
                        <td className="p-2.5 text-right font-semibold">{row.call_count.toString()}</td>
                        <td className="p-2.5 text-right text-ink-muted">{row.total_input_tokens.toString()}</td>
                        <td className="p-2.5 text-right text-ink-muted">{row.total_output_tokens.toString()}</td>
                        <td className="p-2.5 text-right text-accent font-semibold">{row.avg_latency_ms.toFixed(1)}ms</td>
                        <td className="p-2.5 text-right font-bold text-recovered">${row.total_cost_usd.toFixed(4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
