'use client'

import React, { useState } from 'react'
import {
  DollarSign,
  MessageSquare,
  ShieldCheck,
  X,
} from 'lucide-react'
import {
  approveCase,
  resolveCaseSim,
  type RecoveryCase,
  type RecoveryState,
} from '@/lib/api'
import { Badge, type BadgeVariant } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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

  if (!caseItem) return null

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
              <Badge variant="outline">{caseItem.experiment_arm}</Badge>
            </div>
            <span className="text-[11px] font-mono text-ink-muted mt-1 block">
              Payment ID: {caseItem.failure_event.payment_id} | Created: {new Date(caseItem.created_at).toLocaleString()}
            </span>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="rounded-control p-1 text-ink-muted hover:text-ink hover:bg-border/40 transition-colors cursor-pointer"
            title="Close Drawer [Esc]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-border bg-surface px-5">
          {(
            [
              { id: 'overview', label: 'Financials & Diagnosis' },
              { id: 'outreach', label: 'WhatsApp Outreach' },
              { id: 'audit', label: `Audit Trail (${caseItem.audit_trail.length.toString()})` },
              { id: 'actions', label: 'Operator Actions' },
            ] as const
          ).map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => {
                setActiveTab(tab.id)
              }}
              className={`border-b-2 px-4 py-2.5 text-xs font-mono font-medium transition-colors cursor-pointer ${
                activeTab === tab.id
                  ? 'border-accent text-accent font-semibold'
                  : 'border-transparent text-ink-muted hover:text-ink'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Content Area */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {activeTab === 'overview' && (
            <>
              {/* Financial Ledger */}
              <div className="space-y-2">
                <div className="flex items-center gap-1.5 text-xs font-mono font-semibold uppercase tracking-wider text-ink-muted">
                  <DollarSign className="h-3.5 w-3.5 text-accent" />
                  <span>Unit Economics Ledger</span>
                </div>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 font-mono">
                  <div className="p-3 rounded-control bg-surface-sunken border border-border">
                    <span className="text-[10px] text-ink-muted block uppercase">Amount at Risk</span>
                    <span className="text-sm font-bold text-ink mt-0.5 block">
                      {formatINR(caseItem.amount_paise)}
                    </span>
                  </div>
                  <div className="p-3 rounded-control bg-surface-sunken border border-border">
                    <span className="text-[10px] text-ink-muted block uppercase">Recovered</span>
                    <span className="text-sm font-bold text-recovered mt-0.5 block">
                      {formatINR(caseItem.recovered_amount_paise)}
                    </span>
                  </div>
                  <div className="p-3 rounded-control bg-surface-sunken border border-border">
                    <span className="text-[10px] text-ink-muted block uppercase">Total Cost</span>
                    <span className="text-sm font-bold text-failed mt-0.5 block">
                      -{formatINR(caseItem.total_cost_paise)}
                    </span>
                  </div>
                  <div className="p-3 rounded-control bg-surface-sunken border border-recovered/40">
                    <span className="text-[10px] text-recovered block uppercase">Net Value (NRV)</span>
                    <span className="text-sm font-bold text-recovered mt-0.5 block">
                      {formatINR(caseItem.net_recovered_value_paise)}
                    </span>
                  </div>
                </div>
              </div>

              {/* Failure Event Context */}
              <div className="space-y-2">
                <span className="text-xs font-mono font-semibold uppercase tracking-wider text-ink-muted">
                  Failure Telemetry & Ingestion
                </span>
                <div className="p-4 rounded-panel bg-surface-sunken/60 border border-border space-y-2 font-mono text-xs">
                  <div className="flex justify-between">
                    <span className="text-ink-muted">Payment Rail:</span>
                    <span className="text-ink font-semibold uppercase">{caseItem.failure_event.payment_rail}</span>
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
                <div className="flex items-center gap-1.5 text-xs font-mono font-semibold uppercase tracking-wider text-ink-muted">
                  <ShieldCheck className="h-3.5 w-3.5 text-recovered" />
                  <span>Policy Guardrail Status</span>
                </div>
                <div className="grid grid-cols-2 gap-3 font-mono text-xs">
                  <div className="p-3 rounded-control bg-surface-sunken border border-border flex justify-between items-center">
                    <span className="text-ink-muted">Touches Count</span>
                    <span className="font-semibold text-ink">{caseItem.touches_count.toString()} / 3 Max</span>
                  </div>
                  <div className="p-3 rounded-control bg-surface-sunken border border-border flex justify-between items-center">
                    <span className="text-ink-muted">Discount Granted</span>
                    <span className="font-semibold text-ink">{formatINR(caseItem.discount_paise_granted)}</span>
                  </div>
                </div>
              </div>
            </>
          )}

          {activeTab === 'outreach' && (
            <div className="space-y-4">
              <div className="flex items-center gap-1.5 text-xs font-mono font-semibold uppercase tracking-wider text-ink-muted">
                <MessageSquare className="h-3.5 w-3.5 text-accent" />
                <span>Live Customer Outreach Preview</span>
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
                      Cost: -{formatINR(entry.cost_incurred_paise)}
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
              <span className="text-xs font-mono font-semibold uppercase tracking-wider text-ink-muted">
                Manual Operator Overrides
              </span>

              {caseItem.state === 'ESCALATED' && (
                <div className="p-4 rounded-panel bg-escalated-subtle/20 border border-escalated/40 space-y-3">
                  <span className="text-xs font-semibold text-escalated font-mono block">
                    Action Required: High-Value / Policy Escalation
                  </span>
                  <p className="text-xs text-ink">
                    This transaction was paused by the safety gate. Review the diagnosis and approve execution to resume recovery.
                  </p>
                  <Button
                    variant="primary"
                    disabled={actionLoading}
                    onClick={() => {
                      void handleApprove()
                    }}
                  >
                    {actionLoading ? 'Approving...' : 'Approve Intervention'}
                  </Button>
                </div>
              )}

              {caseItem.state !== 'RECOVERED' && (
                <div className="p-4 rounded-panel bg-surface-sunken border border-border space-y-3">
                  <span className="text-xs font-semibold text-ink font-mono block">
                    Simulate Payment Captured Webhook
                  </span>
                  <p className="text-xs text-ink-muted">
                    Simulate the customer completing checkout or mandate capture via Razorpay webhook.
                  </p>
                  <Button
                    variant="secondary"
                    disabled={actionLoading}
                    onClick={() => {
                      void handleSimulatePayment()
                    }}
                  >
                    {actionLoading ? 'Simulating...' : 'Mark as Recovered'}
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
