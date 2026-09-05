'use client'

import React, { useId, useState } from 'react'
import {
  ChevronDown,
  ChevronRight,
  Filter,
  Layers,
  Sparkles,
  Tag,
} from 'lucide-react'
import type { CampaignMetrics } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
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

type SortKey =
  | 'at_risk_paise'
  | 'recovered_paise'
  | 'recovery_rate_pct'
  | 'net_recovered_value_paise'

const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: 'net_recovered_value_paise', label: 'NRV' },
  { key: 'at_risk_paise', label: 'At Risk' },
  { key: 'recovered_paise', label: 'Recovered' },
  { key: 'recovery_rate_pct', label: 'Rate %' },
]

// Bars encode net recovered value, the metric this section is attributed by.
// A campaign can have negative NRV (cost of recovery exceeded what it
// captured), so the scale must accommodate a negative extent, not just 0..max.
function barExtent(campaigns: CampaignMetrics[]): {
  min: number
  max: number
} {
  if (campaigns.length === 0) {
    return { min: 0, max: 1 }
  }
  const values = campaigns.map((c) => c.net_recovered_value_paise)
  const max = Math.max(0, ...values)
  const min = Math.min(0, ...values)
  return { min, max: max === min ? min + 1 : max }
}

export function CampaignAttributionChart({
  campaigns = [],
}: CampaignAttributionChartProps) {
  const [sortBy, setSortBy] = useState<SortKey>('net_recovered_value_paise')
  const [sortAsc, setSortAsc] = useState<boolean>(false)
  const [guideExpanded, setGuideExpanded] = useState<boolean>(false)
  const [filterQuery, setFilterQuery] = useState<string>('')
  const titleId = useId()

  const filteredCampaigns = campaigns.filter((c) =>
    c.campaign_id.toLowerCase().includes(filterQuery.toLowerCase()),
  )

  const sortedCampaigns = [...filteredCampaigns].sort((a, b) => {
    const valA = a[sortBy]
    const valB = b[sortBy]
    return sortAsc ? valA - valB : valB - valA
  })

  const totalAtRisk = campaigns.reduce((acc, c) => acc + c.at_risk_paise, 0)
  const totalRecovered = campaigns.reduce(
    (acc, c) => acc + c.recovered_paise,
    0,
  )
  const totalNRV = campaigns.reduce(
    (acc, c) => acc + c.net_recovered_value_paise,
    0,
  )

  const { min: extentMin, max: extentMax } = barExtent(sortedCampaigns)
  const extentSpan = extentMax - extentMin
  const zeroPct = extentSpan > 0 ? ((0 - extentMin) / extentSpan) * 100 : 0

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
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Tag className="h-4 w-4 text-accent" />
          <CardTitle className="text-base">
            Campaign attribution and recovery
          </CardTitle>
          <Badge variant="outline" className="text-xs">
            Razorpay notes
          </Badge>
        </div>
        <CardDescription className="mt-1">
          Net recovered value by campaign, extracted from Razorpay notes
          metadata.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-3 pt-2">
        {/* Aggregate summary pills */}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div className="rounded-control border border-border bg-surface-sunken p-2.5">
            <p className="text-xs text-ink-muted">Active campaigns</p>
            <p className="text-base font-bold text-ink">{campaigns.length}</p>
          </div>
          <div className="rounded-control border border-border bg-surface-sunken p-2.5">
            <p className="text-xs text-ink-muted">Total at risk</p>
            <p className="money text-left text-base font-bold text-ink">
              {formatINR(totalAtRisk)}
            </p>
          </div>
          <div className="rounded-control border border-recovered/30 bg-recovered-subtle/20 p-2.5">
            <p className="text-xs text-recovered">Total captured</p>
            <p className="money text-left text-base font-bold text-recovered">
              {formatINR(totalRecovered)}
            </p>
          </div>
          <div className="rounded-control border border-accent/30 bg-accent-subtle/20 p-2.5">
            <p className="text-xs text-accent">Net recovered yield</p>
            <p className="money text-left text-base font-bold text-accent">
              {formatINR(totalNRV)}
            </p>
          </div>
        </div>

        {/* Filter & sort controls, one row */}
        <div className="flex flex-col gap-2 border-t border-border/40 pt-2.5 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative max-w-xs flex-1">
            <Filter className="absolute top-2 left-2.5 h-3.5 w-3.5 text-ink-muted" />
            <input
              type="text"
              placeholder="Filter campaign ID..."
              value={filterQuery}
              onChange={(e) => {
                setFilterQuery(e.target.value)
              }}
              className="h-7 w-full rounded-control border border-border bg-surface-sunken pr-3 pl-8 text-xs text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none"
            />
          </div>

          <div className="flex flex-wrap items-center gap-1.5 text-xs text-ink-muted">
            <span>Sort:</span>
            {SORT_OPTIONS.map((opt) => (
              <button
                key={opt.key}
                type="button"
                onClick={() => {
                  handleSort(opt.key)
                }}
                className={`rounded px-1.5 py-0.5 transition-colors ${
                  sortBy === opt.key
                    ? 'border border-border bg-surface font-medium text-ink'
                    : 'hover:text-ink'
                }`}
              >
                {opt.label} {sortBy === opt.key && (sortAsc ? '^' : 'v')}
              </button>
            ))}
          </div>
        </div>

        {/* Horizontal bar chart: net recovered value per campaign */}
        {sortedCampaigns.length === 0 ? (
          <div className="py-6 text-center text-xs text-ink-muted">
            No campaigns found matching filter.
          </div>
        ) : (
          <svg
            viewBox={`0 0 100 ${(sortedCampaigns.length * 22).toString()}`}
            preserveAspectRatio="none"
            className="w-full"
            style={{ height: `${(sortedCampaigns.length * 22).toString()}px` }}
            role="img"
            aria-labelledby={titleId}
          >
            <title id={titleId}>Net recovered value by campaign, in INR</title>
            {extentMin < 0 ? (
              <line
                x1={zeroPct}
                x2={zeroPct}
                y1={0}
                y2={sortedCampaigns.length * 22}
                stroke="var(--color-border-strong)"
                strokeWidth={0.4}
              />
            ) : null}
            {sortedCampaigns.map((c, idx) => {
              const y = idx * 22 + 3
              const nrv = c.net_recovered_value_paise
              const positive = nrv >= 0
              const barStart =
                extentSpan > 0
                  ? ((Math.min(0, nrv) - extentMin) / extentSpan) * 100
                  : 0
              const barWidth =
                extentSpan > 0 ? (Math.abs(nrv) / extentSpan) * 100 : 0
              return (
                <rect
                  key={c.campaign_id}
                  x={barStart}
                  y={y}
                  width={Math.max(0, barWidth)}
                  height={14}
                  rx={2}
                  fill={
                    positive ? 'var(--color-recovered)' : 'var(--color-failed)'
                  }
                />
              )
            })}
          </svg>
        )}

        {/* Compact per-campaign rows, one line each */}
        <div className="space-y-1">
          {sortedCampaigns.map((c) => (
            <div
              key={c.campaign_id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-control border border-border bg-surface-sunken/40 px-2.5 py-1.5 text-xs transition-colors hover:bg-surface-sunken/80"
            >
              <div className="flex min-w-0 items-center gap-1.5">
                <Layers className="h-3 w-3 shrink-0 text-accent" />
                <span className="truncate font-semibold text-ink">
                  {c.campaign_id}
                </span>
                <Badge variant="outline" className="text-[10px]">
                  {c.total_cases}
                </Badge>
                {c.escalated_cases > 0 && (
                  <Badge variant="failed" className="text-[10px]">
                    {c.escalated_cases} esc
                  </Badge>
                )}
              </div>

              <div className="flex items-center gap-3 text-right whitespace-nowrap">
                <span className="text-ink-muted">
                  At risk{' '}
                  <span className="money font-medium text-ink">
                    {formatINR(c.at_risk_paise)}
                  </span>
                </span>
                <span className="text-ink-muted">
                  Recovered{' '}
                  <span className="money font-medium text-recovered">
                    {formatINR(c.recovered_paise)}
                  </span>
                </span>
                <span className="text-ink-muted">
                  NRV{' '}
                  <span className="money font-bold text-accent">
                    {formatINR(c.net_recovered_value_paise)}
                  </span>
                </span>
                <Badge
                  variant={c.recovery_rate_pct >= 50 ? 'recovered' : 'default'}
                  className="text-[10px]"
                >
                  {c.recovery_rate_pct.toFixed(1)}%
                </Badge>
              </div>
            </div>
          ))}
        </div>

        {/* Razorpay notes taxonomy guide - collapsed by default, click header
            to expand. Matches OAuthConnectPanel's collapse convention. */}
        <div className="rounded-control border border-border/60">
          <button
            type="button"
            onClick={() => {
              setGuideExpanded((prev) => !prev)
            }}
            className="flex w-full cursor-pointer items-center justify-between gap-2 px-3 py-2 text-left text-xs font-medium text-ink-muted hover:text-ink"
          >
            <span className="flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
              Setup tracking guide
            </span>
            {guideExpanded ? (
              <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
            )}
          </button>

          {guideExpanded && (
            <div className="border-t border-border/60 px-3 pt-2 pb-3 text-xs">
              <p className="leading-relaxed text-ink-muted">
                Razorpay does not have a native campaign entity. FORTX extracts
                custom cohort tags directly from the{' '}
                <code className="text-ink">notes</code> dictionary in Orders,
                Payments, and Subscriptions payloads (max 15 keys, 256 chars
                each).
              </p>

              <div className="mt-2 rounded border border-border bg-surface-sunken p-3 text-xs">
                <p className="text-ink-muted">
                  // Example: Razorpay Order creation payload
                </p>
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
        </div>
      </CardContent>
    </Card>
  )
}
