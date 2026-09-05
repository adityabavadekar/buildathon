/** Single source of truth for merchant-facing audit event and actor labels. */

import { humanizeToken } from '@/lib/format'

export interface AuditEventInfo {
  label: string
  description: string
  tone: 'neutral' | 'action' | 'success' | 'danger' | 'ai'
}

export const AUDIT_EVENTS: Record<string, AuditEventInfo> = {
  'case.ingested': {
    label: 'Payment failed',
    description:
      'A payment failure was received and added to the recovery queue.',
    tone: 'neutral',
  },
  'case.abandoned_stale': {
    label: 'Case closed (no activity)',
    description:
      'No activity on this case for too long; automatically closed as unrecoverable.',
    tone: 'danger',
  },
  'case.operator_approved': {
    label: 'Approved by operator',
    description: 'An operator approved this case for renewed outreach.',
    tone: 'success',
  },
  'agent.plan_formulated': {
    label: 'Strategy chosen',
    description:
      'The AI agent diagnosed the failure and chose a recovery strategy.',
    tone: 'ai',
  },
  'agent.message_drafted': {
    label: 'Message drafted',
    description: 'The AI agent drafted a personalized customer message.',
    tone: 'ai',
  },
  'policy.evaluated': {
    label: 'Safety check',
    description:
      'The chosen strategy was checked against merchant rules and limits.',
    tone: 'neutral',
  },
  'policy.max_attempts_exceeded': {
    label: 'Attempt limit reached',
    description:
      'The maximum number of recovery attempts was reached; sent to a human for review.',
    tone: 'danger',
  },
  'intervention.executed': {
    label: 'Action sent',
    description:
      'A recovery action was sent to the customer (reminder, payment link, or retry).',
    tone: 'action',
  },
  'intervention.blocked': {
    label: 'Action blocked',
    description: 'A safety rule blocked this action from being sent.',
    tone: 'danger',
  },
  'intervention.escalated': {
    label: 'Sent to human review',
    description: 'This case needs a human decision and was escalated.',
    tone: 'danger',
  },
  'intervention.execution_failed': {
    label: 'Action failed',
    description:
      'The recovery action could not be completed and was sent to a human for review.',
    tone: 'danger',
  },
  'intervention.failed': {
    label: 'Action unsuccessful',
    description: 'The recovery action ran but did not succeed.',
    tone: 'danger',
  },
  'intervention.held_circuit_breaker': {
    label: 'Action held',
    description:
      'Automated actions are currently paused by the operator; this action is on hold.',
    tone: 'neutral',
  },
  'intervention.no_action': {
    label: 'No action taken',
    description: 'The AI agent determined no action was needed for this case.',
    tone: 'neutral',
  },
  'intervention.pending_human_approval': {
    label: 'Waiting for approval',
    description:
      'Automated actions require operator approval right now; this action is waiting.',
    tone: 'neutral',
  },
  'worker.outreach_executed': {
    label: 'Follow-up sent',
    description:
      'A scheduled follow-up message was sent as part of the ongoing recovery attempt.',
    tone: 'action',
  },
  'worker.retry_executed': {
    label: 'Retry attempted',
    description: 'A scheduled payment retry was attempted.',
    tone: 'action',
  },
  'worker.pending_human_approval': {
    label: 'Waiting for approval',
    description:
      'Operator approval is required before this case can continue automatically.',
    tone: 'neutral',
  },
  'p2p.reminder_sent': {
    label: 'Payment reminder sent',
    description:
      'The customer promised to pay by a certain date; that date passed, so a reminder was sent.',
    tone: 'action',
  },
  'p2p.promise_missed_escalated': {
    label: 'Promise missed',
    description:
      'The customer did not pay by their promised date even after a reminder; sent to a human for review.',
    tone: 'danger',
  },
  'payment.recovered': {
    label: 'Payment recovered',
    description:
      'The customer completed the payment. Case closed successfully.',
    tone: 'success',
  },
  'payment.dispute.lost': {
    label: 'Dispute lost',
    description:
      'A payment dispute was resolved against the merchant; recovered amount reduced.',
    tone: 'danger',
  },
  'payment_link.paid_reconciled': {
    label: 'Payment link paid',
    description: 'The customer paid through the payment link sent to them.',
    tone: 'success',
  },
  'payment_link.partially_paid': {
    label: 'Partially paid',
    description:
      'The customer paid part of the amount through the payment link.',
    tone: 'neutral',
  },
  'payment_link.expired': {
    label: 'Payment link expired',
    description:
      'The payment link expired before the customer completed payment.',
    tone: 'danger',
  },
  'invoice.paid_reconciled': {
    label: 'Invoice paid',
    description: 'The customer settled the outstanding invoice in full.',
    tone: 'success',
  },
  'invoice.partially_paid': {
    label: 'Invoice partially paid',
    description: 'The customer paid part of the outstanding invoice.',
    tone: 'neutral',
  },
  'invoice.expired': {
    label: 'Invoice expired',
    description: 'The invoice expired without full settlement.',
    tone: 'danger',
  },
  'refund.processed': {
    label: 'Refund processed',
    description: 'A refund to the customer was completed successfully.',
    tone: 'neutral',
  },
  'refund.failed': {
    label: 'Refund failed',
    description: 'A refund attempt failed; no funds were moved.',
    tone: 'danger',
  },
  'smart_collect.reconciled': {
    label: 'Bank transfer received',
    description:
      'A direct bank transfer (NEFT/RTGS/IMPS/UPI) to the collection account was received and matched to this case.',
    tone: 'success',
  },
  'subscription.cancelled': {
    label: 'Subscription cancelled',
    description:
      'The recurring payment mandate was cancelled at the bank; sent to a human for review.',
    tone: 'danger',
  },
  'subscription.completed': {
    label: 'Subscription cycle completed',
    description:
      'A full billing cycle on this subscription completed normally.',
    tone: 'neutral',
  },
  'outreach.voice_call_placed': {
    label: 'Voice call placed',
    description: 'An automated recovery phone call was placed to the customer.',
    tone: 'action',
  },
  'outreach.voice_call_failed': {
    label: 'Voice call failed',
    description:
      'The automated phone call did not connect or complete; falling back to a text message.',
    tone: 'danger',
  },
  'outreach.voice_call_unavailable': {
    label: 'Voice call unavailable',
    description:
      'Calling is not set up for this customer; falling back to a text message.',
    tone: 'neutral',
  },
  'outreach.whatsapp_business_unavailable': {
    label: 'WhatsApp unavailable',
    description:
      'WhatsApp messaging is not set up; falling back to another channel.',
    tone: 'neutral',
  },
  'experiment.holdout_assigned': {
    label: 'Held out for measurement',
    description:
      'This case was randomly assigned to the no-contact control group, used to measure how much the recovery agent actually helps.',
    tone: 'neutral',
  },
  'auth.operator_logged_in': {
    label: 'Operator signed in',
    description: 'An operator signed in to the dashboard.',
    tone: 'neutral',
  },
  'operator.approved': {
    label: 'Approved by operator',
    description:
      'An operator approved this case, returning it to active recovery.',
    tone: 'success',
  },
  'operator.mode_changed': {
    label: 'Automation mode changed',
    description:
      'An operator changed how much the system is allowed to do automatically.',
    tone: 'neutral',
  },
  'benchmark.completed': {
    label: 'Benchmark run completed',
    description: 'A test run measuring recovery performance finished.',
    tone: 'neutral',
  },
  'model.retrained': {
    label: 'Model retrained',
    description:
      'The recovery prediction model was retrained on the latest data.',
    tone: 'neutral',
  },
  'settings.gateway_credentials_imported': {
    label: 'Gateway credentials added',
    description: 'Razorpay API credentials were imported.',
    tone: 'neutral',
  },
  'settings.gateway_credentials_cleared': {
    label: 'Gateway credentials removed',
    description: 'Imported Razorpay API credentials were removed.',
    tone: 'neutral',
  },
  'integrations.oauth_connected': {
    label: 'Razorpay account connected',
    description:
      'The merchant authorized this app to act on their Razorpay account.',
    tone: 'success',
  },
  'integrations.oauth_disconnected': {
    label: 'Razorpay account disconnected',
    description: 'The operator disconnected the Razorpay account connection.',
    tone: 'neutral',
  },
  'integrations.oauth_refreshed': {
    label: 'Connection refreshed',
    description: 'The Razorpay account connection was renewed.',
    tone: 'neutral',
  },
  'integrations.oauth_authorization_failed': {
    label: 'Connection failed',
    description: 'The merchant declined or the connection to Razorpay failed.',
    tone: 'danger',
  },
  'integrations.oauth_revoked_by_merchant': {
    label: 'Access revoked by merchant',
    description:
      'The merchant revoked this app’s access from their Razorpay dashboard.',
    tone: 'danger',
  },
}

