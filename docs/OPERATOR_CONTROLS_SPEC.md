# Operator Controls Spec - Autonomy Modes and Case Directory Filtering

Status: Spec only, researcher-verified against current code. Nothing here is
implemented. An implementer must fulfill it and run the End-to-End Verification
Contract at the end. Superseded by the working implementation recorded in
`docs/DECISIONS.md`: operator autonomy modes (persisted, audited, API-served) in
`backend/src/app/core/operator.py` and `backend/src/app/api/routes/operator.py`,
server-side case filtering in the relational store, and the EV-prioritized
escalation queue. Kept as the design record; verified by
`backend/tests/test_operator_controls.py`.

## Part 1 - Autonomy modes must actually gate behavior

### Verified current problem

- `frontend/src/components/layout/AutonomySwitcher.tsx` implements
  FULL_AUTONOMY / HUMAN_IN_THE_LOOP / MONITORING_ONLY as pure local React
  `useState` (AutonomySwitcher.tsx:17-22).
- It is rendered from `TopNav.tsx:71` with **no props**, so `onChange` is
  never called. Flipping any mode changes nothing anywhere.
- The backend has no autonomy state at all. `simulation.py:160` hardcodes
  `"circuit_breaker": "ACTIVE"` and `"offline_fallback_operational": True`,
  and `simulation.py:166-170` hardcodes policy numbers. These are fake status
  values that violate the "no hardcoding" rule and misrepresent the system.

A global mode control that does nothing is worse than none: it implies safety
behavior that does not exist. The demo and the audit trail must be truthful.

### Required behavior

Add a real, persisted, audited autonomy mode with three states:

1. `FULL_AUTONOMY` - interventions execute without operator approval (current
   default behavior, but now explicit and recorded).
2. `HUMAN_IN_THE_LOOP` - the orchestrator must pause at the execution step for
   any case that would otherwise auto-execute a real intervention. The case
   moves to a `PENDING_APPROVAL` state (or equivalently ESCALATED), a job is
   queued with a human-approval touchpoint, and the worker does nothing until
   the operator approves. `GET /cases/{id}` and the audit trail show
   "waiting for operator approval."
3. `MONITORING_ONLY` (Paused) - the **global circuit breaker**: all outbound
   interventions are held. The pipeline still ingests, diagnoses, plans,
   gates, and schedules, but every job that would execute a touch stays queued
   in a "held" state with an explicit reason. Nothing is dropped, nothing is
   sent, recovery is not claimed.

Design requirements:

- Persistence: an `operator_mode` key in the same config store as LLM
  settings (`data/llm_config.json` pattern) or a dedicated row, not a
  hardcoded default and not memory-only.
- API: `GET /api/operator/mode` and `PUT /api/operator/mode` with a body
  like `{"mode": "HUMAN_IN_THE_LOOP", "reason": "..."}`.
- Every mode change is audit-logged with actor, from, to, reason, timestamp.
- The worker and orchestrator read the mode at execution time (read each
  claim, do not cache it), so a switch takes effect immediately and
  mid-batch.
- The mode must be visible on every relevant screen and in the status
  endpoint. The StatusView "global circuit breaker" and the TopNav switcher
  are driven by this API value, never by a local toggle.
- `simulation.py` status hardening: replace the hardcoded `circuit_breaker`,
  `offline_fallback_operational`, and `policy_enforcement` literals with
  real derived values (mode state, actual policy object, real LLM provider
  availability).

### Frontend

- `AutonomySwitcher` becomes a controlled component: value + `onChange` call
  the API, show the API's saved/error state, and reverted to the persisted
  value on failure. No optimistic local-only state.
- When MONITORING_ONLY, a banner shows "Outbound interventions held" and the
  dashboard's claimed recovery figures are annotated accordingly.

## Part 2 - Case Directory advanced filtering

### Verified current problem

