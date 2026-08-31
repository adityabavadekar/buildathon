'use client'

import React from 'react'
import { Check, Radio, ShieldCheck } from 'lucide-react'
import type {
  MerchantPolicyPayload,
  PolicyResponse,
  PolicyRuleDetail,
} from '@/lib/api'
import { updatePolicies } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { OutreachChannelIcon } from '@/components/ui/BrandIcons'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { SkeletonCard } from '@/components/ui/skeleton'
import {
  OUTREACH_CHANNELS,
  OUTREACH_CHANNEL_META,
  POLICY_FIELD_BOUNDS,
  type OutreachChannelValue,
  type PolicyErrors,
  type EditablePolicyField,
} from '@/lib/constants'

interface PoliciesViewProps {
  policies: PolicyResponse | null
  loading: boolean
  onSaved?: (updated: PolicyResponse) => void
}

interface EditablePolicies {
  max_touches: number
  min_cooldown_hours: number
  max_discount_bps: number
  holdout_percentage: number
  require_human_above_paise: number
  allowed_channels: OutreachChannelValue[]
}

const RULE_TO_FIELD: Record<string, EditablePolicyField> = {
  max_touches: 'max_touches',
  cooldown: 'min_cooldown_hours',
  discount_cap: 'max_discount_bps',
  holdout_arm: 'holdout_percentage',
  high_value_threshold: 'require_human_above_paise',
}

const FIELD_UNITS: Record<EditablePolicyField, string> = {
  max_touches: 'touches',
  min_cooldown_hours: 'hours',
  max_discount_bps: 'bps',
  holdout_percentage: '%',
  require_human_above_paise: 'paise',
}

type PolicyRuleDetailWithField = PolicyRuleDetail & { id: EditablePolicyField }

function fromResponse(policies: PolicyResponse): EditablePolicies {
  return {
    max_touches: policies.max_touches,
    min_cooldown_hours: policies.min_cooldown_hours,
    max_discount_bps: policies.max_discount_bps,
    holdout_percentage: policies.holdout_percentage,
    require_human_above_paise: policies.require_human_above_paise,
    allowed_channels: policies.allowed_channels.filter(
      (channel): channel is OutreachChannelValue =>
        (OUTREACH_CHANNELS as readonly string[]).includes(channel),
    ),
  }
}

function policySignature(policies: PolicyResponse): string {
  return [
    policies.max_touches,
    policies.min_cooldown_hours,
    policies.max_discount_bps,
    policies.holdout_percentage,
    policies.require_human_above_paise,
    policies.allowed_channels.join(','),
  ].join('|')
}

function validateField(
  field: EditablePolicyField,
  value: number,
): string | null {
  const bounds = POLICY_FIELD_BOUNDS[field]
  if (!Number.isInteger(value)) {
    return 'Must be a whole number'
  }
  if (value < bounds.min) {
    return `Must be at least ${bounds.min.toString()}`
  }
  if (bounds.max !== undefined && value > bounds.max) {
    return `Must be at most ${bounds.max.toString()}`
  }
  return null
}

interface PolicyEditorProps {
  initial: PolicyResponse
  onSaved?: (updated: PolicyResponse) => void
}

