'use client'

import React from 'react'
import { AlertCircle } from 'lucide-react'
import type { CategoryBreakdown } from '@/lib/api'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

interface CategoryDistributionChartProps {
  categories: CategoryBreakdown[]
}

const CATEGORY_COLORS: Record<string, string> = {
  INSUFFICIENT_FUNDS: 'bg-accent',
  TECHNICAL_ERROR: 'bg-failed',
  USER_DROP: 'bg-amber-500',
  AUTHENTICATION_FAILED: 'bg-purple-500',
  LIMIT_EXCEEDED: 'bg-rose-500',
  POLICY_VIOLATION: 'bg-escalated',
  UNKNOWN: 'bg-ink-muted',
}

export function CategoryDistributionChart({
  categories,
}: CategoryDistributionChartProps) {
  const totalDiagnosed = categories.reduce((acc, c) => acc + c.count, 0)

  return (
    <Card>
      <CardHeader className="pb-3 border-b border-border/40">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-accent" />
            <CardTitle className="text-base font-mono">
              Root Cause Failure Diagnosis
            </CardTitle>
          </div>
          <span className="text-xs font-mono text-ink-muted">
            {totalDiagnosed.toString()} Classified Events
          </span>
        </div>
        <CardDescription className="text-xs mt-0.5">
          Semantic root cause classification across payment rails and gateway error signatures.
        </CardDescription>
      </CardHeader>

      <CardContent className="pt-4 space-y-4">
        {categories.length === 0 ? (
          <div className="py-10 text-center text-xs font-mono text-ink-muted">
            No diagnosed failure categories available.
          </div>
        ) : (
          <div className="space-y-3.5">
            {/* Horizontal Distribution Bar */}
            <div className="flex h-3 w-full rounded-full bg-surface-sunken overflow-hidden gap-0.5">
              {categories.map((cat) => {
                const color = CATEGORY_COLORS[cat.category] || 'bg-accent'
                const pct = Math.max(cat.percentage, 2)
                return (
                  <div
                    key={cat.category}
                    className={`${color} transition-all duration-300`}
                    style={{ width: `${pct.toString()}%` }}
                    title={`${cat.category}: ${cat.percentage.toFixed(1)}% (${cat.count.toString()} cases)`}
                  />
                )
              })}
            </div>

            {/* List breakdown */}
            <div className="space-y-2 font-mono text-xs">
              {categories.map((cat) => {
                const color = CATEGORY_COLORS[cat.category] || 'bg-accent'
                return (
                  <div
                    key={cat.category}
                    className="flex items-center justify-between p-2 rounded-control bg-surface-sunken/60 border border-border/60"
                  >
                    <div className="flex items-center gap-2.5">
                      <span className={`h-2.5 w-2.5 rounded-full ${color} shrink-0`} />
                      <span className="font-semibold text-ink">
                        {cat.category.replace(/_/g, ' ')}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-ink-muted">{cat.count.toString()} cases</span>
                      <span className="font-bold text-ink w-12 text-right">
                        {cat.percentage.toFixed(1)}%
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
