'use client'

import React, { useEffect, useState } from 'react'
import {
  Brain,
  DollarSign,
  MessageSquare,
  ShieldCheck,
  Sparkles,
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
import { formatCustomerName, formatINR } from '@/lib/format'
import { RailBadge } from '@/components/ui/BrandIcons'
import { WhatsAppPreview } from '@/components/whatsapp/WhatsAppPreview'

interface CaseDetailDrawerProps {
  caseItem: RecoveryCase | null
  onClose: () => void
  onActionComplete: () => void
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

const TAB_LABELS = {
  overview: 'Overview',
  outreach: 'Outreach',
  audit: 'Audit trail',
  actions: 'Actions',
} as const

export function CaseDetailDrawer({
  caseItem,
  onClose,
  onActionComplete,
}: CaseDetailDrawerProps) {
  const [actionLoading, setActionLoading] = useState<boolean>(false)
  const [activeTab, setActiveTab] =
    useState<keyof typeof TAB_LABELS>('overview')
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
  const recoveredValue =
    caseItem.state === 'RECOVERED'
      ? caseItem.net_recovered_value_paise || caseItem.recovered_amount_paise
      : null

  const handleApprove = async () => {
    try {
      setActionLoading(true)
      await approveCase(caseItem.case_id, 'Approved via operator drawer')
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
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/50"
      onClick={onClose}
    >
      <div
        className="flex h-full w-full max-w-3xl flex-col border-l border-border bg-surface"
        onClick={(e) => {
          e.stopPropagation()
        }}
      >
        <div className="border-b border-border bg-surface-sunken/50 px-5 py-4">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="truncate text-lg font-semibold text-ink">
                  {caseItem.case_id}
                </h2>
                <Badge variant={stateToVariant(caseItem.state)}>
                  {caseItem.state.replaceAll('_', ' ')}
                </Badge>
                <Badge variant="outline">
                  {caseItem.experiment_arm === 'HOLDOUT_CONTROL'
                    ? 'Holdout'
                    : 'Treatment'}
                </Badge>
              </div>
              <p className="mt-1 text-sm text-ink-muted">
                Payment {caseItem.failure_event.payment_id} · Customer{' '}
                {formatCustomerName(caseItem.failure_event.customer_id)}
              </p>
              <p className="mt-1 text-xs text-ink-subtle">{stateDescription}</p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="cursor-pointer rounded-control p-1.5 text-ink-muted transition-colors hover:bg-surface hover:text-ink"
              aria-label="Close transaction details"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <div className="metric-tile">
              <p className="metric-tile-label">At risk</p>
              <p className="metric-tile-value money">
                {formatINR(caseItem.amount_paise, { maximumFractionDigits: 2 })}
              </p>
            </div>
            <div className="metric-tile border-recovered/30 bg-recovered-subtle/30">
              <p className="metric-tile-label text-recovered">Recovered NRV</p>
              <p className="metric-tile-value money text-recovered">
                {recoveredValue !== null
                  ? formatINR(recoveredValue, { maximumFractionDigits: 2 })
                  : '--'}
              </p>
            </div>
            <div className="metric-tile">
              <p className="metric-tile-label">Touches used</p>
              <p className="metric-tile-value">
                {caseItem.touches_count.toString()} / {maxTouches.toString()}
              </p>
            </div>
            <div className="metric-tile">
              <p className="metric-tile-label">Discount granted</p>
              <p className="metric-tile-value money">
                {formatINR(caseItem.discount_paise_granted, {
                  maximumFractionDigits: 2,
                })}
              </p>
            </div>
          </div>
        </div>

        <div className="flex gap-5 border-b border-border px-5">
          {(Object.keys(TAB_LABELS) as Array<keyof typeof TAB_LABELS>).map(
            (tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => {
                  setActiveTab(tab)
                }}
                className={`drawer-tab ${activeTab === tab ? 'drawer-tab--active' : ''}`}
              >
                {TAB_LABELS[tab]}
              </button>
            ),
          )}
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          {activeTab === 'overview' && (
            <>
              {/* AI Agent Reasoning & Decision Card */}
              {(() => {
                const planEntry = caseItem.audit_trail.find(
                  (a) =>
                    a.event_name === 'agent.plan_formulated' ||
                    a.event_name === 'agent.message_drafted' ||
                    a.actor.toLowerCase().includes('agent'),
                )
                const meta = planEntry?.model_metadata
                const planObj =
                  planEntry &&
                  typeof planEntry.decision_outputs.plan === 'object' &&
                  planEntry.decision_outputs.plan !== null
                    ? (planEntry.decision_outputs.plan as Record<
                        string,
                        unknown
                      >)
                    : null
                const rationale =
                  (typeof planObj?.rationale === 'string'
                    ? planObj.rationale
                    : null) ||
                  planEntry?.notes ||
                  caseItem.failure_event.error_description ||
                  null
                const strategy =
                  (typeof planObj?.intervention_type === 'string'
                    ? planObj.intervention_type
                    : null) ||
                  caseItem.next_action ||
                  'DYNAMIC_INTERVENTION'

                const msgEn =
                  caseItem.dunning_message_en ||
                  (planEntry &&
                  typeof planEntry.decision_outputs.dunning_message_en ===
                    'string'
                    ? planEntry.decision_outputs.dunning_message_en
                    : null)
                const msgHi =
                  caseItem.dunning_message_hi ||
                  (planEntry &&
                  typeof planEntry.decision_outputs.dunning_message_hi ===
                    'string'
                    ? planEntry.decision_outputs.dunning_message_hi
                    : null)

                return (
                  <section className="space-y-3 rounded-panel border border-accent/30 bg-accent/5 p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className="flex h-6 w-6 items-center justify-center rounded-control bg-accent/20 text-accent">
                          <Brain className="h-3.5 w-3.5" />
                        </div>
                        <h3 className="text-sm font-bold text-ink">
                          AI Agent Diagnostic Reasoning
                        </h3>
                      </div>
                      <Badge
                        variant="default"
                        className="border-accent/30 bg-accent/10 font-mono text-[10px] text-accent"
                      >
                        {strategy.replaceAll('_', ' ')}
                      </Badge>
                    </div>

                    {rationale ? (
                      <div className="rounded-control border border-border/80 bg-surface p-3 text-xs leading-relaxed text-ink shadow-2xs">
                        <p className="mb-1 font-mono text-[10px] font-semibold tracking-wider text-ink-muted uppercase">
                          Diagnostic Rationale & Strategy
                        </p>
                        <p className="font-medium text-ink">{rationale}</p>
                      </div>
                    ) : null}

                    {/* Model Metadata Bar */}
                    <div className="flex flex-wrap items-center gap-2 font-mono text-[11px] text-ink-muted">
                      <span className="inline-flex items-center gap-1 rounded-control border border-border bg-surface px-2 py-1">
                        <Sparkles className="h-3 w-3 text-accent" />
                        <span>
                          Model: {meta?.model || 'deterministic-rules-v1'}
                        </span>
                      </span>
                      {typeof meta?.latency_ms === 'number' && (
                        <span className="inline-flex items-center gap-1 rounded-control border border-border bg-surface px-2 py-1">
                          <span>Latency: {meta.latency_ms.toFixed(1)}ms</span>
                        </span>
                      )}
                      {typeof meta?.cost_usd === 'number' &&
                        meta.cost_usd > 0 && (
                          <span className="inline-flex items-center gap-1 rounded-control border border-border bg-surface px-2 py-1">
                            <span>Cost: ${meta.cost_usd.toFixed(5)}</span>
                          </span>
                        )}
                      {typeof meta?.input_tokens === 'number' &&
                        meta.input_tokens > 0 && (
                          <span className="inline-flex items-center gap-1 rounded-control border border-border bg-surface px-2 py-1">
                            <span>
                              Tokens:{' '}
                              {meta.input_tokens + (meta.output_tokens ?? 0)}
                            </span>
                          </span>
                        )}
                    </div>

                    {/* Drafted Messages Preview if present */}
                    {(msgEn || msgHi) && (
                      <div className="mt-2 space-y-2 border-t border-border/40 pt-2">
                        <p className="font-mono text-[10px] font-bold tracking-wider text-ink-subtle uppercase">
                          Drafted Recovery Outreach
                        </p>
                        {msgEn && (
                          <div className="rounded-control border border-border bg-surface p-2.5 text-xs text-ink">
                            <span className="mb-0.5 block font-mono text-[9px] font-bold text-accent uppercase">
                              English Draft
                            </span>
                            <span>{msgEn}</span>
                          </div>
                        )}
                        {msgHi && (
                          <div className="rounded-control border border-border bg-surface p-2.5 text-xs text-ink">
                            <span className="mb-0.5 block font-mono text-[9px] font-bold text-accent uppercase">
                              Hinglish Draft
                            </span>
                            <span>{msgHi}</span>
                          </div>
                        )}
                      </div>
                    )}
                  </section>
                )
              })()}

              <section className="space-y-3">
                <h3 className="text-sm font-semibold text-ink">
                  Failure details
                </h3>
                <div className="grid gap-3 rounded-panel border border-border bg-surface-sunken/40 p-4 text-sm">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-ink-muted">Payment rail</span>
                    <RailBadge rail={caseItem.failure_event.payment_rail} />
                  </div>
                  <div className="flex justify-between gap-3">
                    <span className="text-ink-muted">Failure category</span>
                    <span className="font-medium text-ink">
                      {caseItem.failure_event.category || 'TRANSIENT'}
                    </span>
                  </div>
                  <div className="flex justify-between gap-3">
                    <span className="text-ink-muted">Error</span>
                    <span className="text-right text-ink">
                      <span className="font-mono font-medium">
                        {caseItem.failure_event.error_code}
                      </span>
                      {' · '}
                      {caseItem.failure_event.error_reason}
                    </span>
                  </div>
                  <div className="flex justify-between gap-3">
                    <span className="text-ink-muted">Created</span>
                    <span className="font-medium text-ink">
                      {new Date(caseItem.created_at).toLocaleString()}
                    </span>
                  </div>
                </div>
              </section>

              <section className="space-y-3">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4 text-recovered" />
                  <h3 className="text-sm font-semibold text-ink">
                    <GlossaryTerm termKey="POLICY_GATE" showIcon={false}>
                      Policy guardrails
                    </GlossaryTerm>
                  </h3>
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="metric-tile">
                    <p className="metric-tile-label">
                      <GlossaryTerm termKey="TOUCHES" showIcon={false}>
                        Touch limit
                      </GlossaryTerm>
                    </p>
                    <p className="metric-tile-value">
                      {caseItem.touches_count.toString()} of{' '}
                      {maxTouches.toString()}
                    </p>
                    <p className="metric-tile-hint">
                      Remaining attempts before escalation or stop.
                    </p>
                  </div>
                  <div className="metric-tile">
                    <p className="metric-tile-label">
                      <GlossaryTerm termKey="DISCOUNT_GRANTED" showIcon={false}>
                        Discount used
                      </GlossaryTerm>
                    </p>
                    <p className="metric-tile-value money">
                      {formatINR(caseItem.discount_paise_granted, {
                        maximumFractionDigits: 2,
                      })}
                    </p>
                    <p className="metric-tile-hint">
                      Concession already applied on this case.
                    </p>
                  </div>
                </div>
              </section>
            </>
          )}

          {activeTab === 'outreach' && (
            <section className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <MessageSquare className="h-4 w-4 text-accent" />
                  <h3 className="text-sm font-semibold text-ink">
                    Customer outreach preview
                  </h3>
                </div>
                {caseItem.dunning_message_en && (
                  <Badge
                    variant="default"
                    className="border-accent/30 bg-accent/10 font-mono text-[10px] text-accent"
                  >
                    AI Personalized
                  </Badge>
                )}
              </div>
              <p className="text-sm text-ink-muted">
                Personalized message drafted for this customer grounded in
                failure details, including single-use payment link and applied
                concessions.
              </p>
              <WhatsAppPreview caseItem={caseItem} />

              {(caseItem.dunning_message_en || caseItem.dunning_message_hi) && (
                <div className="space-y-3 rounded-panel border border-border bg-surface-sunken/40 p-4">
                  <h4 className="font-mono text-xs font-bold tracking-wider text-ink uppercase">
                    Drafted Outreach Copy
                  </h4>
                  {caseItem.dunning_message_en && (
                    <div className="space-y-1">
                      <span className="font-mono text-[10px] font-semibold text-ink-muted">
                        English Copy
                      </span>
                      <div className="rounded-control border border-border bg-surface p-3 font-mono text-xs text-ink">
                        {caseItem.dunning_message_en}
                      </div>
                    </div>
                  )}
                  {caseItem.dunning_message_hi && (
                    <div className="space-y-1">
                      <span className="font-mono text-[10px] font-semibold text-ink-muted">
                        Hinglish Copy
                      </span>
                      <div className="rounded-control border border-border bg-surface p-3 font-mono text-xs text-ink">
                        {caseItem.dunning_message_hi}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </section>
          )}

          {activeTab === 'audit' && (
            <section className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-ink">
                  Immutable state machine chronology
                </h3>
                <span className="font-mono text-xs text-ink-muted">
                  {caseItem.audit_trail.length} audit checkpoints
                </span>
              </div>
              {caseItem.audit_trail.map((entry) => {
                const isAgent =
                  entry.actor.toLowerCase().includes('agent') ||
                  entry.event_name.startsWith('agent.') ||
                  Boolean(entry.model_metadata)
                const planObj =
                  typeof entry.decision_outputs.plan === 'object' &&
                  entry.decision_outputs.plan !== null
                    ? (entry.decision_outputs.plan as Record<string, unknown>)
                    : null
                const rationale =
                  typeof planObj?.rationale === 'string'
                    ? planObj.rationale
                    : null
                const msgEn =
                  typeof entry.decision_outputs.dunning_message_en === 'string'
                    ? entry.decision_outputs.dunning_message_en
                    : null
                const msgHi =
                  typeof entry.decision_outputs.dunning_message_hi === 'string'
                    ? entry.decision_outputs.dunning_message_hi
                    : null
                const decisionConfidence =
                  typeof entry.decision_inputs.confidence === 'string'
                    ? entry.decision_inputs.confidence
                    : null
                const decisionThreshold =
                  typeof entry.decision_inputs.confidence_threshold === 'string'
                    ? entry.decision_inputs.confidence_threshold
                    : null
                return (
                  <div
                    key={entry.entry_id}
                    className="relative border-l-2 border-border pb-4 pl-5 last:pb-0"
                  >
                    <div
                      className={`absolute top-1 -left-[5px] h-2 w-2 rounded-full ${
                        isAgent
                          ? 'bg-accent ring-2 ring-accent/30'
                          : entry.event_name.includes('policy')
                            ? 'bg-recovered'
                            : 'bg-border'
                      }`}
                    />
                    <div className="flex items-center justify-between text-xs text-ink-muted">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-ink">
                          {entry.event_name.replaceAll('_', ' ')}
                        </span>
                        <Badge
                          variant={isAgent ? 'default' : 'outline'}
                          className={`font-mono text-[10px] ${
                            isAgent
                              ? 'border-accent/30 bg-accent/10 text-accent'
                              : ''
                          }`}
                        >
                          {entry.actor}
                        </Badge>
                      </div>
                      <span className="font-mono text-[10px]">
                        {new Date(entry.timestamp).toLocaleString()}
                      </span>
                    </div>

                    {/* Agent Diagnostic Reasoning Callout */}
                    {rationale && (
                      <div className="mt-2 rounded-control border border-accent/30 bg-accent/5 p-2.5 text-xs text-ink">
                        <div className="mb-1 flex items-center gap-1.5 font-mono text-[10px] font-bold text-accent">
                          <Brain className="h-3 w-3" />
                          <span>Agent Strategy Rationale</span>
                        </div>
                        <p className="font-medium text-ink">{rationale}</p>
                      </div>
                    )}

                    {/* Decision Confidence Callout */}
                    {(decisionConfidence || decisionThreshold) && (
                      <div className="mt-2 flex flex-wrap items-center gap-2 rounded-control border border-border/80 bg-surface-sunken/60 p-2 font-mono text-[11px] text-ink-muted">
                        <span className="text-[10px] font-bold tracking-wider text-ink-muted uppercase">
                          Model confidence
                        </span>
                        {decisionConfidence && (
                          <span className="rounded border border-border/80 bg-surface-sunken px-1.5 py-0.5 text-ink">
                            {decisionConfidence}
                          </span>
                        )}
                        <span className="text-border">/</span>
                        {decisionThreshold && (
                          <span>
                            threshold{' '}
                            <span className="font-bold text-ink">
                              {decisionThreshold}
                            </span>
                          </span>
                        )}
                      </div>
                    )}

                    {/* Drafted Customer Message Callout in Timeline */}
                    {(msgEn || msgHi) && (
                      <div className="mt-2 space-y-1.5 rounded-control border border-border bg-surface-sunken/60 p-2.5 text-xs">
                        <div className="flex items-center gap-1.5 font-mono text-[10px] font-bold text-ink-muted">
                          <MessageSquare className="h-3 w-3 text-accent" />
                          <span>Customer Outreach Message Drafted</span>
                        </div>
                        {msgEn && (
                          <div className="rounded border border-border/70 bg-surface p-2 text-[11px] text-ink">
                            <span className="font-bold text-accent">EN: </span>
                            {msgEn}
                          </div>
                        )}
                        {msgHi && (
                          <div className="rounded border border-border/70 bg-surface p-2 text-[11px] text-ink">
                            <span className="font-bold text-accent">HI: </span>
                            {msgHi}
                          </div>
                        )}
                      </div>
                    )}

                    {/* General Notes or Reason */}
                    {entry.notes && !rationale ? (
                      <p className="mt-1.5 text-xs text-ink-muted">
                        {entry.notes}
                      </p>
                    ) : null}

                    {/* Model Telemetry Chips */}
                    {entry.model_metadata && (
                      <div className="mt-2 flex flex-wrap gap-1.5 font-mono text-[10px] text-ink-muted">
                        <span className="rounded border border-border/80 bg-surface-sunken px-1.5 py-0.5">
                          {entry.model_metadata.model}
                        </span>
                        {entry.model_metadata.latency_ms !== undefined && (
                          <span className="rounded border border-border/80 bg-surface-sunken px-1.5 py-0.5">
                            {entry.model_metadata.latency_ms.toFixed(1)}ms
                          </span>
                        )}
                        {entry.model_metadata.cost_usd !== undefined &&
                          entry.model_metadata.cost_usd > 0 && (
                            <span className="rounded border border-border/80 bg-surface-sunken px-1.5 py-0.5">
                              ${entry.model_metadata.cost_usd.toFixed(5)}
                            </span>
                          )}
                      </div>
                    )}

                    {entry.model_metadata?.error_detail ? (
                      <div className="mt-2 rounded-control border border-failed/40 bg-failed/5 p-2">
                        <p className="mb-1 text-[10px] font-bold text-failed uppercase">
                          LLM error trace
                        </p>
                        <pre className="max-h-40 overflow-auto rounded bg-surface-sunken p-2 font-mono text-[10px] leading-relaxed whitespace-pre-wrap text-failed">
                          {entry.model_metadata.error_detail}
                        </pre>
                      </div>
                    ) : null}

                    {entry.cost_incurred_paise > 0 ? (
                      <span className="mt-0.5 block font-mono text-xs font-medium text-failed">
                        Cost incurred: -
                        {formatINR(entry.cost_incurred_paise, {
                          maximumFractionDigits: 2,
                        })}
                      </span>
                    ) : null}
                  </div>
                )
              })}
            </section>
          )}

          {activeTab === 'actions' && (
            <section className="space-y-3 rounded-panel border border-border bg-surface-sunken/40 p-4">
              <h3 className="text-sm font-semibold text-ink">
                Operator actions
              </h3>
              <p className="text-sm text-ink-muted">
                Approve an escalated case or simulate a successful customer
                payment through the webhook pipeline.
              </p>
              <div className="flex flex-wrap gap-2 pt-1">
                {caseItem.state === 'ESCALATED' ? (
                  <Button
                    size="sm"
                    onClick={() => {
                      void handleApprove()
                    }}
                    disabled={actionLoading}
                  >
                    {actionLoading ? 'Approving...' : 'Approve case'}
                  </Button>
                ) : null}
                {caseItem.state !== 'RECOVERED' ? (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      void handleSimulatePayment()
                    }}
                    disabled={actionLoading}
                    className="gap-1.5"
                  >
                    <DollarSign className="h-3.5 w-3.5 text-recovered" />
                    {actionLoading ? 'Processing...' : 'Simulate payment'}
                  </Button>
                ) : null}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}
