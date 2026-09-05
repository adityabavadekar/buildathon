export const OUTREACH_CHANNELS = [
  'WHATSAPP',
  'SMS',
  'EMAIL',
  'VOICE_CALL',
] as const

// The backend reports a provider id (e.g. "openrouter"), not a display name.
// Derive the label instead of maintaining a lookup table here, so a new
// provider added on the backend needs no matching frontend change.
export function llmProviderLabel(provider: string | null): string {
  if (provider === null) {
    return 'Agent'
  }
  return `Agent (${provider.charAt(0).toUpperCase()}${provider.slice(1)})`
}

export type OutreachChannelValue = (typeof OUTREACH_CHANNELS)[number]

export interface OutreachChannelMeta {
  label: string
  description: string
}

export const OUTREACH_CHANNEL_META: Record<
  OutreachChannelValue,
  OutreachChannelMeta
> = {
  WHATSAPP: {
    label: 'WhatsApp',
    description: 'Rich messages with payment links and delivery receipts.',
  },
  SMS: {
    label: 'SMS',
    description: 'Short text alerts for time-sensitive payment nudges.',
  },
  EMAIL: {
    label: 'Email',
    description: 'Detailed statements and checkout recovery links.',
  },
  VOICE_CALL: {
    label: 'Voice Call',
    description: 'Outbound IVR or agent-assisted follow-up calls.',
  },
}

export interface PolicyFieldBounds {
  min: number
  max?: number
}

export type EditablePolicyField =
  | 'max_attempts'
  | 'min_cooldown_hours'
  | 'max_discount_bps'
  | 'holdout_percentage'
  | 'require_human_above_rupees'

export const POLICY_FIELD_BOUNDS: Record<
  EditablePolicyField,
  PolicyFieldBounds
> = {
  max_attempts: { min: 1, max: 10 },
  min_cooldown_hours: { min: 0 },
  max_discount_bps: { min: 0, max: 5000 },
  holdout_percentage: { min: 0, max: 50 },
  require_human_above_rupees: { min: 0 },
}

export type PolicyErrors = Partial<
  Record<EditablePolicyField | 'allowed_channels', string>
>

/** Shown only until the backend reports the absolute URL it builds per request. */
export const WEBHOOK_INGRESS_PATH = '/api/webhooks/razorpay'

/** Mirrors SIMULATED_PAYMENT_LINK_PREFIX in the backend's core constants. */
export const SIMULATED_PAYMENT_LINK_PREFIX = 'plink_sim_'

/**
 * Mirrors MANDATORY_PROVIDER_NAME in the backend's llm/settings_store.py.
 * This provider is always excluded from the active LLM provider list by
 * name, so its enabled flag is never actually checked -- the toggle for it
 * must stay locked to avoid showing an operator a control that does nothing.
 */
export const MANDATORY_LLM_PROVIDER_NAME = 'deterministic_rules'

/** Case states still being worked, so their value is money a merchant can still recover. */
export const OPEN_CASE_STATES = [
  'IN_DUNNING',
  'OUTREACH_PENDING',
  'RETRY_SCHEDULED',
  'ANALYSIS_QUEUED',
] as const

/** What each autonomy mode changes, shown before an operator switches into it. */
export const AUTONOMY_MODE_COPY = {
  FULL_AUTONOMY: {
    label: 'Autonomous',
    effect:
      'The agent will retry payments and contact customers on its own, within your policy caps. You will not be asked to approve each action.',
  },
  HUMAN_IN_THE_LOOP: {
    label: 'Human in the loop',
    effect:
      'The agent will keep diagnosing and planning, but every customer-facing action waits for your approval. Recovery slows down, and cases queue up until you act on them.',
  },
  MONITORING_ONLY: {
    label: 'Paused',
    effect:
      'All outbound retries and customer outreach stop immediately. The agent keeps watching and recording, but recovers nothing while this is on.',
  },
} as const
