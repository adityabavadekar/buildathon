# Rail Degradation Detection and Auto-Halt Spec

Status: Spec only. Researcher-verified against the current code. The systemic
failure classification exists per-case (`SYSTEMIC_GATEWAY_FAILURE`), but there
is NO fleet-wide degradation detection and NO automated halt of blind retries.
Nothing in this doc is implemented. An implementer must fulfill it and run the
End-to-End Verification Contract at the end, then report the phrase "I have
verified this completely end to end."

## Goal

Detect a payment-rail degradation event (for example "UPI failure rate 4.2x
normal") across the fleet and, while it is active, stop blindly retrying
thousands of customers on that rail. Instead of a fixed retry policy, the
engine should recognise the systemic problem, hold retries on the degraded rail,
and change the recovery policy until the rail recovers. This is the "killer
AI-judgment feature" and the primary way the product proves it is not just a
naive retry loop.

## Design principles

- Degradation is a **fleet-level** signal, computed over the accumulated case +
  outcome history, never per-event. The data already exists: `cases` rows carry
  `payment_rail`, `error_source`, `state`, `created_at`, `occurred_at`, and
  outcome fields (`RECOVERED`, terminal states), and there is a `jobs` table for
  processing history.
- The detector is **deterministic statistical math**, not an LLM call per event.
  The LLM writes the explanation of the event; the statistical detector decides
  whether the rail is degraded and whether to halt.
- The halt must be **bounded, reversible, and audited**: it is a temporary
  circuit breaker on one rail, keyed by rail + window, that lifts automatically
  once the rail recovers above threshold. It must never permanently disable a
  rail.
- Everything a merchant sees (degraded flag, per-rail failure rate, normal
  baseline, ratio, remaining hold window) comes from an API; nothing is
  hardcoded in the UI.

## The statistical detector

Add a rail health component (suggest `backend/src/app/detection/rail_health.py`)
that, for a sliding window, computes per rail:

- `failures`: count of failed attempts on the rail in the window.
- `attempts`: total attempts on the rail in the window.
- `current_failure_rate`: `failures / attempts` where attempts > 0.
- `baseline_failure_rate`: the long-run historical failure rate for the rail,
  from a preceding baseline window (e.g. the prior 7-30 days excluding the
  current window). If insufficient baseline data, do not flag; a detector that
  fires with no baseline is unusable.
- `ratio`: `current_failure_rate / baseline_failure_rate`.

**Flag condition:** a rail is `DEGRADED` when all of:
1. The current window has enough attempts to be statistically meaningful
   (`min_attempts`, a configurable floor, e.g. 30).
2. `ratio >= degradation_ratio_threshold` (default e.g. 3.0, meaning 3x normal).
3. `current_failure_rate >= absolute_min_rate` (default e.g. 0.05) so a tiny
   absolute rate with a low baseline does not trigger.

All three thresholds (and the window lengths, `min_attempts`, and the hold
duration) are configurable on `Settings` in `core/config.py` and/or the merchant
policy. Do not scatter constants.

**Recommended defaults (add to `core/constants.py` or Settings):**
`RAIL_HEALTH_WINDOW_MINUTES`, `RAIL_BASELINE_DAYS`, `RAIL_MIN_ATTEMPTS`,
`RAIL_DEGRADATION_RATIO`, `RAIL_ABSOLUTE_MIN_RATE`, `RAIL_HOLD_MINUTES`.

## Persistent degraded-rail state

Introduce a persisted, thread-safe registry holding, per rail:
`{ rail, state (NORMAL|DEGRADED), detected_at, hold_until, current_rate,
 baseline_rate, ratio, last_observed_at }`. Persist to a JSON file under the
existing settings pattern (mirror `llm/settings_store.py`) OR a SQLite table so
it survives restarts and is inspectable in the audit trail. Compute/refresh it
(evaluate all rails) on the worker loop tick and lazily before any outbound
touch.

## Interaction with the recovery policy

- When a rail is `DEGRADED`, the planner/orchestrator and the executor must
  **hold PASSIVE_RETRY and SMART_RETRY on that rail** rather than sending them.
  The held attempt is recorded in the audit trail with
  `event_name="recovery.rail_hold"`, the rail, the detected ratio, and the
  `hold_until` timestamp, so an operator can see exactly what was suppressed and
  why.
- Strategies that are not blind retries may still be considered with operator
  awareness: converting a degraded-rail retry into a payment link on a healthy
  rail, or a reminder, or routing to a different rail, provided the policy gate
  allows it and it is audited. Do not automatically do expensive or irreversible
  things; if in doubt, escalate to the operator queue with the degradation
  reason.
- The circuit breaker is **auto-releasing**: once `current_failure_rate` returns
  below the release threshold (recovery below, e.g. `ratio < release_ratio` or
  rate under baseline + margin) for a confirm window, the rail returns to
  `NORMAL` and normal retry policy resumes. This is important: a permanent block
  is a bug.
- While degraded, surface a clear signal to the merchant UI (a "rail degraded"
  affordance on the affected rail with the ratio and hold window), fetched from
  the API, never hardcoded.

## API surface

Add a read route (e.g. under `api/routes/pipeline.py` or a new
`api/routes/rail_health.py`) returning per-rail health:
`GET /api/rails/health` -> `[{ rail, state, current_failure_rate,
 baseline_failure_rate, ratio, hold_until, detected_at }]`. Optionally a
time-series of per-rail rate for the UI. This must be read-only over the same
data the UI already uses; no hardcoded breakdowns.

## Interaction with the existing classifier

The per-case classifier already emits `SYSTEMIC_GATEWAY_FAILURE` and
`TRANSIENT_BANK_WINDOW`. Do not disturb that. The rail-health detector operates
above it at the fleet level. When a case is classified as systemic AND its rail
is currently degraded, the recommendation should reflect the hold (e.g. no
immediate blind retry; prefer link/reminder/escalate with the degradation
reason). Keep the two layers separate and composable.

## End-to-End Verification Contract

1. Seed a batch of failures on one rail (e.g. UPI with `bank_technical_error`
   or `INTERNAL_SERVER_ERROR`) into a degraded state and confirm
   `GET /api/rails/health` reports that rail as `DEGRADED` with a ratio at or
   above the threshold and a `hold_until` in the future.
2. Confirm that while degraded, retry-style plans on that rail are held (audit
   rows `recovery.rail_hold` with the ratio and rail) and are NOT sent as blind
   retries, and that other rails are unaffected.
3. Confirm the rail auto-recovers: simulate the rail returning to normal rates
   and confirm the registry flips back to `NORMAL` and normal retry policy
   resumes, with no operator action required.
4. Confirm the UI shows the degraded rail and ratio from the API, not a
   hardcoded value, and that when no rail is degraded all rails show `NORMAL`.
5. Confirm the degraded flag and all evidence (ratio, rates, hold window) are
   visible in the audit trail.
6. Run the full test suite and `make check` green. Add tests for the detector
   (threshold math, insufficient-baseline no-fire, auto-release) and for the
   hold behavior in the executor.

Report: state which of these you have verified completely end to end.
