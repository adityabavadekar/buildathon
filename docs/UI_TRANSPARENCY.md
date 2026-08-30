# UI Transparency Pass

Spec for making the dashboard decipherable: a reviewer cannot tell what a
section is for, what each metric means, or how one screen relates to the next.
The dashboard currently drops a user straight into dense tables and labels
("At Risk Revenue", "Recovered (NRV)") without a plain-language framing for any
of them. Jargon that is obvious to the authors (NRV, touches, holdout arm,
experiment_arm, state names) appears with zero explanation.

This document is the implementation spec. It is read critically against the
backend reality: do not invent meanings, do not hardcode values that already
exist in the API, and do not describe capability that is not actually present.

Scope of this pass (all three are approved):

1. Explain jargon everywhere it is used.
2. Guided recovery-lifecycle explainer (the "how this works" framing).
3. Data density and spacing polish so screens no longer read as held out.

Clarity target: an operator who has never seen this product should be able to
answer, from the UI alone, "what failed, what did the system do, how much money
did it recover, and on what evidence."

## Ground rules

- Every helper-text, tooltip, or explainer sentence must trace to real behavior
  in the backend. If a sentence cannot be sourced, drop it.
- Never hardcode any metric, percentage, or policy value in the UI. Where a
  label needs a number (for example "cost per touch"), pull it from the API or
  from a shared constants module - mirror the backend cost constants, do not
  re-type them.
- Use the existing design tokens (CSS-first Tailwind `@theme`). Do not add a
  tailwind config and do not introduce new emoji or non-ASCII glyphs.
- A shared helper lives in `frontend/src/lib/` (see "Shared glossary component"
  below). Keep drill-down definitions in one place so a definition written twice
  cannot drift.
- All new text is ASCII only, per AGENTS.md.

## 1. Jargon map (the definitions every screen can use)

A single source of truth for terms, expressed as a plain-English glossary so any
view can attach the same explanation. Every term that has a "money path" meaning
must state both what it is and why it matters.

| Term | Placed on | Definition to show |
| --- | --- | --- |
| At Risk revenue | Overview metric card | Gross value of failed and un-recovered transactions being worked by the engine. Not yet recovered. |
| Recovered (NRV) | Overview metric card | Net value recovered after subtracting gateway fees, outreach/SMS/WhatsApp costs, and discounts granted. This is the number that pays the bills, not the gross figure. |
| Gross recovered | Overview card sub-line | Total value of payments that came back, before costs and discounts. See NRV for the net figure. |
| Recovery Rate | Overview metric card | Percent of at-risk cases that reached RECOVERED. A case counts once, not per touch. |
| Need Attention | Overview metric card | Cases escalated to a human because the safety gate paused them (value/risk threshold) or the autonomous loop stopped. Action required. |
| touches | Recovery table column, Case drawer | Number of outbound attempts (WhatsApp/SMS/email/voice or debit retry) spent on this case. Capped by policy. |
| Touch limit (max 3) | Case drawer guardrail block | The engine is not allowed more than this many attempts per transaction before it must stop or escalate. Prevents an unbounded retry loop. |
| Holdout arm | Case drawer badge, Analytics lift banner | A randomly selected share of failed cases the engine deliberately does NOT contact. Used as the control group to prove recovery is real, not natural. |
| experiment_arm | Case drawer badge | The concrete value shown ("treatment" = AI engine worked the case, "holdout" = left uncontacted). |
| treatment | Analytics lift panel | Failed cases the AI engine tried to recover. |
| holdout control | Analytics lift panel | Failed cases left alone to establish the natural baseline that would have recovered anyway. |
| NRV (Net Recovered Value) | Any money summary | Gross recovered minus total costs and discounts. See `money.py` `calculate_net_recovered_value_paise`. |
| Discount granted | Case drawer | Incentive offered to the customer to complete payment; reduces NRV one time. |
| Cost incurred | Audit entries, unit economics | The paise cost of this specific touch (a retry, a WhatsApp/SMS/email/voice message). Values from `core/constants.py`. |
| Policy gate | Policies view, Agent decision feed | The deterministic rule layer (touch cap, cooldown, discount margin cap, opt-out, holdout) that runs before any money action is allowed. |
| Escalated | Recovery view, Overview | Paused by the safety gate for human review/approval. The engine will not act on it automatically until an operator signs off. |

State names (from `audit/state_machine.py`) each need a one-line human reading
in the Recovery table and the Case drawer timeline:

| State | Human reading |
| --- | --- |
| FAILED | Ingested as a failed payment. Entry point of the pipeline. |
| ANALYSIS_QUEUED | Waiting for the diagnoser (LLM or deterministic fallback) to classify the cause. |
| IN_DUNNING | The engine is running outbound recovery touches (WhatsApp/SMS/email dunning) on this case. |
| RETRY_SCHEDULED | A bank-mandate / subscription debit retry is scheduled against the gateway. |
| OUTREACH_PENDING | A recovery touch has been queued and is about to be sent. |
| RECOVERED | Payment captured. Final state; the case is closed. |
| ESCALATED | Paused for human review by the safety gate; not autonomous any more until approved. |

## 2. Guided recovery-lifecycle explainer

