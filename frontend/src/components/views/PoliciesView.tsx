'use client'

import React from 'react'
import type { PolicyResponse } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { SkeletonCard } from '@/components/ui/skeleton'

interface PoliciesViewProps {
  policies: PolicyResponse | null
  loading: boolean
}

export function PoliciesView({ policies, loading }: PoliciesViewProps) {
  if (loading || !policies) {
    return <SkeletonCard />
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Merchant Recovery Policies & Guardrails</CardTitle>
          <CardDescription>
            Active deterministic boundaries enforced on all AI recovery interventions for merchant: {policies.merchant_id}
          </CardDescription>
        </CardHeader>
        <CardContent className="divide-y divide-border">
          {policies.rules.map((rule) => (
            <div key={rule.id} className="flex items-start justify-between py-4 first:pt-0 last:pb-0">
              <div className="space-y-1 pr-6">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-ink font-mono">{rule.name}</span>
                  <Badge variant={rule.enforced ? 'recovered' : 'default'}>
                    {rule.enforced ? 'Enforced' : 'Disabled'}
                  </Badge>
                </div>
                <p className="text-xs text-ink-muted">{rule.description}</p>
              </div>
              <div className="shrink-0 text-right">
                <span className="font-mono text-xs font-semibold text-ink bg-surface-sunken px-2.5 py-1 rounded-control border border-border">
                  {rule.value}
                </span>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}
