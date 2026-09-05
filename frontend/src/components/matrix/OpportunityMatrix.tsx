'use client'

import React, { useState } from 'react'
import type { RecoveryCase } from '@/lib/api'
import { formatCustomerName } from '@/lib/format'
import { RailBadge } from '@/components/ui/BrandIcons'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

interface OpportunityMatrixProps {
  cases: RecoveryCase[]
  onSelectCase: (c: RecoveryCase) => void
}

function formatINR(paise: number): string {
  const rupees = paise / 100
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(rupees)
}

function getRecoveryProbability(c: RecoveryCase): number {
  const reason = (c.failure_event.error_reason || '').toLowerCase()
  const code = (c.failure_event.error_code || '').toLowerCase()
  const rail = c.failure_event.payment_rail

  if (c.state === 'RECOVERED') return 100
  if (c.state === 'ESCALATED') return 35
  if (reason.includes('cutoff') || code.includes('xt') || code.includes('u30'))
    return 78
  if (reason.includes('otp') || code.includes('drop')) return 52
  if (code.includes('ap15') || reason.includes('balance')) return 45
  if (rail === 'ENACH' || code.includes('ap09')) return 22
  return 40
}

export function OpportunityMatrix({
  cases,
  onSelectCase,
}: OpportunityMatrixProps) {
  const [hoveredCase, setHoveredCase] = useState<RecoveryCase | null>(null)

  // Filter non-terminal or sample of 40 cases for clear visual representation
  const activeCases = cases.slice(0, 40)
  const maxAmount = Math.max(...activeCases.map((c) => c.amount_paise), 1000000)

  return (
    <Card className="relative overflow-hidden">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <div>
          <CardTitle>Recovery Opportunity Matrix</CardTitle>
          <CardDescription>
            Interactive 2x2 map: Revenue at risk vs autonomous recovery
            probability
          </CardDescription>
        </div>
        <div className="flex items-center gap-3 text-[11px] text-ink-muted">
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-recovered" /> Recovered
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-accent" /> Active AI
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-escalated" /> Escalated
          </span>
        </div>
      </CardHeader>

      <CardContent className="p-6 pt-2">
        <div className="relative h-80 w-full overflow-hidden rounded-panel border border-border bg-surface-sunken/40">
          {/* 4 Quadrants Labels */}
          <div className="pointer-events-none absolute inset-0 grid grid-cols-2 grid-rows-2 divide-x divide-y divide-border/60">
            {/* Top-Left: Quick Wins */}
            <div className="bg-recovered-subtle/5 p-3">
              <span className="block text-[10px] font-bold tracking-wider text-recovered uppercase">
                Quick Wins
              </span>
              <span className="block text-[9px] text-ink-subtle">
                High Probability · Low Value (Automated Retries)
              </span>
            </div>

            {/* Top-Right: High Value */}
            <div className="bg-accent-subtle/5 p-3">
              <span className="block text-[10px] font-bold tracking-wider text-accent uppercase">
                High Value Priority
              </span>
              <span className="block text-[9px] text-ink-subtle">
                High Probability · High Value (Smart Links)
              </span>
            </div>

            {/* Bottom-Left: Low Priority */}
            <div className="p-3">
              <span className="block text-[10px] font-bold tracking-wider text-ink-subtle uppercase">
                Low Priority
              </span>
              <span className="block text-[9px] text-ink-subtle">
                Low Probability · Low Value (Standard Nudges)
              </span>
            </div>

            {/* Bottom-Right: Human Review */}
            <div className="bg-escalated-subtle/5 p-3">
              <span className="block text-[10px] font-bold tracking-wider text-escalated uppercase">
                Human Review
              </span>
              <span className="block text-[9px] text-ink-subtle">
                Low Probability · High Value (Operator Escalation)
              </span>
            </div>
          </div>

          {/* Plotted Case Bubbles */}
          {activeCases.length === 0 ? (
            <div className="flex h-full items-center justify-center text-xs text-ink-muted">
              No active recovery cases to map.
            </div>
          ) : (
            activeCases.map((c) => {
              const prob = getRecoveryProbability(c)
              // X: 5% to 92% based on log scale of amount
              const xPos = Math.min(
                92,
                Math.max(
                  8,
                  (Math.log10(c.amount_paise) /
                    Math.log10(maxAmount || 1000000)) *
                    88,
                ),
              )
              // Y: 8% to 88% based on probability (higher prob = higher up on chart)
              const yPos = 92 - Math.min(84, Math.max(10, (prob / 100) * 80))

              let dotColor = 'bg-accent border-accent/60'
              if (c.state === 'RECOVERED')
                dotColor = 'bg-recovered border-recovered/60'
              if (c.state === 'ESCALATED')
                dotColor = 'bg-escalated border-escalated/60'

              return (
                <button
                  key={c.case_id}
                  type="button"
                  onClick={() => {
                    onSelectCase(c)
                  }}
                  onMouseEnter={() => {
                    setHoveredCase(c)
                  }}
                  onMouseLeave={() => {
                    setHoveredCase(null)
                  }}
                  style={{
                    left: `${xPos.toString()}%`,
                    top: `${yPos.toString()}%`,
                  }}
                  className={`absolute h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 cursor-pointer rounded-full border shadow-xs transition-all duration-150 hover:scale-150 ${dotColor}`}
                  title={`${c.case_id} (${formatINR(c.amount_paise)})`}
                />
              )
            })
          )}

          {/* Floating Tooltip when hovering over a case */}
          {hoveredCase && (
            <div className="animate-in fade-in pointer-events-none absolute bottom-3 left-3 z-20 max-w-xs rounded-panel border border-border bg-surface p-3 text-xs shadow-xl duration-150">
              <div className="flex items-center justify-between gap-4">
                <span className="font-bold text-ink">
                  {hoveredCase.case_id}
                </span>
                <span className="font-semibold text-recovered">
                  {getRecoveryProbability(hoveredCase).toString()}% Probability
                </span>
              </div>
              <div className="mt-1 flex items-center justify-between gap-2 text-[11px] text-ink-muted">
                <span>
                  {formatCustomerName(hoveredCase.failure_event.customer_id)}
                </span>
                <RailBadge rail={hoveredCase.failure_event.payment_rail} />
              </div>
              <div className="mt-1 font-semibold text-ink">
                Amount: {formatINR(hoveredCase.amount_paise)}
              </div>
              <div className="mt-0.5 truncate text-[10px] text-ink-subtle">
                {hoveredCase.failure_event.error_reason ||
                  hoveredCase.failure_event.error_code}
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
