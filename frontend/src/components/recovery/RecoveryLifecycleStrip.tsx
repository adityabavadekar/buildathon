'use client'

import React from 'react'
import { AlertTriangle, BrainCircuit, CheckCircle2, Send } from 'lucide-react'
import type { RecoveryCase } from '@/lib/api'

interface RecoveryLifecycleStripProps {
  cases: RecoveryCase[]
  onStepClick?: (stepIndex: number) => void
}

function formatINR(paise: number): string {
  const rupees = paise / 100
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(rupees)
}

export function RecoveryLifecycleStrip({
  cases,
  onStepClick,
}: RecoveryLifecycleStripProps) {
  const ingestCount = cases.filter(
    (c) => c.state === 'FAILED' || c.state === 'ANALYSIS_QUEUED',
  ).length

  const activeInterventionCount = cases.filter(
    (c) =>
      c.state === 'IN_DUNNING' ||
      c.state === 'RETRY_SCHEDULED' ||
      c.state === 'OUTREACH_PENDING',
  ).length

  const recoveredCases = cases.filter((c) => c.state === 'RECOVERED')
  const recoveredCount = recoveredCases.length
  const totalNrvPaise = recoveredCases.reduce(
    (acc, c) => acc + (c.net_recovered_value_paise || 0),
    0,
  )

  const steps = [
    {
      stepNumber: '01',
      title: 'Ingest',
      subtitle: 'Webhook Failure Feed',
      description:
        'Raw payment.failed event received with error codes & rail telemetry.',
      icon: AlertTriangle,
      metric: `${ingestCount.toString()} Ingested`,
      accentColor: 'text-failed',
    },
    {
      stepNumber: '02',
      title: 'Diagnose',
      subtitle: 'Root Cause Taxonomy',
      description:
        'AI planner & deterministic rules classify failure into 1 of 6 bounded categories.',
      icon: BrainCircuit,
      metric: 'LLM + NPCI Rules',
      accentColor: 'text-accent',
    },
    {
      stepNumber: '03',
      title: 'Intervene',
      subtitle: 'Policy Gate & Execution',
      description:
        'Touch limits & margin checked, then smart link, debit retry, or WhatsApp sent.',
      icon: Send,
      metric: `${activeInterventionCount.toString()} Active`,
      accentColor: 'text-pending',
    },
    {
      stepNumber: '04',
      title: 'Recover',
      subtitle: 'Counterfactual Proof',
      description:
        'Payment captured on gateway; recovery measured against 10% uncontacted holdout arm.',
      icon: CheckCircle2,
      metric: `${recoveredCount.toString()} Won (${formatINR(totalNrvPaise)})`,
      accentColor: 'text-recovered',
    },
  ]

  return (
    <div className="space-y-3 rounded-panel border border-border bg-surface-sunken/40 p-4">
      <div className="flex flex-col justify-between gap-1 border-b border-border/40 pb-2 sm:flex-row sm:items-center">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs font-bold tracking-wider text-ink uppercase">
            Autonomous Recovery Pipeline
          </span>
          <span className="hidden text-[11px] text-ink-muted md:inline">
            How failed transactions progress through diagnosis, policy
            guardrails, and resolution
          </span>
        </div>
        <span className="font-mono text-[10px] text-ink-subtle uppercase">
          10% Holdout Arm Enforced
        </span>
      </div>

      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
        {steps.map((step, idx) => {
          const Icon = step.icon
          return (
            <div
              key={step.title}
              onClick={() => onStepClick?.(idx)}
              className="group flex cursor-pointer flex-col justify-between space-y-2 rounded-control border border-border/80 bg-surface p-3 transition-colors hover:border-accent/60"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[11px] font-bold text-ink-subtle group-hover:text-accent">
                    {step.stepNumber}
                  </span>
                  <span className="font-mono text-xs font-semibold text-ink">
                    {step.title}
                  </span>
                </div>
                <Icon className={`h-4 w-4 ${step.accentColor} shrink-0`} />
              </div>

              <p className="text-[11px] leading-tight text-ink-muted">
                {step.description}
              </p>

              <div className="flex items-center justify-between border-t border-border/40 pt-1.5 font-mono text-[10px]">
                <span className="text-ink-subtle">{step.subtitle}</span>
                <span className="font-semibold text-ink">{step.metric}</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
