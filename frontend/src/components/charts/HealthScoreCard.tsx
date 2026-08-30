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
    <Card className="border-recovered/40 bg-recovered-subtle/10">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-recovered" />
            <CardTitle>Autonomous Recovery Health</CardTitle>
          </div>
          <span className="rounded-control bg-recovered text-white px-2.5 py-0.5 text-xs font-mono font-bold">
            {healthScore.toString()} / 100 Score
          </span>
        </div>
        <CardDescription>
          Composite health index measuring recovery velocity, policy compliance, and lift
        </CardDescription>
      </CardHeader>
      <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-3 pt-2">
        <div className="p-3.5 rounded-control bg-surface border border-border">
          <div className="flex items-center gap-1.5 text-xs text-ink-muted font-mono">
            <Zap className="h-3.5 w-3.5 text-accent" />
            <span>Health Meter</span>
          </div>
          <span className="text-2xl font-bold font-mono text-recovered mt-1 block">
            {healthScore.toString()}%
          </span>
          <div className="h-2 w-full rounded-full bg-surface-sunken overflow-hidden mt-2">
            <div
              className="h-full bg-recovered transition-all duration-500"
              style={{ width: `${healthScore.toString()}%` }}
            />
          </div>
        </div>

        <div className="p-3.5 rounded-control bg-surface border border-border">
          <div className="flex items-center gap-1.5 text-xs text-ink-muted font-mono">
            <Award className="h-3.5 w-3.5 text-recovered" />
            <span>Return on Recovery Spend</span>
          </div>
          <span className="text-2xl font-bold font-mono text-ink mt-1 block">
            {returnOnSpend.toFixed(1)}x
          </span>
          <span className="text-[11px] text-ink-subtle mt-0.5 block font-mono">
            Gross recovery yield per INR 1 dunning fee
          </span>
        </div>

        <div className="p-3.5 rounded-control bg-surface border border-border">
          <div className="flex items-center gap-1.5 text-xs text-ink-muted font-mono">
            <Flame className="h-3.5 w-3.5 text-amber-500" />
            <span>Recovery Streak</span>
          </div>
          <span className="text-2xl font-bold font-mono text-amber-600 mt-1 block">
            {recoveryStreak.toString()} in a row
          </span>
          <span className="text-[11px] text-ink-subtle mt-0.5 block font-mono">
            Consecutive successful resolutions
          </span>
        </div>
      </CardContent>
    </Card>
  )
}