/** Actual backend Razorpay webhook event names, passed through verbatim
 * (never renamed by us, so no entry above) but still worth a plain-language
 * gloss since a merchant sees them raw otherwise. */
const RAZORPAY_PASSTHROUGH_EVENTS: Record<string, AuditEventInfo> = {
  'refund.created': {
    label: 'Refund started',
    description: 'A refund to the customer was initiated.',
    tone: 'neutral',
  },
  'refund.speed_changed': {
    label: 'Refund speed changed',
    description: "The refund's processing speed was updated by the bank.",
    tone: 'neutral',
  },
  'payment.dispute.created': {
    label: 'Dispute opened',
    description: 'The customer or their bank opened a payment dispute.',
    tone: 'danger',
  },
  'payment.dispute.won': {
    label: 'Dispute won',
    description: 'The payment dispute was resolved in the merchant’s favor.',
    tone: 'success',
  },
  'payment.dispute.closed': {
    label: 'Dispute closed',
    description: 'The payment dispute was closed.',
    tone: 'neutral',
  },
  'payment.dispute.under_review': {
    label: 'Dispute under review',
    description: 'The payment dispute is being reviewed.',
    tone: 'neutral',
  },
  'payment.dispute.action_required': {
    label: 'Dispute needs action',
    description: 'The payment dispute requires a response.',
    tone: 'danger',
  },
}

export function describeAuditEvent(eventName: string): AuditEventInfo {
  return (
    AUDIT_EVENTS[eventName] ??
    RAZORPAY_PASSTHROUGH_EVENTS[eventName] ?? {
      label: humanizeToken(eventName),
      description: humanizeToken(eventName),
      tone: 'neutral',
    }
  )
}

export interface AuditActorInfo {
  label: string
  sub: string
}

export const AUDIT_ACTORS: Record<string, AuditActorInfo> = {
  SYSTEM: { label: 'System', sub: 'Automated engine' },
  AGENT_LLM: { label: 'AI agent', sub: 'Automated recovery planner' },
  POLICY_GATE: {
    label: 'Safety check',
    sub: 'Rule that approves or blocks actions',
  },
  HUMAN_OPERATOR: { label: 'You (operator)', sub: 'Manual review' },
  GATEWAY_WEBHOOK: { label: 'Razorpay', sub: 'Payment gateway notification' },
}

export function describeAuditActor(actor: string): AuditActorInfo {
  return (
    AUDIT_ACTORS[actor] ?? { label: humanizeToken(actor), sub: 'System entity' }
  )
}
