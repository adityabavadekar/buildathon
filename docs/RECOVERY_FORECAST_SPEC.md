# Recovery Forecast and Remaining Opportunity Spec

Status: Spec only. Researcher-verified against the current code. The analytics
summary already exposes `total_at_risk_paise`, `recovered_amount_paise`,
`net_recovered_value_paise`, `overall_recovery_rate_pct`, and per-rail/category
breakdowns (analytics.py). What is missing is the merchant-facing recovery
funnel: turning the at-risk pool into an expected-recoverable estimate and a
"remaining opportunity" number. Nothing in this doc is implemented. An
implementer must fulfill it and run the End-to-End Verification Contract at the
end, then report the phrase "I have verified this completely end to end."

## Goal

Give the merchant the headline funnel from the original feature:

`INR at risk -> expected recoverable -> already recovered -> remaining opportunity`

Concretely, surface:

- `at_risk_paise` - total outstanding that the engine can still act on
  (already exists as part of analytics).
- `expected_recoverable_paise` - a deterministic estimate of what the current
  open pipeline should yield, derived from historical recovery rates per bucket
  (rail, category, customer risk tier), not an LLM guess and not a single flat
  percentage.
- `recovered_paise` - already exists (`net_recovered_value_paise`).
- `remaining_opportunity_paise` - `expected_recoverable - recovered` over the
  current open pipeline; this is the honest, defensible "money left to get."
- `expected_recovery_rate` and a confidence band so the merchant sees it is an
  estimate, not a promise.

## Design

### 1. Deterministic conversion model

Compute expected recoverable as:

```
expected_recoverable_paise =
  sum over open cases of (amount_paise * expected_probability(case))
```

where `expected_probability(case)` is derived from deterministic historical
rates segmented by the same dimensions the engine already reports on:
- by `payment_rail` (from `rail_performance`),
- by `FailureCategory` (from `category_distribution`),
- by customer risk tier once the Customer Recovery Profile lands (#15).

Use segment size to guard small samples: a segment with too few observations
falls back to the overall rate rather than an unstable local rate. All money in
integer paise (`Decimal` / int), never float. This must reuse existing aggregate
helpers so the estimate and the reported actuals come from one source of truth,
not two copies of the math.

### 2. Interaction with the live arm counterfactual

Because there is a 10% holdout arm, the merchant-facing funnel should clearly
distinguish "fleet gross opportunity" from "incremental opportunity attributable
to FORTX." Expose both:
- gross `expected_recoverable` over the whole open pool,
- and the counterfactual-aware `attributable_remaining` that accounts for the
  holdout baseline (reuse `attributable_lift_pct` already computed). The
  spec must not present naive gross recovery as "your additional revenue"; the
  holdout math already exists, reuse it.

### 3. API

Extend the analytics response (or add a companion endpoint) with a
`RecoveryForecast` block: `expected_recoverable_paise`,
`remaining_opportunity_paise`, `expected_recovery_rate_pct`,
`attributable_remaining_paise`, and a small `confidence_window_pct` and segment
detail (per rail/category expected + weight), so the UI can show where the
remaining opportunity lives. Keep it a server-computed read result; do not move
the math into the frontend and do not hardcode any estimate.

### 4. UI

On the merchant overview, replace any flat "recovery rate" hero with the funnel:
At Risk -> Expected Recoverable -> Already Recovered -> Remaining Opportunity.
All four numbers come from the API. Clearly label expected-recoverable as an
estimate (include the confidence band) so it is not mistaken for a guarantee, and
show the attributable (vs holdout) figure where the merchant cares about
incremental recovery.

## End-to-End Verification Contract

1. Seed a mix of open cases across at least two rails/categories and confirm the
   forecast endpoint returns an `expected_recoverable_paise` within a
   deterministic range of the historical per-segment rates, a non-negative
   `remaining_opportunity_paise`, and that the funnel arithmetic holds:
   `remaining = expected - recovered` over the same population with no negative
   or float artifacts.
2. Confirm the estimate updates when the underlying case mix or segment rates
   change, and that small segments fall back to the overall rate (add a unit
   test).
3. Confirm the attributable figure is derived from the holdout/counterfactual
   math and is distinct from the gross figure.
4. Confirm the UI renders all four funnel numbers from the API (no hardcoded
   values) with the confidence band and the attributable callout.
5. Run the full test suite and `make check` green, including integer-paise
   assertions on the funnel arithmetic.

Report: state which of these you have verified completely end to end.
