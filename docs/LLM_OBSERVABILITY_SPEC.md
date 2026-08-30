# LLM Observability Spec - Per-Decision Model Identity, Model-wise Stats, and Model Experimentation

Status: Spec only, researcher-verified against current code. Nothing here is
implemented. An implementer must fulfill it and run the End-to-End Verification
Contract at the end. Superseded by the working implementation in
`backend/src/app/llm/client.py`: per-decision model identity (provider, version,
fallback, config snapshot, tokens, cost, latency), telemetry recorded to the
`model_telemetry` table, and model experimentation tags. Kept as the design
record; verified by `backend/tests/test_llm_observability.py`.

## Verified current problems

1. **The reasoning feed omits provider and identity per log.** Each entry in
   the "Audited Agent Reasoning Feed" (AgentView.tsx) shows a model badge
   derived from `entry.model_metadata?.model`, but `model_metadata` built in
   planner.py:139-146 captures only `model`, tokens, cost, call_id,
   latency_ms. There is **no provider, no model version, no fallback flag, no
   config snapshot, no experiment tag**. `AgentView.tsx:78-79` shows the
   *current* active model / provider from `status.llm_engine`, so a reader
   cannot tell which provider/version actually made a given decision.
2. **The provider is guessed, not recorded.** In `client.py:135,150` the
   custom-model path records `provider="custom_model"` (a literal, not the
   real channel), and `settings.py:188-190` guesses provider from the model
   string (`openrouter` if it contains `/`, else `direct`). History is
   therefore attributed by inference, which is exactly wrong when a user
   changes the model mid-stream.
3. **Changing the model mid-stream corrupts the story.** The report and the
   top cards show the *current* configuration, not the configuration that
   made each decision. Because config identity is not snapshotted per
   decision, switching from Claude to GPT-4o (or reordering providers) makes
   old entries indistinguishable in UI from new ones, and the aggregate
   report cannot say "this cohort was diagnosed by model X with latency Y."
4. **The telemetry table is bypassed for reporting.** `LLMReportResponse`
   (`settings.py:143-215`) is built by re-reading `case.audit_trail` entries
   and re-deriving stats in the request handler - it does *not* query the
   `model_telemetry` table, and only includes cases that `repo.list_cases`
   returns. The table exists but reporting is cobbled on top of audit rows.
5. **No experimentation harness.** There is no way to run model A against
   model B on a controlled cohort, tag runs, and compare accuracy / latency /
   cost / recovery. The fleet simulator in DATA_PIPELINE_SPEC can emit events;
   there is no model-cohort arm.

## Required behavior

### A. Per-decision model identity (the core fix)

Every audited reason entry (and every `model_telemetry` row) must carry an
immutable snapshot of exactly how that decision was made:

- `model` - the actual model string returned by the provider.
- `provider` - the provider that served the call (openrouter, anthropic,
  openai, custom, or `deterministic` for rule fallback) - **recorded, never
  guessed**.
- `version` - provider/model version tag if available, else the model string.
- `input_tokens`, `output_tokens`, `cost_usd` (USD stays explicit), `latency_ms`.
- `call_id`, `used_fallback` (bool), `fallback_reason` (why the fallback
  path ran), `experiment_tag` (nullable).
- `config_snapshot` - a small immutable sketch of the provider fallback
  order and enabled providers at call time, so a reader can see "this was
  decided while the order was [A, B]."

This snapshot is written at decision time and never mutated. The reasoning
feed must render provider + model + version + latency + cost per entry, and
must show a `deterministic` tag (not a blank model) for the deterministic
fallback path.

### B. Honest model switching

- The "Active Reasoning Model" / provider cards show the *current* config and
  are explicitly labeled "current active model" so nobody reads them as
  historical truth.
- The per-entry badge shows the *recorded* snapshot, so a decision made under
  Claude stays labeled Claude even after the operator switches to GPT-4o.
- The report breaks history down by recorded model+provider, so switching
  mid-stream produces groups like "Claude (23 calls)", "GPT-4o (9 calls)"
  rather than a merged blob attributed to the current model.
- Runtime `PUT /settings/llm-config` continues to work, but must stamp the
  config change into a mode/audit event as well.

### C. Model-wise stats from the telemetry table (single source of truth)

Rebuild `GET /settings/llm-report` to aggregate the `model_telemetry` table:

- Per (provider, model): call_count, success_count, fallback_count,
  avg/p50/p95 latency_ms, total input/output tokens, total cost_usd,
  last_call_at.
- Overall totals across all calls.
- The frontend telemetry section (SettingsView) renders exactly these
  numbers; there are no client-side derivations or hardcoded figures.
- Keep listing against `model_telemetry`, not by walking case audit trails.
  If `repo.list_cases` is still the data path, change it so telemetry
  queries the table directly.

### D. Model experimentation

- The fleet simulator and the ingestion path accept an optional
  `experiment_tag` (e.g. "claude-vs-gpt4o-run1") and, when set, attach it to
  every decision it drives.
- An experiment endpoint `GET /api/experiments` lists
  `{experiment_tag, model, call_count, avg_latency_ms, total_cost_usd,
  recovery_rate, failed_count, cohort_size}` so the operator can compare two
  models on one cohort.
- Choosing the model for an experiment: allow an explicit `model` override
  on the fleet/simulation request (planner already accepts a `model` kwarg -
  wire it through), and record `experiment_tag` into both the audit entry and
  the telemetry row.
- Holdout arm integrity must be preserved: the 10% control never receives
  interventions regardless of experiment, so recovery lift per model is
  still measured against the untouched baseline.

## End-to-End Verification Contract (MANDATORY)

Run and demonstrate, then report "I have verified this completely end to end":

1. Seed a cohort with `experiment_tag` and explicit model override; confirm
   every reasoning-feed entry shows provider + model + latency + cost and a
   deterministic tag where applicable.
2. With real LLM keys configured, run one cohort under model A, then switch
   the active model and run another under model B. Confirm the feed and the
   report keep the entries correctly attributed (A stays A, B stays B) and
   the "current active model" card is labeled as current.
3. Confirm `GET /settings/llm-report` returns table-derived numbers matching
   rows in `model_telemetry`, with success/fallback counts and percentiles
   populated - not zero and not guessed.
4. Confirm the deterministic fallback path (blank/revoked key) is audited as
   `provider=deterministic` with `used_fallback=true` and `fallback_reason`
   set.
5. Run a two-model experiment on one cohort; show the comparison table from
   `/api/experiments` with recovery_rate, latency, and cost per model, and
   confirm the holdout arm received no interventions.
6. Confirm no non-ASCII characters and no hardcoded model names/providers in
   the new UI code; all labels source from the API.
7. `make check` green.