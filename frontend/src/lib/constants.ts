export const OUTREACH_CHANNELS = [
  'WHATSAPP',
  'SMS',
  'EMAIL',
  'VOICE_CALL',
] as const

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
  | 'max_touches'
  | 'min_cooldown_hours'
  | 'max_discount_bps'
  | 'holdout_percentage'
  | 'require_human_above_paise'

export const POLICY_FIELD_BOUNDS: Record<
  EditablePolicyField,
  PolicyFieldBounds
> = {
  max_touches: { min: 1, max: 10 },
  min_cooldown_hours: { min: 0 },
  max_discount_bps: { min: 0, max: 5000 },
  holdout_percentage: { min: 0, max: 50 },
  require_human_above_paise: { min: 0 },
}

export type PolicyErrors = Partial<
  Record<EditablePolicyField | 'allowed_channels', string>
>
