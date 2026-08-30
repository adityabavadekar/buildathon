'use client'

import React from 'react'
import type { SystemSettingsResponse } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { SkeletonCard } from '@/components/ui/skeleton'

interface SettingsViewProps {
  settings: SystemSettingsResponse | null
  loading: boolean
}

export function SettingsView({ settings, loading }: SettingsViewProps) {
  if (loading || !settings) {
    return <SkeletonCard />
  }

  return (
    <div className="space-y-6">
      {/* Integration & Gateway Settings */}
      <Card>
        <CardHeader>
          <CardTitle>Razorpay Webhook Endpoint</CardTitle>
          <CardDescription>
            Configure this target URL inside your Razorpay Merchant Dashboard under Webhooks
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
                {settings.webhook_secret_configured ? 'Active' : 'Unset (Dev Mode)'}
              </Badge>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* LLM & Model Engine Configuration */}
      <Card>
        <CardHeader>
          <CardTitle>AI Reasoning Engine</CardTitle>
          <CardDescription>
            Active LLM provider and fallback taxonomy status
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 font-mono text-xs">
          <div className="flex items-center justify-between p-3 rounded-control bg-surface-sunken border border-border">
            <div>
              <span className="font-semibold text-ink block">
                Primary Provider: {settings.primary_llm_provider.toUpperCase()}
              </span>
              <span className="text-[11px] text-ink-muted block mt-0.5">
                Model: {settings.active_llm_model}
              </span>
            </div>
            <Badge variant={settings.configured_llm_providers.length > 0 ? 'recovered' : 'pending'}>
              {settings.configured_llm_providers.length > 0
                ? `Connected (${settings.configured_llm_providers.join(', ')})`
                : 'Offline / Rule Fallback'}
            </Badge>
          </div>

          <div className="flex items-center justify-between p-3 rounded-control bg-surface-sunken border border-border">
            <div>
              <span className="font-semibold text-ink block">Deterministic Fallback Layer</span>
              <span className="text-[11px] text-ink-muted block mt-0.5">
                NPCI & Razorpay Taxonomy Classifier
              </span>
            </div>
            <Badge variant={settings.deterministic_fallback_active ? 'recovered' : 'default'}>
              {settings.deterministic_fallback_active ? '100% Operational' : 'Disabled'}
            </Badge>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
