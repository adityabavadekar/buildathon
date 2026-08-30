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
    <Card className="border-recovered/40 bg-recovered-subtle/10 flex flex-col justify-between">
      <CardHeader className="p-5 pb-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-recovered shrink-0" />
            <CardTitle className="text-base font-mono font-bold text-ink">
              Autonomous Health Index
            </CardTitle>
          </div>
          <span className="rounded-control bg-recovered text-white px-3 py-1 text-sm font-mono font-bold shrink-0 shadow-xs">
            {healthScore.toString()} / 100 Score
          </span>
        </div>
        <CardDescription className="text-xs text-ink-muted mt-1 leading-normal">
          Composite recovery velocity, policy compliance, and margin lift
        </CardDescription>
      </CardHeader>

      <CardContent className="p-5 pt-0 space-y-3.5">
        {/* Health Meter Box */}
        <div className="p-4 rounded-control bg-surface border border-border">
          <div className="flex items-center justify-between font-mono">
            <div className="flex items-center gap-2">
              <div className="p-1.5 rounded-xs bg-accent/15 text-accent">
                <Zap className="h-4 w-4" />
              </div>
              <span className="text-xs font-semibold text-ink">Health Meter</span>
            </div>
            <span className="text-2xl font-bold text-recovered">
              {healthScore.toString()}%
            </span>
          </div>
          <div className="h-2.5 w-full rounded-full bg-surface-sunken overflow-hidden mt-2.5">
            <div
              className="h-full bg-recovered transition-all duration-500"
              style={{ width: `${healthScore.toString()}%` }}
            />
          </div>
        </div>

        {/* Return on Spend Box */}
        <div className="p-4 rounded-control bg-surface border border-border">
          <div className="flex items-center justify-between font-mono">
            <div className="flex items-center gap-2">
              <div className="p-1.5 rounded-xs bg-recovered/20 text-recovered">
                <Award className="h-4 w-4" />
              </div>
              <span className="text-xs font-semibold text-ink">Return on Spend</span>
            </div>
            <span className="text-2xl font-bold text-ink">
              {returnOnSpend.toFixed(1)}x
            </span>
          </div>
          <p className="text-xs text-ink-muted font-mono mt-1.5 leading-tight">
            Gross recovery yield per INR 1 dunning fee
          </p>
        </div>

        {/* Recovery Streak Box */}
        <div className="p-4 rounded-control bg-surface border border-border">
          <div className="flex items-center justify-between font-mono">
            <div className="flex items-center gap-2">
              <div className="p-1.5 rounded-xs bg-amber-500/15 text-amber-500">
                <Flame className="h-4 w-4" />
              </div>
              <span className="text-xs font-semibold text-ink">Recovery Streak</span>
            </div>
            <span className="text-2xl font-bold text-amber-600">
              {recoveryStreak.toString()} in a row
            </span>
          </div>
          <p className="text-xs text-ink-muted font-mono mt-1.5 leading-tight">
            Consecutive successful autonomous resolutions
          </p>
        </div>
      </CardContent>
    </Card>
  )
}
