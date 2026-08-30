# Smart Collect Recovery Spec

Status: Spec only. Researcher-verified against the current code and Razorpay
docs (razorpay.com/docs/api/payments/smart-collect and
razorpay.com/docs/webhooks/smart-collect). Nothing in this doc is implemented.
An implementer must fulfill it and run the End-to-End Verification Contract at
the end, then report the phrase "I have verified this completely end to end."

## Goal

Broaden recovery beyond cards/checkout/links to B2B and high-value bank
transfers using Razorpay Smart Collect. Smart Collect lets the business create a
per-customer virtual account / customer identifier that the customer pays into
via NEFT, RTGS, IMPS, or UPI. The engine can issue a virtual account to a
delinquent B2B/high-value customer, share the identifier as its recovery
touch, then reconcile the incoming payment via webhooks and close the case. This
turns the receivables workflow (#5) into a real collections pipeline with direct
bank settlement, not just a payment link.

## What Smart Collect provides (verified)

- Create a virtual account for a customer identifier:
  `POST /v1/virtual_accounts` with `receivers.types` in
  `[bank_account, vpa, qr_code]`, optional `customer_id`, `close_by`,
  `notes`. The response includes the bank account / VPA / QR receiver to share.
- Fetch/close virtual accounts: `GET /v1/virtual_accounts`,
  `POST /v1/virtual_accounts/:id/close`.
- Webhooks: `virtual_account.created`, `virtual_account.credited`,
  `virtual_account.closed`. The `credited` payload carries a `bank_transfer`
  entity with `payment_id`, `mode` (`NEFT`/`RTGS`/`IMPS`/`UPI`), `amount`,
  `payer_bank_account`, and `virtual_account_id` - this is the reconciliation
  touchpoint.
- Audited/credited amounts and fees come through the payloads (`amount_paid`,
  `fee`, `tax`).
- Auth: same Razorpay key id/secret over `https://api.razorpay.com/v1`. In
  partner/sub-merchant mode an `X-Razorpay-Account` header is used; the current
  repo targets a single merchant with direct keys, so keep direct-auth as
  primary and treat the partner header as out of scope unless the account work
  (see notes) lands.

## Design

### 1. Ingestion / reconciliation seam

The existing webhook ingress (`POST /api/webhooks/razorpay`, already HMAC-verified
and 202-enqueue async) currently handles `payment.failed` and related. Extend the
same listener to recognize Smart Collect events - primarily
`virtual_account.credited`. On credited:
- Parse the `bank_transfer` entity (payment_id, virtual_account_id, amount,
  mode).
- The virtual account carries `notes` (which the engine set at creation, e.g.
  the matching `case_id` / `idempotency_key`) plus `customer_id`, so the credit
  can be matched to the open recovery case deterministically. Store both the
  case join key and the virtual_account_id on the case.
- Enqueue a reconciliation job (reuse the durable `jobs` queue) so a credit is
  not lost and is idempotent against retries (the webhook is at-least-once).

### 2. Case data model

Add indexed columns to the case/store for this workflow so the audit trail and
the UI can tie a credit to a case:
- `virtual_account_id`
- `bank_transfer_id`
- `collected_amount_paise` (actual credited amount)
- `collection_mode` (`NEFT`/`RTGS`/`IMPS`/`UPI`)
- `collected_at`

This mirrors the existing `invoice_id` / `subscription_id` pattern. The store
schema migration section in `audit/sqlite_store.py` already shows the pattern
for adding columns via `ALTER TABLE ... ADD COLUMN`.

### 3. New intervention strategy

Add a recovery strategy for B2B/high-value receivables (suggest
`InterventionType.SMART_COLLECT` + a tool under
`backend/src/app/intervention/tools/` mirroring `payment_link.py`):
- Create a per-case virtual account with `close_by` set to a bounded window and
  `notes` carrying the case join key.
- Share the receiver (VPA/QR/bank account) as the outreach payload.
- Track the account as "awaiting collection" (`P2P_WAITING`-style or a dedicated
  state), with a bounded `close_by`.
- On `virtual_account.credited`, mark collected, close the account, reconcile,
  and transition the case to `RECOVERED` with the actual `collected_amount_paise`.
- On `virtual_account.closed` without credit (or expiry), decide next step
  (re-extend once, remind, or escalate) subject to the same bounded retry /
  touch caps and policy gate as every other intervention.

Keep the Razorpay live-vs-sandbox fallback exactly like `payment_link.py`: real
API when keys are set, deterministic sandbox simulation object when they are
not. Reuse `httpx2` (never `httpx`) and the idempotency-key pattern.

### 4. Targeting

Enable this strategy only for cases the operator/policy deems B2B or
high-value (e.g. `B2B_INVOICE` rail or amount above a configurable threshold),
so the engine does not create bank accounts for small consumer failures. Ties
into the Customer Recovery Profile (#15) and the rail-health/bounds in the
merchant policy. It must remain a bounded, merit-selected strategy, not a
default for every failure.

### 5. Display

Expose the collection status in the case directory and details via the API
(virtual account, mode, credited amount, collection state) - no hardcoded
values. Show an "awaiting bank credit" state clearly distinct from a card
retry.

## Interaction with other specs

- Depends on the durable pipeline queue (DATA_PIPELINE_SPEC) and the webhook
  ingress being async (both already implemented).
- Reconcile against the Customer Recovery Profile (#15) for targeting and
  scoring.
- Respect operator autonomy mode (OPERATOR_CONTROLS_SPEC) and the merchant
  policy gate (bounded amounts, caps, escalation).

## End-to-End Verification Contract

1. With Razorpay keys set, trigger a B2B/high-value case and confirm the engine
   issues a virtual account (`virtual_account_id` stored on the case) and
   returns shareable receiver details in the touch payload.
2. Simulate/emit a `virtual_account.credited` webhook carrying the `notes`
   join key and confirm a reconciliation job runs, the case transitions to
   `RECOVERED` with the credited `collected_amount_paise`, and it is idempotent
   against a duplicate webhook delivery.
3. Confirm a `virtual_account.closed` without credit does not lose the case: it
   either re-extends, reminds, or escalates within the touch caps, and the
   decision is audit-logged.
4. Confirm the sandbox mode (no keys) produces a simulated virtual account and
   a simulated credit path so tests and demos run offline.
5. Confirm the UI shows the collection state, mode, and credited amount from the
   API.
6. Add tests for the credited-reconciliation logic, idempotency, the close
   fallback, and the targeting rule. Run the full suite and `make check` green.

Report: state which of these you have verified completely end to end.
