# Project Review, Gap Analysis, and UI/Model Spec

One consolidated record of three review passes, all grounded in verified code
state, plus implementation specs for the coding agent. Read order:

1. Track coverage vs. the buildathon brief (what is real, what is scaffold).
2. Live Razorpay test-mode reality (why interventions simulate).
3. Frontend experience gaps and the model-provider/settings improvements.

Every claim below traces to a file or a live API result. Anything a developer
cannot source from the code is flagged as a question, not asserted.

---

## 1. Track coverage: the bar and the example directions

### The bar (the mandatory core)

The brief's bar is: do not just identify the problem. Show measured money
recovered across a batch, with compliant escalation, stopping rules, and an
audit trail. Verified against code:

| Requirement | Status | Evidence |
| --- | --- | --- |
| Detect revenue at risk | Met | `api/routes/webhooks.py` ingests `payment.failed`, `subscription.halted`, `payment.captured`. |
| Diagnose root cause | Met | `detection/classifier.py` (NPCI/Razorpay taxonomy), `llm/planner.py`, `FailureCategory` enum. |
| Choose bounded intervention | Met | `intervention/` tools: payment link, mandate retry, notification (dunning), orchestrator, policy gate. |
| Measured money across a batch | Met | `simulation/seeder.py` seeds 50-case batches; analytics summary with NRV, recovery rate, channel/rail performance. |
| Counterfactual / holdout arm | Met | `ExperimentArm.TREATMENT/HOLDOUT_CONTROL`, `policies.holdout_percentage`, analytics lift (treatment vs holdout). |
| Compliant escalation | Met | `ESCALATED` state, `MANUAL_ESCALATION` intervention, human approve in Recovery view and case drawer. |
| Stopping rules | Met | Policy gate (max 3 touches, cooldown, discount margin cap) and terminal states `RECOVERED`/`ABANDONED`/`WRITTEN_OFF`. |
| Audit trail | Met | Immutable `audit/` trail; `AuditActor`; state machine logs before action; Audit view and drawer timeline. |

The mandatory bar is fully met. Backend tests confirm (`48 passed`,
`testpaths` under `backend/tests`).

### The example directions (illustrative list; we cover some)

| Direction | Status | Notes |
| --- | --- | --- |
| Payment degradation -> root cause -> recovery | Met | Full pipeline. |
| Failed-subscription recovery | Met | `subscription.halted` webhook + `MandateRetryTool`. |
| Mandate retry sequencer | Met | `RETRY_SCHEDULED` state + mandate tool with cooldown. |
| Checkout drop-off recovery | Partial | `FailureCategory.CHECKOUT_DROP_OFF` + `INCENTIVIZED_LINK`, but modeled as a payment-failure category only. No abandoned-cart/cart-abandonment funnel or abandoned-checkout ingestion. |
| Hinglish voice recovery | Partial | Planner generates dunning copy (English + Hinglish) and `VOICE_CALL` channel exists, but no voice provider dispatch (falls back to simulation). Hinglish is copy-language, not a placed voice call. |
| B2B receivables chaser | Not built | Only a seeder string "Net-30 B2B invoice past due date" (`simulation/seeder.py:78`). No receivables ingestion, overdue tracking, or overdue-dunning pipeline. |
| Promise-to-pay tracker | Not built | `P2P_WAITING`/`P2P_PROMISED` exist in `core/enums.py` and `audit/state_machine.py`, but nothing creates or continues them. No tool, no seeder, no orchestrator path maps to them. |

Bottom line: the core bar is demoable and real. The three honest gaps are the
partial checkout-abandonment funnel and the absent receivables and promise-to-pay
paths. P2P and receivables are represented by enum states and a seeder string,
not shipped features.

---

## 2. Live Razorpay test-mode reality (why interventions simulate)

Probed the real test-mode API with the configured `.env` credentials (via the
Razorpay CLI, v1.0.9) and via direct HTTP.

Live results:

```
OK    Orders (create)      real order returned (e.g. order_TW0rxFyxg7zjoT, INR 500)
OK    Customers (list)     real, empty
OK    Refunds (list)       real
WARN  Payment Links        HTTP 429 "test mode limit of 30 reached for payment_link"
WARN  Subscriptions        HTTP 401 (feature not enabled on test account)
```

Root cause of "everything simulates":

- Credentials are real and the API is reachable. `GET /v1/orders` returns real
  data, so the auth path works.
- The test account has exhausted Razorpay's test-mode cap of 30 payment links.
  The exact response: `RATE_LIMIT_EXCEEDED, test mode limit of 30 reached for
  payment_link`.
- On that 429, `intervention/tools/payment_link.py` (the non-production branch)
  fabricates a link and marks it `sandbox_simulated=True`. That is correct
  graceful fallback, not a stub pretending.
- Subscriptions return 401 because the test account does not have the
  Subscriptions/emandates feature enabled, so `MandateRetryTool` falls back to
  simulation.
- Notification has no `NOTIFICATION_WEBHOOK_URL`/`WHATSAPP_API_TOKEN` set, so
  `CustomerNotificationTool` falls back to simulation.

Implication for the demo: to show a real payment link, use a fresh test account
(or wait for quota reset) and re-run the existing code unchanged. To show real
mandate work, enable the Subscriptions feature on the test account. To show real
WhatsApp dispatch, provide a provider webhook/token. Tooling already added:
`scripts/live-razorpay-check.sh` probes all relevant endpoints and distinguishes
live success from quota/feature-blocked.

