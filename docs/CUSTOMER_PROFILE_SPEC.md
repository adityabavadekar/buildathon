# Customer Recovery Profile Spec

Status: Spec only. Researcher-verified against the current code: there is no
per-customer behavior profile anywhere (no customer_profile module, no
per-customer table or aggregation). The `cases` table has `customer_id` indexed
but nothing aggregates over it. Nothing in this doc is implemented. An
implementer must fulfill it and run the End-to-End Verification Contract at the
end, then report the phrase "I have verified this completely end to end."

## Goal

Build a lightweight, deterministic payment-behavior profile per customer that
feeds opportunity scoring (#2), strategy selection (#3), and human escalation
(#16). The profile turns raw failure/outcome history into signals the engine can
act on:

- historical success / recovery rate,
- usual payment delay (how long a customer takes to pay after a failure),
- preferred payment rail,
- previous recovery success,
- outstanding amount,
- repeat-failure propensity.

Today the escalation queue uses a flat, rule-based `prob` (0.50..0.85) in
`analytics.py` with no customer context. The profile is the missing input that
makes that probability and the recommended action customer-aware.

## Data source

All inputs are derivable from existing `cases` rows keyed by `customer_id`
(plus `payment_rail`, `state`, `recovered_amount_paise`, `occurred_at`,
`created_at`, `amount_paise`). No new ingestion is required.

## Profile shape

Add a computed per-customer profile registry (suggest
`backend/src/app/detection/customer_profile.py`) producing, per `customer_id`:

- `total_cases`, `recovered_cases`, `recovered_rate` (within lifetime or a
  trailing window).
- `avg_payment_delay_hours`: mean time from first failure/`occurred_at` to
  `RECOVERED` across the customer's completed cases.
- `preferred_rail`: the rail with the most successful recoveries (fallback: most
  cases).
- `outstanding_paise`: sum of `amount_paise` over non-terminal cases for the
  customer.
- `repeat_failure_count`: number of times this customer appears with a failure
  in the window; a repeat-failure flag if above a threshold.
- `last_activity_at`.
- A small derived `risk_tier` (e.g. LOW / MEDIUM / HIGH) from deterministic
  rules over the above - not an LLM judgment.

Compute lazily on read and cache with a short TTL; do not add a hot recompute to
the request path. Persist the built profile (JSON under the settings-store
pattern, or a `customer_profiles` table) only if it must survive restarts for
reporting; otherwise computing on demand from `cases` is fine and avoids drift.

## Use in opportunity scoring

In `analytics.py`, replace the flat `prob` guess with a score that blends the
customer profile into the EV: `ev_paise = amount_paise * p_estimate` where
`p_estimate` starts from `cost(customer.recovered_rate)` and is adjusted by
rail health (see RAIL_DEGRADATION_SPEC) and case urgency. Keep it deterministic
and bounded; document the exact formula. The operator queue then ranks by a
customer-informed expected value, not a canned 0.5.

## Use in strategy selection

Allow the planner to bias channel choice from the profile - e.g. a customer who
consistently recovers via UPI intent links is defaulted to that rather than a
generic retry. This must still pass the policy gate and be audited with the
`decision_inputs` including which profile signals were used.

## API surface

Expose the profile read-only so the UI can show it:
`GET /api/customers/{customer_id}/profile` -> the profile fields above.
Optionally a customer view that lists each customer's outstanding, recovered,
and risk tier from the API (no hardcoded tiers). Merge with any campaign/user
identity work when that lands (see DECISIONS notes on campaign/user id).

## End-to-End Verification Contract

1. Seed several cases for one customer (mix of recovered and outstanding, across
   two rails) and confirm `GET /api/customers/{id}/profile` returns a sensible
   recovered_rate, avg delay, preferred rail and outstanding amount computed
   from those cases.
2. Confirm the escalation queue EV ranking changes when customers have
   different recovered rates, so ordering is no longer purely amount- or
   subnet-rule driven (rule-based same-amount cases should now differ by
   profile).
3. Confirm the planner, for a repeat-failure customer, does not choose a blind
   retry when the profile + rail health suggest otherwise, and that the chosen
   action is audit-logged with the profile signals in `decision_inputs`.
4. Confirm the frontend shows the profile from the API and not a hardcoded tier.
5. Run the full test suite and `make check` green, with unit tests for the
   profile aggregation (delay math, rate, preferred rail, tier boundaries) and
   for the scoring change.

Report: state which of these you have verified completely end to end.