Add one shared panel describing the pipeline, reusable at the top of Overview
and Recovery. Because it is shared, the same framing appears wherever the user
first meets the data. Keep it a compact 4-step strip, not an essay:

1. Ingest - a failed payment or subscription halt arrives from the Razorpay
   webhook. (State: FAILED / ANALYSIS_QUEUED)
2. Diagnose - an AI planner (or deterministic NPCI/Razorpay classifier fallback)
   assigns the cause and a bounded recovery strategy.
3. Intervene - the policy gate checks caps, then a bounded set of touches runs:
   dunning outreach and payment links, mandate debit retries.
4. Recover - a payment captures and the case closes; value is attributed against
   the holdout control arm to prove the engine's lift.

Each step maps to a section in the UI so the strip doubles as navigation: the
ingest row in Recovery, the diagnose feed in Agent, the intervene numbers in
Overview channel performance, the recover figure in Analytics NRV. Where a step
needs a number (count in each state), take it from the loaded `cases`, never
hardcode.

Implementation: a `RecoveryLifecycleStrip` component in
`components/recovery/`, exported for embedding in Overview and Recovery. Include
it also as the first thing in the analytics "Counterfactual lift" card so the
A/B panel is never shown without its why.

## 3. Page-level context (what is where)

Add a consistent, small intro header to each view so the first thing a user sees
is what the screen is for, not a table. Pattern: view title (already exists in
most), one-sentence "what this screen is", and one line on "where the data comes
from". Current gaps per view:

- Overview - present, but make the metric cards self-describing (see jargon map
  for At Risk / NRV / rate).
- Recovery - title "Recovery Workspace" with no plain-language sentence. Add:
  "Every failed payment the engine is working, with its cause, status, and the
  next operator action." Clarify the sub-tabs (All / Active / At Risk /
  Recovered / Escalated) mirror the lifecycle states.
- Analytics - dense but framed. Widen the intro for the lift banner so a
  non-researcher reads "we recovered this much more than the control group".
- Agent - "Autonomous Decision Stream" is abstract. Add: "Why the engine chose
  each recovery move, including the raw AI rationale and model used." Also fix
  the two hardcoded numbers in this view (see Fixes below).
- Policies - has a strong description already. Keep, but restate each rule value
  in plain words next to the raw value (for example convert BPS discount cap to
  a percent already shown, keep both).
- Audit - strongest framing on the page; keep, but attach the cost field meaning
  per entry ("what this action cost", via the shared glossary).
- Status - add one line: "Health of the gateway, AI, and policy subsystems that
  power this dashboard."
- Settings - add one line: "Where this instance points and which engine it runs
  on", and note which knobs are read-only because they are env-driven.

## 4. Hardcoded-value fixes (correctness, not style)

The following values are hardcoded in the current components and must be pulled
from data/API instead, both for correctness and because they contradict the "no
hardcoding" rule. Verified in code:

- `AgentView.tsx` - "100%" for "Deterministic Guardrail Pass" and the
  "OpenRouter / Claude" model label are editorialized numbers. Guardrail pass %
  should come from computed cases (audit entries with a POLICY_GATE actor that
  allowed vs. blocked) or be removed; the model name must come from the status/
  settings API, never hardcoded.
- `RecoveryView.tsx` and `CaseDetailDrawer.tsx` - write "max 3" as a literal in
  several places. This is the policy touch cap; it must come from the loaded
  `policies` payload, not be typed as 3 in the component.

## 5. Data density and spacing polish

The feedback "UI looks very held out" reads as: too many equal-weight cards,
too much vertical whitespace, and rows that do not group related information.
Concrete, low-risk fixes that stay within the current design language:

- Secondary text under every metric card already exists; make it carry meaning
  (what the count refers to) instead of a bare "x total failed transactions".
- In the Recovery table, group the three related display fields (Case ID /
  Payment ID / Failure reason) so the eye reads them as one unit; keep money and
  status right-aligned per the `money` utility.
- Reduce inter-card gaps slightly in the Overview metric section and align card
  headers and footers so the four metrics read as one row, not four loose tiles.
- Where a view already has a strong intro (Audit), leave it; do not re-work
  screens that already read well. Polish should target Overview, Recovery,
  Analytics, Agent, and Status - the ones a reviewer flags as opaque or scattered.
- Keep tables dense: the small radii and `font-mono` money columns are already
  correct. Do not convert tables into cards.

## 6. Deliverables / definition of done

- A shared `frontend/src/lib/glossary.ts` exporting the jargon map (term ->
  plain definition), and a `GlossaryTerm`/tooltip primitive in
  `components/ui/` used consistently across views; each definition written once.
- A `RecoveryLifecycleStrip` component shown at the top of Overview and
  Recovery (and referenced by the Analytics lift card).
- Intro context lines added to Recovery, Agent, Status, and Settings.
- Hardcoded values in `AgentView` and the touch-cap literals traced to real
  data.
- Run `make check` (backend lint/typecheck/tests + frontend lint/typecheck/
  build) until clean.

## Verification standards

Like every change: a reviewer must be able to point at each helper-text sentence
and find its backend source. Any sentence that cannot be sourced is cut. Any
number displayed must come from the API or a shared constants module; a number
typed into a component is a regression and fails review.