---

## 3. Frontend experience gaps and model-provider settings

### 3.1 UI/styling asks (from review)

- More colour overall. Current palette is deliberately near-neutral slate with a
  single teal accent. Add restrained, semantic colour (already partially present
  via lifecycle badges, but cards/labels read monochrome).
- Text is too small. Current body copy is overwhelmingly `text-xs` and
  `text-[11px]`. Raise the floor: tables can stay dense, but section intros,
  card titles, and metric values need a larger default (for example `text-sm`
  body, larger metric figures).
- Selected section does not take full available space. The active nav item and
  main content area should expand to the available width. Verify the `max-w-6xl`
  wrapper (`app/page.tsx:136`) and the 64-column sidebar against the target
  layout.
- Show Razorpay account info: merchant id and related account details, not just
  a masked key id. Where the backend exposes account/merchant data it should be
  surfaced on the Settings/Status pages (see 3.3 re what is real vs. what would
  be a new fetch).

### 3.2 Filled coloured icons for stats and large numbers

- Replace the current mostly outline/lucide icon treatment on stat cards with
  filled, colour-coded icons that track the semantic status tokens already in
  `frontend/src/app/globals.css` (`recovered`, `pending`, `failed`,
  `escalated`).
- Make the primary metric numbers larger and stronger (see 3.1 text-size). Keep
  the `font-mono`/`money` right-aligned figures; just increase the displayed
  size and weight on key figures.

### 3.3 Model provider fallback settings (the main functional gap)

Current state (verified):

- Model selection and provider fallback order are **hardcoded** in
  `llm/client.py` `complete()`: `openrouter -> anthropic -> openai -> default`,
  and in `api/routes/settings.py` `primary_llm_provider` the same fixed order.
- `configured_providers()` returns which API keys are present, sorted
  alphabetically. It does not reflect any user-set preference or order.
- Settings are read-only. `SystemSettingsResponse` exposes
  `primary_llm_provider`, `active_llm_model`, `configured_llm_providers`, and
  `deterministic_fallback_active`, but there is no endpoint to enable/disable a
  provider, re-order fallback, or change the active model. The UI
  (`SettingsView.tsx`) renders these as `readOnly` inputs.
- `LLMResponse` and audit `model_metadata` already capture model,
  input_tokens, output_tokens, cost_usd, and call_id. Verified in
  `llm/client.py` and `intervention/orchestrator.py:170`. Latency/duration is
  NOT captured.
- The Audit/Agent UIs already show model, token counts, and cost_usd where
  model_metadata exists. There is no model-wise rollup, no latency breakdown,
  and no full report endpoint.

The brief for the coding agent (spec, not yet implemented):

1. Provider management settings surfaced in the UI:
   - Enable/disable each provider (openrouter, anthropic, openai, deterministic
     fallback).
   - Reorder the fallback chain (which provider is tried first when the primary
     is down or unset).
   - Change the active model per provider (for example pick a model name per
     provider, not just the single hardcoded `openrouter_model`).
   - These must persist (config or a dedicated settings store), not reset on
     restart, and must drive `llm/client.py` selection instead of the hardcoded
     order.
2. Telemetry and reporting:
   - Capture per-call latency/duration in `LLMResponse` and persist it in
     `model_metadata` (currently missing).
   - Add a model-wise breakdown endpoint (per model: call count, tokens in/out,
     cost, mean/p95 latency, success vs fallback). Feed a new UI panel.
   - Add a "full report" view: tokens used and the cost borne by those tokens
     per provider/model, over a date range, drawn from the audit trail (which
     already stores model_metadata).
   - Keep all money in paise / cents with explicit currency and keep cost_usd
     as the nominal provider cost; convert to INR only for display with an
     explicit rate note.
3. Rules:
   - Never hardcode a provider list, model list, or order in the frontend.
     Everything (available providers, models, active selection, order) must come
     from the backend settings API.
   - Keep the deterministic fallback (`NPCI & Razorpay Rule Classifier`) as the
     guaranteed offline path; UI controls should treat it as a provider that can
     be toggled/ordered but not removed.

---

## 4. Cross-cutting review rules (apply to all UI work)

- No hardcoding of metrics, percentages, provider lists, model names, or URLs in
  the frontend. Each value comes from the API or a shared constants module.
- Shared helpers live in `frontend/src/lib/` (`api.ts`, plus a glossary module).
- Design tokens live in `frontend/src/app/globals.css` under `@theme`. Do not
  add a `tailwind.config.js`.
- ASCII only in code, comments, config, and docs (no em-dashes, arrows, or
  smart quotes).
- Every helper-text sentence must source to real backend behavior or be cut.
- Run `make check` (backend lint/typecheck/tests + frontend lint/typecheck/
  build) to green before calling a UI change done.

---

## 5. Questions to resolve before implementation

- Is the goal to keep the single-account view (show one Razorpay merchant) or
  to support per-merchant account selection? Current code is single-account.
  The "show merchant account info" ask depends on this.
- Should provider enable/disable/order persist to disk (like the audit
  repository does once for cases) or be env-driven? Recommendation: persist so
  runtime changes survive restart, and document the chosen store in
  `DECISIONS.md`.
- For model-wise cost reporting, is nominal `cost_usd` from litellm acceptable,
  or is a client-side INR conversion with an explicit FX rate required? This
  needs a decision because AGENTS.md forbids implicit INR conversion.
