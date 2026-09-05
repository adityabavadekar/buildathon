'use client'

import React from 'react'
import { Award, ShieldCheck } from 'lucide-react'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

interface HealthScoreCardProps {
  healthScore: number
  healthScoreAvailable: boolean
  returnOnSpend: number
}

export function HealthScoreCard({
  healthScore,
  healthScoreAvailable,
  returnOnSpend,
}: HealthScoreCardProps) {
  return (
    <Card className="flex flex-col justify-between border-recovered/40 bg-recovered-subtle/10">
      <CardHeader className="p-5 pb-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 shrink-0 text-recovered" />
            <CardTitle className="text-base font-bold text-ink">
              Autonomous Health Index
            </CardTitle>
          </div>
          <span className="shrink-0 rounded-control bg-recovered px-3 py-1 text-sm font-bold text-white shadow-xs">
            {healthScoreAvailable
              ? `${healthScore.toString()} / 100 Score`
              : 'No data yet'}
          </span>
        </div>
        <CardDescription className="mt-1 text-xs leading-normal text-ink-muted">
          Composite recovery velocity, policy compliance, and margin lift
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-3.5 p-5 pt-0">
        {!healthScoreAvailable && (
          <p className="text-xs leading-tight text-ink-muted">
            No treatment cases have resolved yet.
          </p>
        )}

        {/* Return on Spend Box */}
        <div className="rounded-control border border-border bg-surface p-4">
          <div className="flex items-center justify-between">
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
          <p className="mt-1.5 text-xs leading-tight text-ink-muted">
            Gross recovery yield per INR 1 dunning fee
          </p>
        </div>
      </CardContent>
    </Card>
  )
}