function PolicyEditor({ initial, onSaved }: PolicyEditorProps) {
  const [draft, setDraft] = React.useState<EditablePolicies>(() =>
    fromResponse(initial),
  )
  const [errors, setErrors] = React.useState<PolicyErrors>({})
  const [saving, setSaving] = React.useState(false)
  const [saveMessage, setSaveMessage] = React.useState<string | null>(null)

  const setField = (field: EditablePolicyField, value: number) => {
    setDraft((prev) => ({ ...prev, [field]: value }))
    setErrors((prev) => ({ ...prev, [field]: validateField(field, value) }))
  }

  const toggleChannel = (channel: OutreachChannelValue) => {
    setDraft((prev) => {
      const has = prev.allowed_channels.includes(channel)
      return {
        ...prev,
        allowed_channels: has
          ? prev.allowed_channels.filter((c) => c !== channel)
          : [...prev.allowed_channels, channel],
      }
    })
    setErrors((prev) => ({ ...prev, allowed_channels: undefined }))
  }

  const validateAll = (): boolean => {
    const nextErrors: PolicyErrors = {}
    for (const field of Object.keys(
      POLICY_FIELD_BOUNDS,
    ) as EditablePolicyField[]) {
      const error = validateField(field, draft[field])
      if (error !== null) {
        nextErrors[field] = error
      }
    }
    if (draft.allowed_channels.length === 0) {
      nextErrors.allowed_channels = 'At least one channel must be enabled'
    }
    setErrors(nextErrors)
    return Object.keys(nextErrors).length === 0
  }

  const handleSave = async () => {
    if (!validateAll()) return
    setSaving(true)
    setSaveMessage(null)
    try {
      const payload: MerchantPolicyPayload = {
        merchant_id: initial.merchant_id,
        max_touches: draft.max_touches,
        min_cooldown_hours: draft.min_cooldown_hours,
        max_discount_bps: draft.max_discount_bps,
        holdout_percentage: draft.holdout_percentage,
        require_human_above_paise: draft.require_human_above_paise,
        allowed_channels: [...draft.allowed_channels],
      }
      const saved = await updatePolicies(payload)
      onSaved?.(saved)
      setSaveMessage('Policies saved and now enforced by the policy gate.')
    } catch (err: unknown) {
      setSaveMessage(
        err instanceof Error ? `Save failed: ${err.message}` : 'Save failed',
      )
    } finally {
      setSaving(false)
    }
  }

  const editableRules = initial.rules.flatMap((rule) => {
    const field = RULE_TO_FIELD[rule.id]
    return field ? [{ rule: rule as PolicyRuleDetailWithField, field }] : []
  })

  const enabledChannelCount = draft.allowed_channels.length

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 shrink-0 text-accent" />
          <CardTitle>Merchant Recovery Policies & Guardrails</CardTitle>
        </div>
        <CardDescription>
          Active deterministic boundaries enforced on all AI recovery
          interventions. Edit values and save; the gate enforces the saved
          values at once.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-8">
        <section className="space-y-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h3 className="text-sm font-semibold text-ink">
                Recovery Limits
              </h3>
              <p className="mt-0.5 text-xs text-ink-muted">
                Numeric guardrails applied before any outreach is attempted.
              </p>
            </div>
            <Badge variant="recovered">All enforced</Badge>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            {editableRules.map(({ rule, field }) => {
              const bounds = POLICY_FIELD_BOUNDS[field]
              const unit = FIELD_UNITS[field]
              return (
                <div
                  key={rule.id}
                  className="rounded-panel border border-border bg-surface-sunken/40 p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 space-y-1">
                      <span className="text-sm leading-snug font-semibold text-ink">
                        {rule.name}
                      </span>
                      <p className="text-xs leading-relaxed text-ink-muted">
                        {rule.description}
                      </p>
                      {errors[field] ? (
                        <span className="text-danger block text-xs">
                          {errors[field]}
                        </span>
                      ) : null}
                    </div>
                    <Badge
                      variant={rule.enforced ? 'recovered' : 'default'}
                      className="shrink-0"
                    >
                      {rule.enforced ? 'On' : 'Off'}
                    </Badge>
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    <input
                      type="number"
                      className="field-input max-w-28"
                      value={draft[field].toString()}
                      min={bounds.min}
                      max={bounds.max}
                      aria-label={rule.name}
                      aria-invalid={errors[field] ? 'true' : undefined}
                      onChange={(event) => {
                        setField(field, Number(event.target.value))
                      }}
                    />
                    <span className="font-mono text-xs text-ink-muted">
                      {unit}
                    </span>
                  </div>
                  <p className="mt-2 font-mono text-[11px] text-ink-subtle">
                    Current: {rule.value}
                  </p>
                </div>
              )
            })}
          </div>
        </section>

        <section className="space-y-4 border-t border-border pt-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h3 className="text-sm font-semibold text-ink">
                Allowed Outreach Channels
              </h3>
              <p className="mt-0.5 text-xs text-ink-muted">
                The payment-recovery engine may only message customers through
                channels you keep enabled. Unchecking a channel blocks it at
                execution time, not just in this screen.
              </p>
            </div>
            <Badge variant="outline">
              {enabledChannelCount.toString()} of{' '}
              {OUTREACH_CHANNELS.length.toString()} enabled
            </Badge>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {OUTREACH_CHANNELS.map((channel) => {
              const meta = OUTREACH_CHANNEL_META[channel]
              const selected = draft.allowed_channels.includes(channel)
              return (
                <label
                  key={channel}
                  className={`channel-card ${selected ? 'channel-card--selected' : ''}`}
                >
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={selected}
                    onChange={() => {
                      toggleChannel(channel)
                    }}
                  />
                  <div className="channel-card-icon">
                    <OutreachChannelIcon
                      channel={channel}
                      className="h-5 w-5"
                    />
                  </div>
                  <div className="min-w-0 flex-1">
                    <span className="text-sm font-semibold text-ink">
                      {meta.label}
                    </span>
                    <p className="mt-0.5 text-xs leading-relaxed text-ink-muted">
                      {meta.description}
                    </p>
                  </div>
                  <span
                    className={`channel-card-check ${selected ? 'channel-card-check--on' : ''}`}
                    aria-hidden
                  >
                    {selected ? (
                      <Check className="h-3.5 w-3.5" />
                    ) : (
                      <Radio className="h-3.5 w-3.5 opacity-30" />
                    )}
                  </span>
                </label>
              )
            })}
          </div>
          {errors.allowed_channels ? (
            <span className="text-danger text-xs">
              {errors.allowed_channels}
            </span>
          ) : null}
        </section>

        <div className="flex flex-wrap items-center gap-3 border-t border-border pt-6">
          <Button
            variant="primary"
            onClick={() => {
              void handleSave()
            }}
            disabled={saving}
          >
            {saving ? 'Saving...' : 'Save Policies'}
          </Button>
          {saveMessage ? (
            <span className="text-sm text-ink-muted">{saveMessage}</span>
          ) : null}
        </div>
      </CardContent>
    </Card>
  )
}

export function PoliciesView({
  policies,
  loading,
  onSaved,
}: PoliciesViewProps) {
  if (loading || !policies) {
    return <SkeletonCard />
  }
  return (
    <div className="space-y-6">
      <p className="border-b border-border pb-4 text-sm text-ink-muted">
        Configure deterministic recovery limits and approved customer outreach
        channels.
      </p>
      <PolicyEditor
        key={policySignature(policies)}
        initial={policies}
        onSaved={onSaved}
      />
    </div>
  )
}
