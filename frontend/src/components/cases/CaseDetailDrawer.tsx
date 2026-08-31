'use client'

import React, { useEffect, useState } from 'react'
import {
  DollarSign,
  MessageSquare,
  ShieldCheck,
  X,
} from 'lucide-react'
import {
  approveCase,
  getPolicies,
  resolveCaseSim,
  type PolicyResponse,
  type RecoveryCase,
  type RecoveryState,
} from '@/lib/api'
import { Badge, type BadgeVariant } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { GlossaryTerm } from '@/components/ui/GlossaryTerm'
import { STATE_READINGS } from '@/lib/glossary'
import { RailBadge } from '@/components/ui/BrandIcons'
import { WhatsAppPreview } from '@/components/whatsapp/WhatsAppPreview'

interface CaseDetailDrawerProps {
  caseItem: RecoveryCase | null
  onClose: () => void
  onActionComplete: () => void
}

function formatINR(paise: number): string {
  const rupees = paise / 100
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(rupees)
}

function stateToVariant(state: RecoveryState): BadgeVariant {
  switch (state) {
    case 'RECOVERED':
      return 'recovered'
    case 'ESCALATED':
      return 'escalated'
    case 'FAILED':
      return 'failed'
    case 'OUTREACH_PENDING':
    case 'RETRY_SCHEDULED':
    case 'IN_DUNNING':
    case 'ANALYSIS_QUEUED':
      return 'pending'
    default:
      return 'default'
  }
}

