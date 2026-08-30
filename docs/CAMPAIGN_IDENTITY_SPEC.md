# Campaign / Merchant-User Identity Spec

Status: Spec only. Researcher-verified against the current code and Razorpay
docs. Merchants can thread their own identifiers (campaign id, user id,
reference id) through Razorpay via the `notes` key/value map (and dedicated
fields). Those identifiers DO come back in payment webhooks. Our pipeline today
captures them only as part of an opaque `metadata` blob on the failure event -
not as indexed, queryable columns - so per-campaign and per-user reporting is
impossible. An implementer must fulfill this and run the End-to-End Verification
Contract at the end, then report the phrase "I have verified this completely
end to end."

## Goal

Give every recovery case a first-class, indexed merchant identity: the campaign
a case belongs to and the merchant's own user/reference id for the customer, so
FORTX can filter, group, and report recovered vs lost revenue per campaign and
per customer. This turns the whole pipeline (detection -> workflow -> audit) into
a per-objective and per-customer view, which the campaign-workflows feature needs.

## What Razorpay supports (verified against Razorpay docs)

- `notes` - a free-form {key: value} map a merchant attaches when creating an
  Order, Invoice, Subscription, Payment Link, or QR code. Razorpay echoes it back
  in webhooks under `payload.<entity>.entity.notes`. This is the standard way to
  carry merchant-defined keys like `campaign_id`, `user_id`, `reference_id`,
  `order_id`.
- `receipt` (Orders API) - a merchant reference string, returned with the order.
- `description` - a free merchant string on the payment entity.
- `customer_id` - if the merchant uses the Customers API, the payment is tied to
  a customer and it comes back in the payment webhook.
- `email` and `contact` - customer contact details on the payment entity.

All of these are present in the `payment.failed`, `payment.captured`, and
`payment.authorized` webhook payloads.

## Current gap (verified on disk)

- `backend/src/app/api/routes/webhooks.py` builds the failure event from the
  payment entity, setting `customer_id` as a single field that collapses
  customer_id -> contact -> "guest_customer", and stores `invoice_id`,
  `subscription_id`, and `metadata=payment_entity` (the raw blob including
  `notes`).
- `backend/src/app/detection/models.py` `RawFailureEvent` has `contact_email`,
  `contact_phone`, `invoice_id`, `subscription_id`, and a generic
  `metadata: dict`. No `campaign_id`, no `user_ref`, no `reference_id`.
- `backend/src/app/audit/models.py` `RecoveryCase` has no campaign/user identity
  fields; the customer is only reachable via `failure_event.customer_id`.
- `backend/src/app/audit/sqlite_store.py` `cases` table has a single indexed
  `customer_id` column; no campaign_id / contact columns; `data_json` stores the
  raw blob.

Result: the merchant's `notes` keys are physically present inside `metadata` but
are not parsed, not indexed, and not usable for filters or per-campaign/per-user
reporting. Also, `contact_email`/`contact_phone` are never populated from the
webhook (the code writes `customer_id` = contact but drops the separate email and
phone), even though `RawFailureEvent` already declares those fields.

## Design

### 1. Capture merchant identity at the webhook

In `webhooks.py`, parse the payment entity and, when present, extract:
- `campaign_id` from `notes["campaign_id"]` (also accept `metadata["campaign_id"]`
  and `notes["utm_campaign"]` as aliases, noting the source used).
- `user_ref` from `notes["user_id"]`, `notes["customer_ref"]`, `notes["reference_id"]`,
  or `notes["order_id"]` (prefer in that order).
- `reference_id` from `notes["reference_id"]` when distinct from the user ref.
- `contact_email` from `entity["email"]` and `contact_phone` from
  `entity["contact"]`.

Populate these on `RawFailureEvent` (add `campaign_id: str | None`,
`user_ref: str | None`, `reference_id: str | None` alongside the already-present
`contact_email`/`contact_phone`). Keep the raw entity in `metadata` unchanged
for full fidelity and audit. Do not silently overwrite a value that is already
present; log a conflict and keep the inbound value.

Note: existing legacy `metadata` blobs may still hold the fields; provide a
one-time backfill that lifts `metadata.notes` keys into the new columns where
they are null.

### 2. Persist as indexed columns

Add to the `cases` table (and to `RecoveryCase`):
- `campaign_id TEXT`
- `user_ref TEXT`
- `reference_id TEXT`
- `contact_email TEXT`
- `contact_phone TEXT`

Index `campaign_id` and `user_ref`. Migrate the schema additively (idempotent
`ALTER TABLE ... ADD COLUMN` guarded by an existence check, or a versioned
`schema_migrations` table). Never drop or rename existing columns.

### 3. Query surface

Extend the repo (and its API routes) so the operator can:
- filter/get cases by `campaign_id`, `user_ref`, and `reference_id`,
- select a cohort by campaign for the campaign-workflow and strategy-experiment
  features,
- report per-campaign and per-user aggregates: at-risk amount, net recovered,
  failed, escalated, and remaining opportunity, always in integer paise with an
  explicit currency and measured against the holdout where recovery is claimed.

### 4. UI

Surface per-campaign grouping and a campaign filter in the operator/merchant
views, plus per-campaign recovered-vs-lost totals sourced exclusively from the
API (no hardcoded campaign lists or percentages). Guard against leaking
`user_ref`/`contact_email`/`contact_phone` where a role should not see PII.
Campaign analytics reuse the existing analytics components.

### 5. Interaction with the holdout and experiments

Campaign identity is metadata on a case, not an experiment arm. Assigning a case
to a campaign must not change arm assignment or bypass the holdout. Campaign
cohort selection for a strategy experiment must still route through the
deterministic arm logic.

## End-to-End Verification Contract

1. A webhook whose payment entity carries `notes: {campaign_id, user_id,
   reference_id}` produces a case with `campaign_id`, `user_ref`, and
   `reference_id` persisted and queryable; null when absent.
2. `contact_email` and `contact_phone` are populated from the webhook entity
   (or remain null when not sent); they are no longer collapsed into
   `customer_id`.
3. A legacy case whose `metadata.notes` already held the keys is backfilled into
   the new columns where null.
4. Filtering by campaign and by user returns the expected subset; per-campaign
   recovered vs lost aggregates match a hand-computed check in integer paise.
5. Campaign assignment does not change experiment-arm assignment or bypass the
   holdout.
6. The UI campaign view renders solely from the API with no hardcoded campaign
   values, and PII fields are not exposed to roles that should not see them.
7. Existing tests still pass, new tests cover parsing, backfill, index use, and
   arm independence. Full suite and `make check` green.

Report: state which of these you have verified completely end to end.
