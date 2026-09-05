'use client'

import React, { useEffect, useState } from 'react'
import {
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Coins,
  Cpu,
  FlaskConical,
  Save,
  Server,
} from 'lucide-react'
import {
  getLlmConfig,
  getLlmReport,
  listExperiments,
  testGatewayConnection,
  updateLlmConfig,
  type ExperimentMetric,
  type GatewayTestResponse,
  type LLMReportResponse,
  type LLMSettingsState,
  type SystemSettingsResponse,
} from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { CopyButton } from '@/components/ui/CopyButton'
import { CredentialImportPanel } from '@/components/settings/CredentialImportPanel'
import { OAuthConnectPanel } from '@/components/settings/OAuthConnectPanel'
import {
  MANDATORY_LLM_PROVIDER_NAME,
  WEBHOOK_INGRESS_PATH,
} from '@/lib/constants'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { RazorpaySymbol } from '@/components/ui/BrandIcons'
import { SkeletonCard } from '@/components/ui/skeleton'

interface IntegrationsViewProps {
  settings: SystemSettingsResponse | null
  loading: boolean
  onRefresh: () => void
}

export function IntegrationsView({
  settings,
  loading,
  onRefresh,
}: IntegrationsViewProps) {
  const [testingGateway, setTestingGateway] = useState(false)
  const [gatewayTestResult, setGatewayTestResult] =
    useState<GatewayTestResponse | null>(null)

  const [llmConfig, setLlmConfig] = useState<LLMSettingsState | null>(null)
  const [llmReport, setLlmReport] = useState<LLMReportResponse | null>(null)
  const [experiments, setExperiments] = useState<ExperimentMetric[]>([])
  const [savingConfig, setSavingConfig] = useState<boolean>(false)
  const [saveSuccess, setSaveSuccess] = useState<boolean>(false)

  useEffect(() => {
    getLlmConfig()
      .then(setLlmConfig)
      .catch(() => null)
    getLlmReport()
      .then(setLlmReport)
      .catch(() => null)
    listExperiments()
      .then(setExperiments)
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
    if (name === MANDATORY_LLM_PROVIDER_NAME) return
    const updated = {
      ...llmConfig,
      providers: llmConfig.providers.map((p) =>
        p.name === name ? { ...p, enabled: !p.enabled } : p,
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
        p.name === providerName ? { ...p, active_model: model } : p,
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
      const freshReport = await getLlmReport()
      setLlmReport(freshReport)
    } finally {
      setSavingConfig(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="border-b border-border pb-4">
        <h1 className="text-2xl font-bold text-ink">Integrations</h1>
        <p className="mt-0.5 text-sm text-ink-muted">
          Razorpay gateway connectivity, webhook ingress, LLM provider
          hierarchy, and subsystem health.
        </p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Server className="h-4 w-4 text-accent" />
            <CardTitle>Razorpay Webhook & Payment Gateway</CardTitle>
          </div>
          <CardDescription className="text-xs">
            Production connection parameters for webhook ingress and recovery
            link generation.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {loading ? (
            <SkeletonCard />
          ) : (
            <div className="grid grid-cols-1 gap-4 text-xs md:grid-cols-2">
              <div className="space-y-2 rounded-control border border-accent/30 bg-accent/5 p-3 md:col-span-2">
                <span className="block text-[11px] text-ink-muted">
                  Linked Merchant Account
                </span>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-bold text-ink uppercase">
                    {settings?.razorpay_account_name ||
                      settings?.razorpay_account_id ||
                      'Name unavailable in test mode'}
                  </span>
                  {settings?.razorpay_account_type && (
                    <Badge variant="outline" className="text-[10px] uppercase">
                      {settings.razorpay_account_type}
                    </Badge>
                  )}
                  {settings?.razorpay_account_status && (
                    <Badge
                      variant={
                        settings.razorpay_account_status === 'active'
                          ? 'recovered'
                          : 'pending'
                      }
                      className="text-[10px] uppercase"
                    >
                      {settings.razorpay_account_status}
                    </Badge>
                  )}
                </div>
                {settings?.razorpay_account_id && (
                  <div className="text-[11px] text-ink-muted">
                    Account ID:{' '}
                    <span className="text-ink select-all">
                      {settings.razorpay_account_id}
                    </span>
                  </div>
                )}
              </div>

              <div className="grid grid-cols-4 gap-3 text-xs md:col-span-2">
                <div className="space-y-1 rounded-control border border-border bg-surface-sunken p-3">
                  <span className="block text-[11px] text-ink-muted">
                    Environment
                  </span>
                  <span className="font-bold text-ink uppercase">
                    {settings?.environment || 'Not configured'}
                  </span>
                </div>

                <div className="space-y-1 rounded-control border border-border bg-surface-sunken p-3">
                  <span className="block text-[11px] text-ink-muted">
                    Gateway Mode
                  </span>
                  <div className="flex items-center gap-1.5">
                    <span className="font-bold text-ink uppercase">
                      {settings?.razorpay_mode || 'Unset'}
                    </span>
                    <Badge
                      variant={
                        settings?.razorpay_mode === 'LIVE'
                          ? 'recovered'
                          : settings?.razorpay_mode === 'TEST'
                            ? 'pending'
                            : 'outline'
                      }
                      className="text-[10px]"
                    >
                      {settings?.razorpay_key_id
                        ? 'derived from key'
                        : 'no key'}
                    </Badge>
                  </div>
                </div>

                <div className="space-y-1 rounded-control border border-border bg-surface-sunken p-3">
                  <span className="block text-[11px] text-ink-muted">
                    Key ID
                  </span>
                  <span className="font-semibold text-ink">
                    {settings?.razorpay_key_id
                      ? `${settings.razorpay_key_id.slice(0, 10)}...`
                      : 'Not configured'}
                  </span>
                </div>

                <div className="min-w-0 space-y-1 rounded-control border border-border bg-surface-sunken p-3">
                  <span className="block text-[11px] text-ink-muted">
                    Webhook
                  </span>
                  <div className="flex min-w-0 items-center gap-1.5">
                    <span className="min-w-0 truncate text-ink select-all">
                      {settings?.webhook_ingress_url || WEBHOOK_INGRESS_PATH}
                    </span>
                    <CopyButton
                      value={
                        settings?.webhook_ingress_url ?? WEBHOOK_INGRESS_PATH
                      }
                      subject="webhook endpoint"
                      variant="outline"
                    />
                    <Badge
                      variant={
                        settings?.webhook_secret_configured
                          ? 'recovered'
                          : 'outline'
                      }
                      className="shrink-0 text-[10px]"
                    >
                      {settings?.webhook_secret_configured
                        ? 'Verified'
                        : 'Unsigned'}
                    </Badge>
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3 pt-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                void handleTestGateway()
              }}
              disabled={testingGateway}
              className="cursor-pointer gap-2 text-xs"
            >
              <RazorpaySymbol className="h-3.5 w-3.5" />
              <span>
                {testingGateway
                  ? 'Testing Gateway...'
                  : 'Test Gateway Connection'}
              </span>
            </Button>
            {gatewayTestResult ? (
              <span className="flex items-center gap-1.5 text-xs text-recovered">
                <CheckCircle2 className="h-3.5 w-3.5" />
                {gatewayTestResult.message} (
                {gatewayTestResult.latency_ms.toFixed(0)}ms)
              </span>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <OAuthConnectPanel onChanged={onRefresh} />

      <CredentialImportPanel onImported={onRefresh} />

      <div className="border-b border-border pt-2 pb-2">
        <h2 className="text-lg font-bold text-ink">LLM</h2>
        <p className="mt-0.5 text-xs text-ink-muted">
          AI reasoning engine provider hierarchy, model telemetry, and
          experiment evaluation.
        </p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
            <div>
              <div className="flex items-center gap-2">
                <Cpu className="h-4 w-4 text-accent" />
                <CardTitle>AI Reasoning Engine & Provider Hierarchy</CardTitle>
              </div>
              <CardDescription className="text-xs">
                Configure fallback priority, model models, and enable/disable
                LLM providers dynamically
              </CardDescription>
            </div>

            <Button
              variant="primary"
              size="sm"
              disabled={savingConfig || !llmConfig}
              onClick={() => {
                void handleSaveLLMConfig()
              }}
              className="cursor-pointer gap-2 self-start text-xs sm:self-auto"
            >
              {saveSuccess ? (
                <Check className="h-3.5 w-3.5 text-recovered" />
              ) : (
                <Save className="h-3.5 w-3.5" />
              )}
              <span>
                {savingConfig
                  ? 'Saving...'
                  : saveSuccess
                    ? 'Saved to Store'
                    : 'Save LLM Settings'}
              </span>
            </Button>
          </div>
        </CardHeader>
        <CardContent className="p-4">
          {llmConfig && llmConfig.providers.length > 0 && (
            <div className="data-table-shell">
              <table className="data-table w-full text-xs">
                <thead className="text-[10px] uppercase">
                  <tr>
                    <th className="p-2.5 text-left">Priority</th>
                    <th className="p-2.5 text-left">Provider</th>
                    <th className="p-2.5 text-left">API Key</th>
                    <th className="p-2.5 text-left">Active Model</th>
                    <th className="p-2.5 text-left">Status</th>
                    <th className="p-2.5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {llmConfig.providers.map((provider, idx) => (
                    <tr
                      key={provider.name}
                      className={provider.enabled ? '' : 'opacity-60'}
                    >
                      <td className="p-2.5 font-mono font-bold text-ink">
                        #{provider.priority.toString()}
                      </td>
                      <td className="p-2.5 font-semibold text-ink">
                        {provider.label}
                      </td>
                      <td className="p-2.5">
                        <Badge
                          variant={
                            provider.has_api_key ? 'recovered' : 'outline'
                          }
                          className="text-[10px]"
                        >
                          {provider.has_api_key ? 'Configured' : 'No Key'}
                        </Badge>
                      </td>
                      <td className="p-2.5">
                        <select
                          value={provider.active_model}
                          onChange={(e) => {
                            handleSelectModel(provider.name, e.target.value)
                          }}
                          disabled={!provider.enabled}
                          aria-label={`Active model for ${provider.label}`}
                          className="cursor-pointer rounded-control border border-border bg-surface px-2 py-1 text-xs text-ink focus:outline-hidden"
                        >
                          {provider.available_models.map((m) => (
                            <option key={m} value={m}>
                              {m}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="p-2.5">
                        {provider.name === MANDATORY_LLM_PROVIDER_NAME ? (
                          <Badge variant="outline" className="text-[10px]">
                            Always Active
                          </Badge>
                        ) : (
                          <Button
                            variant={provider.enabled ? 'primary' : 'outline'}
                            size="sm"
                            onClick={() => {
                              handleToggleProvider(provider.name)
                            }}
                            className="h-7 cursor-pointer px-2.5 text-xs"
                          >
                            {provider.enabled ? 'Enabled' : 'Disabled'}
                          </Button>
                        )}
                      </td>
                      <td className="p-2.5 text-right">
                        <div className="inline-flex items-center overflow-hidden rounded-control border border-border bg-surface">
                          <button
                            type="button"
                            disabled={idx === 0}
                            onClick={() => {
                              handleMovePriority(idx, 'up')
                            }}
                            className="cursor-pointer border-r border-border p-1 text-ink transition-colors hover:bg-surface-sunken disabled:cursor-not-allowed disabled:opacity-30"
                            title="Move Priority Up"
                          >
                            <ChevronUp className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            disabled={idx === llmConfig.providers.length - 1}
                            onClick={() => {
                              handleMovePriority(idx, 'down')
                            }}
                            className="cursor-pointer p-1 text-ink transition-colors hover:bg-surface-sunken disabled:cursor-not-allowed disabled:opacity-30"
                            title="Move Priority Down"
                          >
                            <ChevronDown className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {llmReport && (
        <Card>
          <CardHeader className="border-b border-border/40 pb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Coins className="h-4 w-4 text-accent" />
                <CardTitle className="text-base font-semibold">
                  AI Model Telemetry & Token Accounting
                </CardTitle>
              </div>
              <span className="text-xs font-bold text-ink">
                Total USD Cost: ${(llmReport.total_cost_usd || 0).toFixed(5)}
              </span>
            </div>
            <CardDescription className="text-xs">
              Live aggregations derived directly from the model_telemetry
              relational store
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 p-4">
            <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
              <div className="rounded-control border border-border bg-surface-sunken p-3">
                <span className="block text-[11px] text-ink-muted">
                  Total Calls
                </span>
                <span className="mt-0.5 block text-sm font-bold text-ink">
                  {llmReport.total_calls.toString()}
                </span>
              </div>
              <div className="rounded-control border border-border bg-surface-sunken p-3">
                <span className="block text-[11px] text-ink-muted">
                  Input Tokens
                </span>
                <span className="mt-0.5 block text-sm font-bold text-ink">
                  {llmReport.total_input_tokens.toLocaleString()}
                </span>
              </div>
              <div className="rounded-control border border-border bg-surface-sunken p-3">
                <span className="block text-[11px] text-ink-muted">
                  Output Tokens
                </span>
                <span className="mt-0.5 block text-sm font-bold text-ink">
                  {llmReport.total_output_tokens.toLocaleString()}
                </span>
              </div>
              <div className="rounded-control border border-recovered/40 bg-surface-sunken p-3">
                <span className="block text-[11px] font-semibold text-recovered">
                  Total Cost
                </span>
                <span className="mt-0.5 block text-sm font-bold text-recovered">
                  ${(llmReport.total_cost_usd || 0).toFixed(5)}
                </span>
              </div>
            </div>

            {llmReport.model_breakdown.length > 0 && (
              <div className="data-table-shell">
                <table className="data-table w-full text-xs">
                  <thead className="text-[10px] uppercase">
                    <tr>
                      <th className="p-2.5 text-left">Model</th>
                      <th className="p-2.5 text-left">Provider</th>
                      <th className="p-2.5 text-right">Calls</th>
                      <th className="p-2.5 text-right">
                        Latency (Avg / p50 / p95)
                      </th>
                      <th className="p-2.5 text-right">Tokens (In / Out)</th>
                      <th className="p-2.5 text-right">Cost (USD)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {llmReport.model_breakdown.map((row) => (
                      <tr key={`${row.provider}-${row.model}`}>
                        <td className="p-2.5 font-semibold text-ink">
                          {row.model}
                        </td>
                        <td className="p-2.5 text-ink-muted uppercase">
                          {row.provider}
                        </td>
                        <td className="p-2.5 text-right text-ink">
                          {row.call_count.toString()}
                          {row.fallback_count && row.fallback_count > 0 ? (
                            <span className="text-warning ml-1 text-[10px]">
                              ({row.fallback_count} fb)
                            </span>
                          ) : null}
                        </td>
                        <td className="p-2.5 text-right text-accent">
                          {row.avg_latency_ms.toFixed(0)}ms /{' '}
                          {(row.p50_latency_ms || 0).toFixed(0)}ms /{' '}
                          {(row.p95_latency_ms || 0).toFixed(0)}ms
                        </td>
                        <td className="p-2.5 text-right text-ink-muted">
                          {row.total_input_tokens.toLocaleString()} /{' '}
                          {row.total_output_tokens.toLocaleString()}
                        </td>
                        <td className="p-2.5 text-right font-semibold text-recovered">
                          ${(row.total_cost_usd || 0).toFixed(5)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="border-b border-border/40 pb-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FlaskConical className="h-4 w-4 text-accent" />
              <CardTitle className="text-base font-semibold">
                A/B Model Experiment Cohorts
              </CardTitle>
            </div>
            <Badge variant="outline" className="text-xs">
              {experiments.length} Active Experiments
            </Badge>
          </div>
          <CardDescription className="text-xs">
            Controlled model-vs-model comparisons with holdout control arm
            baseline integrity
          </CardDescription>
        </CardHeader>
        <CardContent className="p-4">
          {experiments.length === 0 ? (
            <div className="py-6 text-center text-xs text-ink-muted">
              No experiment tags registered yet. Seed cohorts with experiment
              tags to compare models.
            </div>
          ) : (
            <div className="data-table-shell">
              <table className="data-table w-full text-xs">
                <thead className="text-[10px] uppercase">
                  <tr>
                    <th className="p-2.5 text-left">Experiment Tag</th>
                    <th className="p-2.5 text-left">Model</th>
                    <th className="p-2.5 text-left">Provider</th>
                    <th className="p-2.5 text-right">Cohort Size</th>
                    <th className="p-2.5 text-right">Recovery Rate</th>
                    <th className="p-2.5 text-right">Avg Latency</th>
                    <th className="p-2.5 text-right">Total Cost</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {experiments.map((exp) => (
                    <tr
                      key={`${exp.experiment_tag}-${exp.model}`}
                      className="hover:bg-surface-sunken/40"
                    >
                      <td className="p-2.5 font-bold text-accent">
                        {exp.experiment_tag}
                      </td>
                      <td className="p-2.5 font-semibold text-ink">
                        {exp.model}
                      </td>
                      <td className="p-2.5 text-ink-muted uppercase">
                        {exp.provider}
                      </td>
                      <td className="p-2.5 text-right text-ink">
                        {exp.cohort_size.toString()}
                      </td>
                      <td className="p-2.5 text-right font-bold text-recovered">
                        {(exp.recovery_rate * 100).toFixed(1)}% (
                        {exp.recovered_count}/{exp.cohort_size})
                      </td>
                      <td className="p-2.5 text-right text-ink-muted">
                        {exp.avg_latency_ms.toFixed(0)}ms
                      </td>
                      <td className="p-2.5 text-right font-semibold text-ink">
                        ${exp.total_cost_usd.toFixed(5)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
