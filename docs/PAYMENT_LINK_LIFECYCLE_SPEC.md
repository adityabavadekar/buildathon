# Payment Link Lifecycle Recovery Spec

Status: Spec only. Researcher-verified against the current code. The current
`RazorpayPaymentLinkTool` (`backend/src/app/intervention/tools/payment_link.py`)
only creates a single-use link and returns. There is no detection of link
abandonment or expiry, and no resend/extend/cancel/remind lifecycle. Nothing in
this doc is implemented. An implementer must fulfill it and run the End-to-End
Verification Contract at the end, then report the phrase "I have verified this
completely end to end."

## Goal

Turn "issue a link" into a managed lifecycle. When a recovery payment link is
created, the engine should detect that it was not paid before expiry and decide
automatically whether to resend, extend, create a fresh link, send a reminder, or
escalate - rather than treating a link as a one-shot fire-and-forget.

## Current state (verified)

`payment_link.py` sets `expire_by` (15 minutes when a discount applies, else
1440 minutes) and `accept_partial=False`, posts to `POST /v1/payment_links`,
and returns the link. It does not:
- record which link it created on the case,
- track whether the link was viewed or paid,
- resend, extend, or cancel a link,
- react to link lifecycle webhooks.

The case already has fields useful here: `due_at`, `next_action`, `touches_count`,
and the durable `jobs` table for scheduling. The store schema-migration pattern
exists in `audit/sqlite_store.py` for adding new case columns.

## Razorpay payment link facts (verified from docs)

Razorpay exposes payment links as a first-class resource with a lifecycle and
webhooks: `payment_link.created`, `payment_link.paid`,
`payment_link.partially_paid`, `payment_link.expired`, and `payment_link.cancelled`.
There are APIs to fetch a link, cancel it, and update/resend reminders on it.
Rebuild a "paid after link" outcome into the case via the same
`payment_link.paid` webhook that the existing ingress already signs.

## Design

### 1. Record the link on the case

When a link tool runs, persist the returned `link_id`, `short_url`, `expire_by`,
and `reference_id` on the case (add indexed columns, e.g. `payment_link_id`,
`payment_link_url`, `payment_link_expires_at`) so the lifecycle has a handle.
Keep the idempotency-key discipline already used for the link creation.

### 2. Lifecycle states

Introduce explicit link-lifecycle awareness on the case, e.g. a field/state the
worker reads:
- `LINK_ISSUED` - created, awaiting payment.
- `LINK_AWAITING` - reminder scheduled while still valid.
- `LINK_EXPIRED` - passed `expire_by` without payment.
- `LINK_PAID` / `LINK_PARTIALLY_PAID` - terminal-ish outcomes leading to
  `RECOVERED` reconciliation.
- `LINK_CANCELLED` - operator or policy closed it.

Drive these from the `payment_link.expired` webhook (or from a scheduled
eval at `expire_by`) and from `payment_link.paid`.

### 3. Decision on expiry

When a link is due and unpaid, run a bounded decision (deterministic + optional
LLM reasoning, audit-logged) choosing among:
- **Resend / remind** - the link is still valid and the customer just needs a
  nudge. Reuse the notification/outreach tool, bounded by the outreach caps.
- **Extend** - push `expire_by` out (Razorpay update) within a bounded max life.
- **Create a fresh link** - only if the old one cannot be revived; a new
  reference/idempotency key; still bounded.
- **Escalate** - when touches/retries cap reached, or confidence is low, to the
  operator queue with the reason.

The decision must respect the existing policy gate (max touches, cooldowns,
discount caps) and the operator autonomy mode. Do not create unbounded resend
loops. Every chosen action is audit-logged before execution, with the inputs
(after creation, after expiry, touches so far).

### 4. `accept_partial`

The current tool hardcodes `accept_partial=False`. Partial payments are a Razorpay
capability the merchant explicitly flagged as actionable. Make this configurable
per plan / case (a policy field), not hardcoded. When a partial comes in,
`payment_link.partially_paid` should update the case's `collected`/outstanding
rather than treating a partial as a full recovery. Validate the amount math in
integer paise.

### 5. Payload/notes join

Place a case/`reference_id` join key in the link `notes` so the paid/expired
webhooks reconcile deterministically to the case (same approach as Smart
Collect). Handle at-least-once delivery idempotently via the existing job queue.

## End-to-End Verification Contract

1. Create a link via the tool and confirm the `payment_link_id`,
   `payment_link_url`, and `payment_link_expires_at` are persisted on the case.
2. Simulate a `payment_link.expired` webhook (or due-eval) and confirm the engine
   selects a bounded next action (resend/remind/extend/new-link/escalate),
   respects the touch cap, and audit-logs the decision with its inputs.
3. Simulate a `payment_link.paid` webhook carrying the join key and confirm the
   case reconciles to `RECOVERED` and is idempotent on a duplicate delivery.
4. Make `accept_partial` come from policy, not the hardcoded `False`, and
   confirm `partially_paid` updates outstanding rather than full recovery.
5. Confirm no unbounded resend loop: verify a stopping rule (max touches) is
   enforced and excess attempts escalate with a reason.
6. Confirm the UI shows link state, expiry, and whether it was paid, from the
   API. Add tests for expiry-decision, idempotent paid-reconciliation, and the
   partial-payment math. Run the full suite and `make check` green.

Report: state which of these you have verified completely end to end.
