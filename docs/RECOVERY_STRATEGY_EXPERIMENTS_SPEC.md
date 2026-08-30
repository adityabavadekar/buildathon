# Recovery Strategy Experiments Spec

Status: Spec only. Researcher-verified against the current code. The existing
`/api/experiments` endpoint and `get_experiments_report()` in
`audit/sqlite_store.py` aggregate **model** cohorts by `experiment_tag` +
`model` (the LLM model experimentation harness from LLM_OBSERVABILITY). What is
missing is the merchant-facing **recovery strategy** experiment: comparing
separate intervention strategies end to end (e.g. "retry -> reminder" vs
"payment link -> reminder") and measuring which recovers more incremental
rupees. Nothing in this doc is implemented. An implementer must fulfill it and
run the End-to-End Verification Contract at the end, then report the phrase "I
have verified this completely end to end."

## Goal

Let the operator define two (or more) recovery strategies, assign a slice of new
recovery cases to each, run them, and compare **incremental rupees recovered**
per strategy - not just "which strategy succeeded most." This is feature #12 from
the merchant brief and it intentionally reuses the existing holdout/counterfactual
discipline so "won" means "recovered more than it would have without action," not
"recovered the most gross."

## The two experiment axes (do not conflate)

- **Model experiments** (already implemented): vary the LLM *model* per
  `experiment_tag`; compare recovery rate, latency, cost. Aggregated in
  `get_experiments_report()`.
- **Strategy experiments** (this spec): vary the *intervention strategy* a case
  follows (sequence of interventions, channels, link vs retry, etc.); compare
  incremental recovered value in a holdout arm. Not implemented.

Both share `experiment_arm` (TREATMENT vs HOLDOUT_CONTROL) already on the case.

## Design

### 1. Strategy definition

Introduce a typed, versioned strategy definition (an enum or a small config
object) that describes a full recovery policy per case, e.g.:
- `RETRY_THEN_REMINDER` - passive/smart retry, then a reminder if unpaid.
- `LINK_THEN_REMINDER` - issue payment link, then a reminder if unpaid.
- `LINK_THEN_INCENTIVE` - link, then a discounted link on the second touch.

This is orthogonal to the single-step `InterventionType`. The planner/orchestrator
currently picks one intervention per touch; a strategy is the instruction for the
whole lifecycle (bounded by the existing policy gate: max touches, cooldowns,
discount caps).

### 2. Assignment

When a case is created, assign it to a strategy. Keep the counterfactual arm:
a case is either in a strategy cohort (TREATMENT) or in HOLDOUT_CONTROL. The
strategy becomes a first-class, indexed column on the case (`strategy_tag`),
deterministically assigned (hash of payment_id, mirroring the existing
`_assign_experiment_arm`), with an explicit override for operator-initiated
experiments. Do not reuse `experiment_tag` (that column is the model axis); add a
separate `strategy_tag`.

### 3. Measurement

Add a strategy comparison report that, per `strategy_tag`:
- counts cohort size and recovered_count,
- sums `recovered_amount_paise` (gross) and `net_recovered_value_paise`,
- computes the **incremental** value against the holdout baseline:
  `incremental_paise = net_recovered(treatment) - baseline_paise` where
  `baseline_paise` is `holdout_recovery_rate * treatment_at_risk`, the same
  counterfactual logic already used for `attributable_lift_pct`.
- reports cost (gateway + outreach + discount) and ROI per strategy.

Present the comparison so the merchant can read which strategy wins on
incremental recovery, not just on gross or on success rate.

### 4. API + UI

Expose `GET /api/experiments/strategies` returning per-strategy metrics
(cohort size, recovered, gross vs net, incremental vs holdout basis, cost, ROI).
Render in a comparison view (e.g. next to the existing model-experiment and
escalation views) that shows the winning strategy on incremental value. All
values come from the API; do not hardcode strategies or percentages in the
frontend. Show cohort sizes and note when a cohort is too small to be conclusive.

### 5. Interaction with the safety bounds

A strategy experiment must still respect the merchant policy (touch caps,
amount caps, discount caps) and the operator autonomy mode. It changes the
*sequence/category* of interventions, never the safety ceiling. An experiment
never disables the holdout arm; removing a comparison without a counterpart is a
bug.

## End-to-End Verification Contract

1. Define at least two strategies and confirm new cases are deterministically
   assigned to one of them (or holdout) with `strategy_tag` persisted and
   indexed.
2. Recover cases under each strategy and confirm the strategy report shows, per
   strategy, gross recovered, net recovered, and an incremental figure computed
   against the holdout baseline - and that a strategy with high gross but high
   cost/discount does not necessarily rank first on incremental value.
3. Confirm the existing model `get_experiments_report()` is unchanged and that
   `experiment_tag` and `strategy_tag` remain independent axes on a case.
4. Confirm the UI renders the strategy comparison from the API (no hardcoded
   values) and flags small cohorts.
5. Confirm no experiment bypasses the policy gate or the holdout arm. Add tests
   for assignment determinism, incremental math (integer paise, non-negative),
   and axis independence. Run the full suite and `make check` green.

Report: state which of these you have verified completely end to end.
