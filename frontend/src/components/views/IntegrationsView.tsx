'use client'

import React, { useState } from 'react'
import { CheckCircle2, Server } from 'lucide-react'
import {
  testGatewayConnection,
  type GatewayTestResponse,
  type SystemSettingsResponse,
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
import { RazorpaySymbol } from '@/components/ui/BrandIcons'
import { SkeletonCard } from '@/components/ui/skeleton'
import { StatusView } from '@/components/views/StatusView'

interface IntegrationsViewProps {
  settings: SystemSettingsResponse | null
  status: SystemStatusResponse | null
  loading: boolean
  onRefresh: () => void
}

export function IntegrationsView({
  settings,
  status,
  loading,
  onRefresh,
}: IntegrationsViewProps) {
  const [testingGateway, setTestingGateway] = useState(false)
  const [gatewayTestResult, setGatewayTestResult] =
    useState<GatewayTestResponse | null>(null)

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

  return (
    <div className="space-y-6">
      <div className="border-b border-border pb-4">
        <h1 className="font-mono text-2xl font-bold text-ink">Integrations</h1>
        <p className="mt-0.5 text-sm text-ink-muted">
          Razorpay gateway connectivity, webhook ingress, and subsystem health.
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
            <div className="grid grid-cols-1 gap-4 font-mono text-xs md:grid-cols-2">
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
                    <Badge
                      variant="outline"
                      className="text-[10px] uppercase"
                    >
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

              <div className="space-y-1 rounded-control border border-border bg-surface-sunken p-3">
                <span className="block text-[11px] text-ink-muted">
                  Deployment Environment
                </span>
                <span className="font-bold text-ink uppercase">
                  {settings?.environment || 'Not configured'}
                </span>
              </div>

              <div className="space-y-1 rounded-control border border-border bg-surface-sunken p-3">
                <span className="block text-[11px] text-ink-muted">
                  Gateway Mode
                </span>
                <div className="flex items-center justify-between gap-2">
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
                    {settings?.razorpay_key_id ? 'derived from key' : 'no key'}
                  </Badge>
                </div>
              </div>

              <div className="space-y-1 rounded-control border border-border bg-surface-sunken p-3">
                <span className="block text-[11px] text-ink-muted">
                  Razorpay Key ID
                </span>
                <span className="font-semibold text-ink">
                  {settings?.razorpay_key_id
                    ? `${settings.razorpay_key_id.slice(0, 10)}...`
                    : 'Not configured'}
                </span>
              </div>

              <div className="space-y-1 rounded-control border border-border bg-surface-sunken p-3 md:col-span-2">
                <span className="block text-[11px] text-ink-muted">
                  Ingress Webhook Endpoint
                </span>
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-ink select-all">
                    {settings?.webhook_ingress_url || '/api/webhooks/razorpay'}
                  </span>
                  <Badge
                    variant={
                      settings?.webhook_secret_configured
                        ? 'recovered'
                        : 'outline'
                    }
                    className="text-[10px]"
                  >
                    {settings?.webhook_secret_configured
                      ? 'HMAC Verification Active'
                      : 'Unsigned (Simulated)'}
                  </Badge>
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
              className="cursor-pointer gap-2 font-mono text-xs"
            >
              <RazorpaySymbol className="h-3.5 w-3.5" />
              <span>
                {testingGateway
                  ? 'Testing Gateway...'
                  : 'Ping Gateway & Verify HMAC'}
              </span>
            </Button>
            {gatewayTestResult ? (
              <span className="flex items-center gap-1.5 font-mono text-xs text-recovered">
                <CheckCircle2 className="h-3.5 w-3.5" />
                {gatewayTestResult.message} (
                {gatewayTestResult.latency_ms.toFixed(0)}ms)
              </span>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <StatusView
        status={status}
        loading={loading}
        onRefresh={onRefresh}
        showPageHeader={false}
      />
    </div>
  )
}
