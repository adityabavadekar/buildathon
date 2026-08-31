'use client'

import React from 'react'
import { Award, Flame, ShieldCheck, Zap } from 'lucide-react'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

interface HealthScoreCardProps {
  healthScore: number
  returnOnSpend: number
  recoveryStreak: number
}

export function HealthScoreCard({
  healthScore,
  returnOnSpend,
  recoveryStreak,
}: HealthScoreCardProps) {
  return (
    <Card className="flex flex-col justify-between border-recovered/40 bg-recovered-subtle/10">
      <CardHeader className="p-5 pb-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 shrink-0 text-recovered" />
            <CardTitle className="font-mono text-base font-bold text-ink">
              Autonomous Health Index
            </CardTitle>
          </div>
          <span className="shrink-0 rounded-control bg-recovered px-3 py-1 font-mono text-sm font-bold text-white shadow-xs">
            {healthScore.toString()} / 100 Score
          </span>
        </div>
        <CardDescription className="mt-1 text-xs leading-normal text-ink-muted">
          Composite recovery velocity, policy compliance, and margin lift
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-3.5 p-5 pt-0">
        {/* Health Meter Box */}
        <div className="rounded-control border border-border bg-surface p-4">
          <div className="flex items-center justify-between font-mono">
            <div className="flex items-center gap-2">
              <div className="rounded-xs bg-accent/15 p-1.5 text-accent">
                <Zap className="h-4 w-4" />
              </div>
              <span className="text-xs font-semibold text-ink">
                Health Meter
              </span>
            </div>
            <span className="text-2xl font-bold text-recovered">
              {healthScore.toString()}%
            </span>
          </div>
          <div className="mt-2.5 h-2.5 w-full overflow-hidden rounded-full bg-surface-sunken">
            <div
              className="h-full bg-recovered transition-all duration-500"
              style={{ width: `${healthScore.toString()}%` }}
            />
          </div>
        </div>

        {/* Return on Spend Box */}
        <div className="rounded-control border border-border bg-surface p-4">
          <div className="flex items-center justify-between font-mono">
            <div className="flex items-center gap-2">
              <div className="rounded-xs bg-recovered/20 p-1.5 text-recovered">
                <Award className="h-4 w-4" />
              </div>
              <span className="text-xs font-semibold text-ink">
                Return on Spend
              </span>
            </div>
            <span className="text-2xl font-bold text-ink">
              {returnOnSpend.toFixed(1)}x
            </span>
          </div>
          <p className="mt-1.5 font-mono text-xs leading-tight text-ink-muted">
            Gross recovery yield per INR 1 dunning fee
          </p>
        </div>

        {/* Recovery Streak Box */}
        <div className="rounded-control border border-border bg-surface p-4">
          <div className="flex items-center justify-between font-mono">
            <div className="flex items-center gap-2">
              <div className="rounded-xs bg-amber-500/15 p-1.5 text-amber-500">
                <Flame className="h-4 w-4" />
              </div>
              <span className="text-xs font-semibold text-ink">
                Recovery Streak
              </span>
            </div>
            <span className="text-2xl font-bold text-amber-600">
              {recoveryStreak.toString()} in a row
            </span>
          </div>
          <p className="mt-1.5 font-mono text-xs leading-tight text-ink-muted">
            Consecutive successful autonomous resolutions
          </p>
        </div>
      </CardContent>
    </Card>
  )
}