- Backend `GET /cases` accepts only `merchant_id`, `state`, `experiment_arm`,
  `limit`, `offset` (cases.py:42-69).
- The store (`sqlite_store.py:298-361`) builds `WHERE` clauses only from
  those three columns. Case metadata (rail, error code, customer, amount,
  timestamps, touch counts) lives in the `data_json` blob and is not
  queryable.
- Frontend `RecoveryView.tsx:90-119` filters client-side: state tabs plus a
  text search over only `case_id`, `payment_id`, `customer_id`,
  `error_reason`. `app/page.tsx:50` loads `listCases()` with no pagination
  params, so the directory is capped at the first 50 loaded cases and
  filtering only works over that slice. There is no sort control.

### Required backend contract

Extend `GET /cases` with server-side filters and sort, and add only
parameterized predicates. Filters to support (each optional, combinable):

- `state` (list of states allowed, not just one) and `experiment_arm`
  (existing, keep).
- `payment_rail` (one or many).
- `error_code` and `error_source` (one or many).
- `amount_min_paise` / `amount_max_paise` (inclusive range).
- `created_after` / `created_before` and `occurred_after` /
  `occurred_before` (timezone-aware UTC).
- `touches_min` / `touches_max`.
- `recovered` boolean (recovered_amount_paise > 0).
- `opted_out` boolean.
- `has_escalation` boolean (state is ESCALATED or an escalation audit entry
  exists).
- `customer_id`, `payment_id`, `invoice_id`, `subscription_id` (exact or
  prefix match, parameterized).
- `q` free text that searches case_id, payment_id, customer_id,
  invoice_id, subscription_id, error_reason, and next_action.
- `model_used` - cases whose plan-formulated audit entry has this model in
  `model_metadata.model` (enables "what did model X do").
- `sort_by` in {created_at, updated_at, amount_paise, recovered_amount_paise,
  touched_at, next_due_at} and `sort_dir` in {asc, desc}.

Persistence/query notes:

- Promote the filterable fields to real, indexed columns on `cases`, or add
  them, so filters run in the store, not over re-parsed `data_json` in
  Python. `q` and `model_used` may be joins/JSON lookups but must stay
  parameterized.
- `list_cases` and `count` must share one filter-predicate builder so `total`
  always equals the filtered page count.
- Multi-select lists keep `IN (...)` parameterized with bounds; never
  interpolate user input.

### Required frontend behavior

- A filter bar in RecoveryView: rail multiselect, error-code multiselect,
  amount range, date range, touches range, experiment arm, recovered toggle,
  opted-out toggle, free-text `q`, and sort picker. Filter chips show active
  filters; a "Clear all" resets.
- All filtering and sorting are **server-side**: changing a filter calls
  `listCases` with the new query params and replaces the list. No
  client-side slicing over the loaded page.
- Pagination controls (page size, offset, total from response) wired to the
  same filter state so paging preserves filters.
- The search field in the existing command palette can reuse the same search.

## End-to-End Verification Contract (MANDATORY)

Run and demonstrate, then report "I have verified this completely end to end":

1. Put the switch in HUM... HITL: seed events, confirm real interventions stop
   at PENDING_APPROVAL, approve one, confirm it resumes exactly once.
2. Put the switch in MONITORING_ONLY: confirm every outbound touch is held,
   diagnostics/planning still happen, nothing is dropped, and the status
   endpoint reflects the change instead of hardcoded values.
3. Switch mode live while the worker is mid-batch: confirm the very next
   claim observes the new mode (no cached mode).
4. Every mode change appears in the audit trail with actor/reason/timestamp.
5. Filter the directory by at least: rail + error code + amount range + date
   range + q + recovered + model_used, confirm `total` matches the visible
   filtered rows, and confirm pagination preserves the filters.
6. Confirm no non-ASCII characters and no hardcoded numbers/strings in the
   new UI code, per repo rules.
7. `make check` green (backend tests, ruff, mypy, eslint, tsc, frontend
   build).