export function CaseDetailDrawer({
  caseItem,
  onClose,
  onActionComplete,
}: CaseDetailDrawerProps) {
  const [actionLoading, setActionLoading] = useState<boolean>(false)
  const [activeTab, setActiveTab] = useState<'overview' | 'outreach' | 'audit' | 'actions'>('overview')
  const [policy, setPolicy] = useState<PolicyResponse | null>(null)

  useEffect(() => {
    getPolicies()
      .then((p) => {
        setPolicy(p)
      })
      .catch(() => null)
  }, [])

  if (!caseItem) return null

  const maxTouches = policy?.max_touches ?? 3
  const stateDescription = STATE_READINGS[caseItem.state] || caseItem.state

  const handleApprove = async () => {
    try {
      setActionLoading(true)
      await approveCase(caseItem.case_id, 'Approved via Operator Drawer')
      onActionComplete()
    } finally {
      setActionLoading(false)
    }
  }

  const handleSimulatePayment = async () => {
    try {
      setActionLoading(true)
      await resolveCaseSim(caseItem.case_id)
      onActionComplete()
      onClose()
    } finally {
      setActionLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-xs">
      <div className="flex h-full w-full max-w-2xl flex-col bg-surface border-l border-border shadow-2xl animate-in slide-in-from-right duration-200">
        {/* Drawer Header */}
        <div className="flex items-center justify-between border-b border-border p-5 bg-surface-sunken/40">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="font-mono text-sm font-bold text-ink">{caseItem.case_id}</span>
              <Badge variant={stateToVariant(caseItem.state)}>
                {caseItem.state.replace('_', ' ')}
              </Badge>
              <Badge variant="outline">
                {caseItem.experiment_arm === 'HOLDOUT_CONTROL' ? 'Holdout (10%)' : 'Treatment'}
              </Badge>
            </div>
            <span className="text-[11px] font-mono text-ink-muted mt-1 block">
              Payment ID: {caseItem.failure_event.payment_id} | Created: {new Date(caseItem.created_at).toLocaleString()}
            </span>
          </div>
          <button
            onClick={onClose}
            className="rounded-control p-1.5 text-ink-muted hover:bg-surface hover:text-ink transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* State Explanation Banner */}
        <div className="px-5 py-2.5 bg-surface-sunken border-b border-border text-xs flex items-center justify-between">
          <span className="text-ink font-medium">{stateDescription}</span>
          <span className="text-[10px] font-mono text-ink-subtle uppercase">Lifecycle State</span>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-border px-5 gap-6 font-mono text-xs">
          {(['overview', 'outreach', 'audit', 'actions'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => {
                setActiveTab(tab)
              }}
              className={`py-3 border-b-2 font-medium capitalize transition-colors ${
                activeTab === tab
                  ? 'border-accent text-accent'
                  : 'border-transparent text-ink-muted hover:text-ink'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Drawer Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6">
          {activeTab === 'overview' && (
            <>
              {/* Financial Breakdown */}
              <div className="grid grid-cols-2 gap-4">
                <div className="p-4 rounded-panel bg-surface-sunken border border-border space-y-1">
                  <span className="text-[11px] font-mono text-ink-muted flex items-center justify-between">
                    <GlossaryTerm termKey="AT_RISK_REVENUE" showIcon={false}>
                      At-Risk Amount
                    </GlossaryTerm>
                  </span>
                  <div className="text-lg font-mono font-bold text-ink">
                    {formatINR(caseItem.amount_paise)}
                  </div>
                  <p className="text-[11px] text-ink-subtle leading-relaxed">
                    The money behind the failed payment. This is what was at stake.
                  </p>
                </div>

                <div className="p-4 rounded-panel bg-surface-sunken border border-border space-y-1">
                  <span className="text-[11px] font-mono text-ink-muted flex items-center justify-between">
                    <GlossaryTerm termKey="RECOVERED_NRV" showIcon={false}>
                      Net Recovered Value (NRV)
                    </GlossaryTerm>
                  </span>
                  <div className="text-lg font-mono font-bold text-recovered">
                    {caseItem.state === 'RECOVERED'
                      ? formatINR(caseItem.net_recovered_value_paise || caseItem.recovered_amount_paise)
                      : '--'}
                  </div>
                  <p className="text-[11px] text-ink-subtle leading-relaxed">
                    {caseItem.state === 'RECOVERED'
                      ? 'Money actually recovered, minus the cost of retries, messages, and any discount given. This is the real win.'
                      : 'Will show here once this payment is recovered.'}
                  </p>
                </div>
              </div>

              {/* Ingestion & Telemetry */}
              <div className="space-y-2">
                <div className="space-y-0.5">
                  <span className="text-xs font-mono font-semibold uppercase tracking-wider text-ink-muted">
                    Failure Telemetry & Ingestion
                  </span>
                  <p className="text-[11px] text-ink-subtle leading-relaxed">
                    The raw details of the failed payment that started this case: which payment method failed, the error the bank or gateway returned, and who the customer is.
                  </p>
                </div>
                <div className="p-4 rounded-panel bg-surface-sunken/60 border border-border space-y-2 font-mono text-xs">
                  <div className="flex justify-between items-center">
                    <span className="text-ink-muted">Payment Rail:</span>
                    <RailBadge rail={caseItem.failure_event.payment_rail} />
                  </div>
                  <div className="flex justify-between">
                    <span className="text-ink-muted">Error Category:</span>
                    <span className="text-ink font-semibold">{caseItem.failure_event.category || 'TRANSIENT'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-ink-muted">Error Code / Reason:</span>
                    <span className="text-ink">{caseItem.failure_event.error_code} - {caseItem.failure_event.error_reason}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-ink-muted">Customer ID:</span>
                    <span className="text-ink">{caseItem.failure_event.customer_id}</span>
                  </div>
                </div>
              </div>

              {/* Guardrails & Touch Status */}
              <div className="space-y-2">
                <div className="space-y-0.5">
                  <div className="flex items-center gap-1.5 text-xs font-mono font-semibold uppercase tracking-wider text-ink-muted">
                    <ShieldCheck className="h-3.5 w-3.5 text-recovered" />
                    <span>
                      <GlossaryTerm termKey="POLICY_GATE" showIcon={false}>
                        Policy Guardrail Status
                      </GlossaryTerm>
                    </span>
                  </div>
                  <p className="text-[11px] text-ink-subtle leading-relaxed">
                    The safety limits applied to this case: how many attempts are still allowed, and whether a discount has been granted to get the payment through.
                  </p>
                </div>
                <div className="grid grid-cols-2 gap-3 font-mono text-xs">
                  <div className="p-3 rounded-control bg-surface-sunken border border-border flex justify-between items-center">
                    <span className="text-ink-muted">
                      <GlossaryTerm termKey="TOUCHES" showIcon={false}>
                        Touches Count
                      </GlossaryTerm>
                    </span>
                    <span className="font-semibold text-ink">
                      {caseItem.touches_count.toString()} / {maxTouches.toString()} Max
                    </span>
                  </div>
                  <div className="p-3 rounded-control bg-surface-sunken border border-border flex justify-between items-center">
                    <span className="text-ink-muted">
                      <GlossaryTerm termKey="DISCOUNT_GRANTED" showIcon={false}>
                        Discount Granted
                      </GlossaryTerm>
                    </span>
                    <span className="font-semibold text-ink">{formatINR(caseItem.discount_paise_granted)}</span>
                  </div>
                </div>
              </div>
            </>
          )}

          {activeTab === 'outreach' && (
            <div className="space-y-4">
              <div className="space-y-0.5">
                <div className="flex items-center gap-1.5 text-xs font-mono font-semibold uppercase tracking-wider text-ink-muted">
                  <MessageSquare className="h-3.5 w-3.5 text-accent" />
                  <span>Live Customer Outreach Preview</span>
                </div>
                <p className="text-[11px] text-ink-subtle leading-relaxed">
                  A preview of the WhatsApp message the customer would receive if the engine reached out about this failed payment. It shows the message text, the payment link, and any discount offered.
                </p>
              </div>
              <WhatsAppPreview caseItem={caseItem} />
            </div>
          )}

          {activeTab === 'audit' && (
            <div className="space-y-4">
              <span className="text-xs font-mono font-semibold uppercase tracking-wider text-ink-muted">
                Immutable State Machine Chronology
              </span>
              {caseItem.audit_trail.map((entry) => (
                <div
                  key={entry.entry_id}
                  className="relative pl-5 border-l-2 border-border pb-4 last:pb-0"
                >
                  <div className="absolute -left-[5px] top-1 h-2 w-2 rounded-full bg-accent" />
                  <div className="flex items-center justify-between text-xs text-ink-muted font-mono">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-ink">{entry.event_name}</span>
                      <Badge variant="outline">{entry.actor}</Badge>
                    </div>
                    <span>{new Date(entry.timestamp).toLocaleTimeString()}</span>
                  </div>
                  <p className="mt-1.5 text-xs text-ink">{entry.reason}</p>
                  {entry.cost_incurred_paise > 0 && (
                    <span className="text-[10px] font-mono text-failed mt-0.5 block">
                      Cost Incurred: -{formatINR(entry.cost_incurred_paise)}
                    </span>
                  )}
                  {Object.keys(entry.decision_inputs).length > 0 && (
                    <pre className="mt-2 p-2 rounded-control bg-surface-sunken border border-border/60 text-[10px] font-mono text-ink-muted overflow-x-auto">
                      {JSON.stringify(entry.decision_inputs, null, 2)}
                    </pre>
                  )}
                </div>
              ))}
            </div>
          )}

          {activeTab === 'actions' && (
            <div className="space-y-4">
              <div className="p-4 rounded-panel bg-surface-sunken border border-border space-y-2">
                <span className="text-xs font-mono font-bold text-ink">Operator Actions</span>
                <p className="text-xs text-ink-muted">
                  Approve an escalated case or simulate a customer payment completion against the Razorpay webhook pipeline.
                </p>
                <div className="pt-2 flex flex-wrap gap-2">
                  {caseItem.state === 'ESCALATED' && (
                    <Button
                      size="sm"
                      onClick={() => {
                        void handleApprove()
                      }}
                      disabled={actionLoading}
                      className="font-mono text-xs"
                    >
                      {actionLoading ? 'Approving...' : 'Approve Case'}
                    </Button>
                  )}
                  {caseItem.state !== 'RECOVERED' && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        void handleSimulatePayment()
                      }}
                      disabled={actionLoading}
                      className="font-mono text-xs flex items-center gap-1.5"
                    >
                      <DollarSign className="h-3.5 w-3.5 text-recovered" />
                      {actionLoading ? 'Processing...' : 'Simulate Customer Payment'}
                    </Button>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
