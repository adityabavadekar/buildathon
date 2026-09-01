'use client'

import React, { useState } from 'react'
import {
  Code2,
  Filter,
  Layers,
  Sparkles,
  Tag,
} from 'lucide-react'
import type { CampaignMetrics } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { formatINR } from '@/lib/format'

interface CampaignAttributionChartProps {
  campaigns?: CampaignMetrics[]
}

type SortKey = 'at_risk_paise' | 'recovered_paise' | 'recovery_rate_pct' | 'net_recovered_value_paise'

export function CampaignAttributionChart({
  campaigns = [],
}: CampaignAttributionChartProps) {
  const [sortBy, setSortBy] = useState<SortKey>('at_risk_paise')
  const [sortAsc, setSortAsc] = useState<boolean>(false)
  const [showMetadataGuide, setShowMetadataGuide] = useState<boolean>(false)
  const [filterQuery, setFilterQuery] = useState<string>('')

  const filteredCampaigns = campaigns.filter((c) =>
    c.campaign_id.toLowerCase().includes(filterQuery.toLowerCase()),
  )

  const sortedCampaigns = [...filteredCampaigns].sort((a, b) => {
    const valA = a[sortBy]
    const valB = b[sortBy]
    return sortAsc ? valA - valB : valB - valA
  })

  const totalAtRisk = campaigns.reduce((acc, c) => acc + c.at_risk_paise, 0)
  const totalRecovered = campaigns.reduce((acc, c) => acc + c.recovered_paise, 0)
  const totalNRV = campaigns.reduce((acc, c) => acc + c.net_recovered_value_paise, 0)

  const handleSort = (key: SortKey) => {
    if (sortBy === key) {
      setSortAsc(!sortAsc)
    } else {
      setSortBy(key)
      setSortAsc(false)
    }
  }

  return (
    <Card className="col-span-full">
      <CardHeader className="flex flex-col gap-3 border-b border-border/40 pb-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Tag className="h-4 w-4 text-accent" />
            <CardTitle className="text-base">
              Campaign attribution and recovery
            </CardTitle>
            <Badge variant="outline" className="font-mono text-xs">
              Razorpay notes
            </Badge>
          </div>
          <CardDescription className="mt-1">
            Recovery yield, net recovered value, and conversion rate grouped by
            custom campaign identifiers.
          </CardDescription>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setShowMetadataGuide(!showMetadataGuide)
            }}
            className="h-8 gap-1 text-xs"
          >
            <Code2 className="h-3.5 w-3.5" />
            {showMetadataGuide ? 'Hide notes guide' : 'Setup tracking guide'}
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-4 pt-4">
        {/* Razorpay Notes Taxonomy Guide Accordion */}
        {showMetadataGuide && (
          <div className="rounded-control border border-accent/30 bg-accent-subtle/10 p-4 text-xs">
            <div className="flex items-center gap-2 font-medium text-accent">
              <Sparkles className="h-4 w-4" />
              <span>Razorpay Metadata (notes) Attribution Specification</span>
            </div>
            <p className="mt-1 text-ink-muted leading-relaxed">
              Razorpay does not have a native campaign entity. FORTX extracts custom cohort tags
              directly from the <code className="font-mono text-ink">notes</code> dictionary in Orders, Payments, and Subscriptions payloads (max 15 keys, 256 chars each).
            </p>

            <div className="mt-3 rounded border border-border bg-surface-sunken p-3 font-mono text-xs">
              <p className="text-ink-muted">// Example: Razorpay Order creation payload</p>
              <p className="text-ink">
                {`client.order.create({
  "amount": 149900,
  "currency": "INR",
  "notes": {
    "recovery_campaign": "dunning_wave_1",
    "subscription_id": "sub_premium_992",
    "dunning_stage": "stage_2",
    "retry_attempt": "1",
    "user_ref": "usr_9981"
  }
})`}
              </p>
            </div>
          </div>
        )}

        {/* Aggregate Summary Pills */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-control border border-border bg-surface-sunken p-3">
            <p className="text-xs text-ink-muted">Active campaigns</p>
            <p className="text-lg font-bold text-ink">{campaigns.length}</p>
          </div>
          <div className="rounded-control border border-border bg-surface-sunken p-3">
            <p className="text-xs text-ink-muted">Total at risk</p>
            <p className="text-lg font-bold money text-ink">{formatINR(totalAtRisk)}</p>
          </div>
          <div className="rounded-control border border-recovered/30 bg-recovered-subtle/20 p-3">
            <p className="text-xs text-recovered">Total captured</p>
            <p className="text-lg font-bold money text-recovered">{formatINR(totalRecovered)}</p>
          </div>
          <div className="rounded-control border border-accent/30 bg-accent-subtle/20 p-3">
            <p className="text-xs text-accent">Net recovered yield</p>
            <p className="text-lg font-bold money text-accent">{formatINR(totalNRV)}</p>
          </div>
        </div>

        {/* Filter & Sort Controls */}
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-t border-border/40 pt-3">
          <div className="relative flex-1 max-w-xs">
            <Filter className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-ink-muted" />
            <input
              type="text"
              placeholder="Filter campaign ID..."
              value={filterQuery}
              onChange={(e) => {
                setFilterQuery(e.target.value)
              }}
              className="h-8 w-full rounded-control border border-border bg-surface-sunken pl-8 pr-3 text-xs text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none"
            />
          </div>

          <div className="flex flex-wrap items-center gap-1.5 text-xs text-ink-muted">
            <span>Sort by:</span>
            <button
              type="button"
              onClick={() => {
                handleSort('at_risk_paise')
              }}
              className={`rounded px-2 py-1 transition-colors ${
                sortBy === 'at_risk_paise'
                  ? 'bg-surface text-ink font-medium border border-border'
                  : 'hover:text-ink'
              }`}
            >
              At Risk {sortBy === 'at_risk_paise' && (sortAsc ? '^' : 'v')}
            </button>
            <button
              type="button"
              onClick={() => {
                handleSort('recovered_paise')
              }}
              className={`rounded px-2 py-1 transition-colors ${
                sortBy === 'recovered_paise'
                  ? 'bg-surface text-ink font-medium border border-border'
                  : 'hover:text-ink'
              }`}
            >
              Recovered {sortBy === 'recovered_paise' && (sortAsc ? '^' : 'v')}
            </button>
            <button
              type="button"
              onClick={() => {
                handleSort('recovery_rate_pct')
              }}
              className={`rounded px-2 py-1 transition-colors ${
                sortBy === 'recovery_rate_pct'
                  ? 'bg-surface text-ink font-medium border border-border'
                  : 'hover:text-ink'
              }`}
            >
              Rate % {sortBy === 'recovery_rate_pct' && (sortAsc ? '^' : 'v')}
            </button>
            <button
              type="button"
              onClick={() => {
                handleSort('net_recovered_value_paise')
              }}
              className={`rounded px-2 py-1 transition-colors ${
                sortBy === 'net_recovered_value_paise'
                  ? 'bg-surface text-ink font-medium border border-border'
                  : 'hover:text-ink'
              }`}
            >
              NRV {sortBy === 'net_recovered_value_paise' && (sortAsc ? '^' : 'v')}
            </button>
          </div>
        </div>

        {/* Campaign Breakdown List */}
        {sortedCampaigns.length === 0 ? (
          <div className="py-8 text-center text-xs text-ink-muted">
            No campaigns found matching filter.
          </div>
        ) : (
          <div className="space-y-2.5">
            {sortedCampaigns.map((c) => {
              const recoveryPct = c.recovery_rate_pct
              const recoveredWidth = (c.recovered_paise / Math.max(1, c.at_risk_paise)) * 100

              return (
                <div
                  key={c.campaign_id}
                  className="space-y-2 rounded-control border border-border bg-surface-sunken/40 p-3 text-xs transition-colors hover:bg-surface-sunken/80"
                >
                  <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex items-center gap-2">
                      <Layers className="h-3.5 w-3.5 text-accent shrink-0" />
                      <span className="font-semibold text-ink font-mono">
                        {c.campaign_id}
                      </span>
                      <Badge variant="outline" className="text-[10px]">
                        {c.total_cases} cases
                      </Badge>
                      {c.escalated_cases > 0 && (
                        <Badge variant="failed" className="text-[10px]">
                          {c.escalated_cases} escalated
                        </Badge>
                      )}
                    </div>

                    <div className="flex items-center gap-4 text-right">
                      <div>
                        <span className="text-ink-muted">At risk: </span>
                        <span className="font-semibold money text-ink">
                          {formatINR(c.at_risk_paise)}
                        </span>
                      </div>
                      <div>
                        <span className="text-ink-muted">Recovered: </span>
                        <span className="font-semibold money text-recovered">
                          {formatINR(c.recovered_paise)}
                        </span>
                      </div>
                      <div>
                        <span className="text-ink-muted">NRV: </span>
                        <span className="font-bold money text-accent">
                          {formatINR(c.net_recovered_value_paise)}
                        </span>
                      </div>
                      <Badge
                        variant={recoveryPct >= 50 ? 'recovered' : 'default'}
                        className="font-mono text-xs"
                      >
                        {recoveryPct.toFixed(1)}%
                      </Badge>
                    </div>
                  </div>

                  {/* Proportional Volume & Recovery Bar */}
                  <div className="space-y-1">
                    <div className="h-2 w-full overflow-hidden rounded bg-surface border border-border/50">
                      <div
                        className="h-full bg-recovered transition-all duration-300"
                        style={{ width: `${Math.min(100, recoveredWidth).toFixed(1)}%` }}
                      />
                    </div>
                    <div className="flex justify-between text-[11px] text-ink-muted">
                      <span>{c.recovered_cases} recovered / {c.total_cases} failures</span>
                      <span>Mean ticket: {formatINR(c.avg_amount_paise)}</span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
