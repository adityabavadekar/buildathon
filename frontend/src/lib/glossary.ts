/** Single source of truth for UI terms, financial metrics, and lifecycle states. */

export interface GlossaryDefinition {
  term: string
  title: string
  definition: string
  whyItMatters: string
}

export const GLOSSARY: Record<string, GlossaryDefinition> = {
  AT_RISK_REVENUE: {
    term: 'At Risk Revenue',
    title: 'Gross At-Risk Revenue',
    definition:
      'Gross value of failed and un-recovered transactions currently being worked by the engine.',
    whyItMatters:
      'Represents potential revenue loss if no recovery intervention is performed.',
  },
  RECOVERED_NRV: {
    term: 'Recovered (NRV)',
    title: 'Net Recovered Value (NRV)',
    definition:
      'Net value recovered after deducting gateway retry fees, outreach/SMS/WhatsApp costs, and discounts granted.',
    whyItMatters:
      'This is the true net bottom-line money recovered, not the gross invoice amount.',
  },
  GROSS_RECOVERED: {
    term: 'Gross Recovered',
    title: 'Gross Recovered Value',
    definition:
      'Total nominal value of failed payments that were successfully captured, before costs and discounts.',
    whyItMatters:
      'Shows headline top-line recovered cash volume before deducting channel execution expenses.',
  },
  RECOVERY_RATE: {
    term: 'Recovery Rate',
    title: 'Cohort Recovery Rate (%)',
    definition:
      'Percentage of at-risk cases that reached RECOVERED state. A case counts once, not per attempt.',
    whyItMatters:
      'Measures autonomous conversion effectiveness across failed checkout and mandate cohorts.',
  },
  NEED_ATTENTION: {
    term: 'Need Attention / Escalated',
    title: 'Human Review Queue',
    definition:
      'Cases paused by policy guardrails (e.g. value threshold, custom dispute, low AI confidence) requiring manual operator review.',
    whyItMatters:
      'Guarantees human oversight and prevents runaway automated interventions on sensitive accounts.',
  },
  ATTEMPTS: {
    term: 'Attempts',
    title: 'Recovery Attempts',
    definition:
      'Number of outbound actions (WhatsApp/SMS dunning, payment links, mandate retries) spent on this case.',
    whyItMatters:
      'Strictly bounded to prevent customer spam and unnecessary per-attempt gateway fees.',
  },
  ATTEMPT_LIMIT: {
    term: 'Attempt Limit',
    title: 'Deterministic Attempt Cap',
    definition:
      'Maximum allowable recovery attempts (default 3) per transaction before the engine must pause or escalate.',
    whyItMatters:
      'Enforces stopping rules so retry loops are always strictly bounded.',
  },
  HOLDOUT_ARM: {
    term: 'Holdout Arm',
    title: '10% Counterfactual Control Arm',
    definition:
      'A randomly assigned 10% sample of failed cases the engine deliberately leaves uncontacted.',
    whyItMatters:
      'Establishes the natural baseline recovery rate to mathematically prove true AI recovery lift.',
  },
  TREATMENT_ARM: {
    term: 'Treatment Arm',
    title: 'Active Treatment Cohort',
    definition:
      'Failed transactions actively worked by the AI agent, deterministic classifier, and smart dunning tools.',
    whyItMatters:
      'Performance is benchmarked directly against the holdout control arm to measure incremental uplift.',
  },
  POLICY_GATE: {
    term: 'Policy Gate',
    title: 'Deterministic Safety Gate',
    definition:
      'Pre-execution rule layer checking attempt caps, cooldown intervals, margin discount limits, and customer opt-outs.',
    whyItMatters:
      'Guarantees the AI cannot violate financial margins or spam customers regardless of LLM output.',
  },
  DISCOUNT_GRANTED: {
    term: 'Discount Granted',
    title: 'Recovery Incentive Discount',
    definition:
      'Margin-capped dynamic incentive (e.g. 5%) offered to motivate checkout completion.',
    whyItMatters:
      'Deducted once from Gross Recovered to calculate true Net Recovered Value.',
  },
}

export const STATE_READINGS: Record<string, string> = {
  FAILED: 'Ingested as a failed payment. Entry point of the recovery pipeline.',
  ANALYSIS_QUEUED:
    'Waiting for contextual failure classification and recovery plan generation.',
  IN_DUNNING:
    'Running bounded outbound customer communication (WhatsApp/SMS dunning).',
  RETRY_SCHEDULED:
    'Smart debit retry scheduled after transient bank maintenance window.',
  OUTREACH_PENDING:
    'Single-use fallback payment link generated; outreach queued for delivery.',
  P2P_WAITING:
    'Waiting for promised payment confirmation after customer engagement.',
  P2P_PROMISED:
    'Customer committed to pay; automated aggressive retries paused.',
  RECOVERED:
    'Payment captured on gateway. Final state; case closed with positive NRV.',
  ESCALATED:
    'Paused by safety guardrail for human review; autonomous loop halted.',
  ABANDONED:
    'Exhausted maximum allowed attempts or expired without customer completion.',
  WRITTEN_OFF: 'Marked uncollectible after exhaustive dunning schedule.',
}
