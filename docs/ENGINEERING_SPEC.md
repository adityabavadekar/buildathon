# Production-Grade Engineering Implementation Spec

Spec for moving the revenue-recovery engine from a synchronous single-process
monolith to an asynchronous, durable, crash-recoverable distributed system, and
for adding the GenAI-forward pieces. This is the build contract for the coding
agent, written to intern-hiring engineering standards.

This is a long-horizon build. It is documented so it can be executed in
coherent, independently-verifiable phases. The goal is real engineering, not
surface area: every claim in this spec must be backed by running code, a durable
store, and a test.

Read `docs/SOLUTION.md` for the original architecture intent and the tech-stack
rationale table. This spec refines that intent with one deliberate change: the
event backbone is **Redis Streams, not Kafka**. Kafka is correct at true
multi-datacenter scale but is overkill here; Redis Streams gives durable,
consumer-grouped, replayable streams with far less operational weight, and it is
still a production-grade primitive.

## 0. What exists today and what it is missing

Current state (verified against code):

- Synchronous monolith. `api/routes/webhooks.py:166` calls
  `process_failure_event`, which runs diagnosis + plan + policy + tool execution
  all inline in the webhook HTTP request. The LLM call latency is borne by that
  request.
- No worker, no queue, no scheduler, no timer. `active_recovery_queue` in
  `api/routes/simulation.py:128` is a computed count of cases in active states,
  not a real queue with consumers. "RETRY_SCHEDULED" and "OUTREACH_PENDING" are
  set as states but nothing ever wakes later to execute them; resolution is
  fabricated eagerly by `simulation/seeder.py`.
- State is held in a JSON-file repository (`audit/repository.py`) with a thread
  lock. Not ACID, no crash-recovery resume, not multi-process safe.
- LLM is a single call in `llm/planner.py` that returns a JSON plan; the
  orchestrator falls back to a deterministic classifier on failure or low
  confidence. That fallback is the one genuine resilience path.
- Frontend polls the full dataset every 10s (`app/page.tsx:76`); there is no
  streaming, no per-case incremental updates, no progress surfaced.

The gap to close: an **asynchronous, durable, resumable** recovery workflow with
real scheduled execution, real progress tracking, crash and dependency-outage
handling, and GenAI depth.

## 1. Architecture target

```
	                          +-------------------------------------------+
   Razorpay/PG                |                  Ingress                 |
   webhook ------------------>|  FastAPI /webhooks/razorpay             |
	                          |  - HMAC verify (fast, atomic)           |
	                          |  - idempotency check                    |
	                          |  - write event -> Redis Stream (XADD)   |
	                          |  - reply 202 ACCEPTED immediately       |
	                          +------------------+----------------------+
	                                             | Redis Streams (durable, replayable)
	                                             v
	                          +-------------------------------------------+
	                          |   Sync Worker (Redis consumer group)     |
	                          |  - claim case, lock, transition to AT    |
	                          |  - diagnose (LLM or deterministic fb)    |
	                          |  - policy gate                           |
	                          |  - schedule due job -> job table (due)   |
	                          |  - ack (XACK) after durable commit       |
	                          +------------------+----------------------+
	                                             | reads due jobs
	                                             v
	                          +-------------------------------------------+
	                          |   Delayed/Retry Worker                   |
	                          |  - SELECT due jobs (SKIP LOCKED)         |
	                          |  - execute touch (link / mandate / nudge)|
	                          |    with idempotency + circuit breaker   |
	                          |  - transition state, schedule next, log  |
	                          +------------------+----------------------+
	                                             |
	                                             v
	                          +-------------------------------------------+
	                          |   PostgreSQL (ACID source of truth)      |
	                          |  cases, audit (append-only), jobs,       |
	                          |  policies, model_telemetry               |
	                          +------------------+----------------------+
	                                             |
			    SSE stream of case/audit state changes
	                                             v
	                          +-------------------------------------------+
	                          |   Next.js operator UI (SSE-subscribed)   |
	                          +-------------------------------------------+
```

Key properties:

- Webhook ingress is **fast and idempotent**: HMAC-verify, dedupe, then enqueue
  and return `202 Accepted` immediately. No LLM or tool work in the request
  path. This is the "low latency, non-blocking checkout/subscription loop"
  requirement from `SOLUTION.md`.
- All state transitions and financial actions are **durable and resumable**.
- The system degrades gracefully if Razorpay, the LLM, or Redis is down.
- The UI is **realtime via Server-Sent Events**, with true per-case progress.

## 2. Data layer: PostgreSQL as the durable source of truth

Replace the JSON-file repository with PostgreSQL (or, at minimum, a SQLite
backend that matches the same interface for local-only runs). The
`CaseRepository` interface stays as the seam - the provider swaps underneath.

Required tables and invariants (all money in paise integer minor units, all
timestamps timezone-aware UTC):

- `cases`: id (uuid pk), merchant_id, payment_id (unique), case_id, arm, state,
  amount_paise, currency, touches_count, discount_paise_granted,
  total_cost_paise, net_recovered_value_paise, created_at, updated_at,
  due_at (nullable), version (for optimistic locking).
- `audit` (append-only, immutable): entry_id pk, case_id, event_name, actor,
  from_state, to_state, reason, decision_inputs jsonb, model_metadata jsonb,
  cost_paise, created_at. Never updated or deleted; PK is monotonic so the UI
  can stream new rows via position.
- `jobs` (scheduled work): id, case_id fk, job_type (RETRY / OUTREACH /
  CAPTURE_CHECK / P2P_WAKE), due_at, status (PENDING / RUNNING / DONE / FAILED /
  CANCELLED), idempotency_key unique, attempts, next_run_at, payload jsonb,
  created_at. Index on (status, due_at).
- `model_telemetry`: id, model, provider, input_tokens, output_tokens,
  cost_usd, latency_ms, success, used_fallback, case_id nullable, created_at.
  This powers the model-wise breakdown, tokens, cost, and latency reporting.

Concurrency rules:

- Use `SELECT ... FOR UPDATE SKIP LOCKED` when a worker claims a due job, so
  multiple workers never execute the same financial action.
- Every `cases` row update carries `version`; a write that sees a stale version
  is rejected (optimistic lock), surfacing a concurrent-edit conflict the worker
  must handle.
- Audit rows are written in the same transaction as the state transition that
  produced them (audit-before-action is preserved).

## 3. Event backbone: Redis Streams

Use Redis Streams (Redis 5.0+) as the durable event backbone.

- `XADD events * <json>` on webhook ingress. The stream is the durable inbox and
  the replay source.
- A consumer group `synccg` with `XGROUP CREATE events synccg 0` so multiple
  sync-worker replicas can process in parallel with per-message `XACK`.
- On worker crash, unacked messages remain in the group and are redelivered
  (at-least-once). Idempotency keys make redelivery safe (no double-charge).
- Pending-entry list (`XPENDING`) lets a supervisor requeue stuck messages after
  a visibility timeout.
- Stream retention can be trimmed (`XTRIM`) after durable commit to PostgreSQL;
  the audit table remains the permanent record. Do not trim before commit.

Dependency: Redis must be available. For the error case "Redis down", the
ingress route falls back to writing the event directly to the `events` table in
PostgreSQL and the worker reads from there, so a Redis outage does not lose
events (details in the outage section).

## 4. Worker component

A single long-running worker process (or N replicas) in
`backend/src/app/worker/`, started separately from the API (for example a
`make worker` target). Two responsibilities in one loop, or two cooperative
loops:

1. **Sync consumer**: reads the `events` Redis stream group, claims each event,
   runs [diagnose + plan + gate], schedules a `due_at` job, commits the case +
   audit + job in one transaction, then `XACK`.
2. **Due-job executor**: polls the `jobs` table for `(status=PENDING AND
   due_at <= now)`, claims with `FOR UPDATE SKIP LOCKED`, executes the touch with
   idempotency + timeout + circuit breaker, transitions state, schedules the next
   `due_at` (or escalates/terminates), audits, releases the lock.

The worker is the thing that makes "RETRY_SCHEDULED after +24h" real: the state
is set, a `due_at = now + cooldown` job is written, and the worker wakes it when
the time arrives. This is the trigger/execution answer to the reviewer question:
"when does execution happen? who configures it?" - the policy rules configure
the cooldowns (config/code), and the worker executes at `due_at`.

Worker lifecycle and crash recovery:

- The worker uses the async driver (`asyncpg`/SQLAlchemy async) so it never
  blocks the API event loop; the worker is its own process, so the API and
  worker scale independently.
- A job in `RUNNING` state whose worker died is reclaimed: on startup and
  periodically, jobs stuck in `RUNNING` older than a visibility timeout are
  reset to `PENDING` with `attempts += 1` and a bounded retry counter.
- Exactly-once is approximated at the application level via idempotency keys
  plus row locks: the financial action (payment link / mandate / notify) carries
  an idempotency key, and the `jobs` table enforces uniqueness on it.

## 5. Trigger, config, and who decides when

- **Trigger**: a webhook (`payment.failed`, `subscription.halted`) is the only
  trigger. It enqueues to Redis and returns `202`. Nothing else starts a case.
- **Next-action**: the diagnosis/policy output sets `due_at` on a job.
  Constants for cooldowns (24h default), touch cap (3), discount cap now live in
  `core/constants.py` and are read from `Settings`/policy config; the worker
  reads the same constants so there is one source of truth.
- **Config source**: cooldowns, caps, holdout ratio, and per-provider model
  selection become **configurable** (see section 7). For now the config lives in
  `core/config.py` + policy constants; a future admin API can mutate them, but
  the worker must always re-read the current value, never a cached copy, so a
  mid-run policy change is respected on the next claim.

## 6. Progress tracking and realtime UI

The UI's "workflow progress: current state, next action, waiting period,
attempts, expected completion" (from `SOLUTION.md`) becomes real:

- Each case exposes: state, `due_at` (next scheduled action), `next_action`
  (job type), touches count/cap, attempts, and last-updated. These are already
  latent in the state machine; the missing part is `due_at` + `next_action`,
  which the job scheduling introduces.
- The case detail drawer and recovery table render a **live countdown/timer**
  until the next `due_at`, not a static state label.
- **SSE** (`application/x-ndjson` or `text/event-stream`) substitutes the 10s
  full poll (`page.tsx:76`). The backend pushes each `audit` append and state
  change for subscribed cases / a global feed. Rationale for SSE over Websockets
  (documented in `SOLUTION.md`): one-way push, HTTP-friendly, simpler ops, and
  automatic reconnection. Use `Last-Event-ID` on reconnect to resume from the
  last audit position.
- Frontend keeps `lib/api.ts` as the single call surface; add an SSE client in
  `lib/sse.ts`. Do not hardcode timers as the primary sync mechanism.

## 7. LLM and GenAI depth

Move beyond "LLM outputs one JSON plan" to a bounded, multi-step agent flow so
the GenAI requirement is substantive and defensible:

- **Tool-calling diagnosis**: the LLM can call bounded tools in a loop - for
  example `lookup_customer_history(customer_id)`, `check_issuer_status(code)`,
  `check_policy(proposed_discount)`, `propose_plan()`. Wrap in LangGraph (or a
  hand-rolled guarded loop) with a hard node count cap, so it cannot loop
  unboundedly. Every tool call is audit-logged.
- **Provider routing with fallback** (interoperable with LiteLLM): route to
  openrouter -> anthropic -> openai by configured order, with the deterministic
  NPCI/Razorpay classifier as the guaranteed final fallback. The order and set
  of enabled providers must be configurable (not the hardcoded chain in
  `llm/client.py:80`).
- **Model telemetry**: capture per call `latency_ms` (currently missing from
  `LLMResponse`/`model_metadata`), plus the already-captured input/output tokens
  and `cost_usd`, into `model_telemetry`. Add a model-wise report: per
  provider/model - call count, tokens in/out, mean and p95 latency, cost, and
  fallback rate. Display as a new view fed by a `/report/models` endpoint.
- **GenAI-forward directions** (Bonuses, add after core is durable):
  - Promise-to-pay: parse a customer's free-text reply with the LLM to extract a
    promised date, create a `P2P_WAITING` job with `due_at = promised_date`, and
    hold dunning until then. This gives `P2P_WAITING`/`P2P_PROMISED` real
    behavior (currently dead enum states).
  - Checkout-abandonment funnel: ingest a distinct abandoned-cart event (not just
    a `CHECKOUT_DROP_OFF` payment-failure category) and run an incentivized-link
    recovery.
  - Voice: Hinglish voice outreach (documented in `SOLUTION.md` differentiators).

## 8. Outage and failure handling (the reviewer's exact questions)

Addressed as first-class behavior, not afterthoughts:

**System goes down mid-reconciliation:**
- All state is durable in PostgreSQL; in-flight work is a `RUNNING` job that the
  worker reclaims after a visibility timeout and retries (bounded).
- A webhook that arrived but was not consumed is still in the Redis stream
  (unacked, pending), redelivered after the worker recovers. At-least-once +
  idempotency = no double-charge, no lost event.
- Redis Streams retention is not trimmed until the event is committed to
  PostgreSQL (see section 3).

**Razorpay goes down:**
- Tool execution wraps calls in a timeout. On failure the tool returns
  `success=False` (as it does today), but now the orchestrator schedules a
  **retry job with exponential backoff** (for example +5m, +15m, +1h capped)
  rather than giving up or silently simulating.
- A **circuit breaker** around Razorpay: after N consecutive failures in a
  window, open the circuit, pause Razorpay-dependant jobs, surface
  `GATEWAY_CIRCUIT_OPEN` in system status, and resume later (half-open probe).
- This must be tested by a chaos test that stops the mock gateway mid-batch and
  asserts the batch resumes and completes without duplicates.

**LLM goes down:**
- Already handled: deterministic fallback in `planner.py`. Formalize it: when the
  configured LLM providers all fail or time out, the planner returns a
  deterministic plan and records `used_fallback=True` in `model_metadata` /
  `model_telemetry`, so the UI shows which cases were LLM-routed vs fallback. No
  graceful-degradation gap here, but make the fallback path explicit and tested.

**Redis goes down:**
- Ingress falls back to writing the event into a PostgreSQL `inbox_events` table;
  the worker reads from the inbox when the stream is unavailable. Events are
  never lost on a Redis failure. On recovery, drain both.

## 9. Testing strategy (engineering credibility)

The bar for this build is tests that prove the hard properties, not just happy
path:

- **Idempotency**: deliver the same webhook twice (duplicate + replayed after
  crash) -> exactly one case, zero double financial actions.
- **Crash recovery**: kill the worker mid-`RUNNING` job -> job reclaimed and
  re-executed once the worker restarts, no duplicate charge.
- **Scheduling timing**: job with `due_at` in the future is not executed early;
  a job whose `due_at` passes is executed.
- **Chaos / outage**: stop the mock Razorpay and the LLM mid-batch; assert the
  batch eventually completes with correct NRV and no duplicates.
- **Counterfactual integrity**: holdout cases are never touched by any worker,
  and the measured lift is computed over the completed batch.
- **Backfill/ordering**: events redelivered out of order are deduped by
  idempotency key.
- Keep existing tests green; add the ones above. Run `make check` to green.

## 10. Dependencies and local run

- PostgreSQL (or SQLite fallback behind the same repository interface) for state.
- Redis with Streams support for the event backbone, jobs-guarantee, and
  idempotency locks.
- `httpx2` for outbound (already in use). Use the async SQLAlchemy/asyncpg
  driver for the worker.
- A `Makefile` target `worker` to run the worker process; keep the API worker-
  free so they scale separately.
- Docker compose for Postgres + Redis so a reviewer can stand it up with one
  command (and document it in `docs/` and the README).
- Keep `.env.example` updated with new keys (Redis URL, DB URL). Never commit
  `.env`.

## 11. Execution phases (each independently verifiable)

1. **Phase A - Durability**: swap JSON repo for PostgreSQL behind the same
   interface; add `jobs` + `audit` + `model_telemetry` tables and migrations.
   Tests: persistence + idempotency.
2. **Phase B - Async ingest**: webhook returns 202 after enqueueing to Redis;
   add the sync worker + consumer group. Tests: 202-before-work, redelivery,
   dedupe.
3. **Phase C - Scheduling**: `due_at` jobs + due-job worker + `SKIP LOCKED` +
   reclaim. Tests: timing, crash-recovery, concurrent workers.
4. **Phase D - Realtime + config**: SSE replaces the 10s poll; progress
   (due_at/next_action/countdown) surfaced; provider routing made configurable.
5. **Phase E - Resilience**: circuit breakers, backoff retries, Redis fallback
   inbox, chaos tests.
6. **Phase F - GenAI tool-calling + telemetry report**: LangGraph guarded loop,
   model latency/cost report, then optional P2P / checkout funnel / voice.

The first four phases are the highest-credibility wins and should be done before
the optional directions.

## 12. Decisions to record

Append to `docs/DECISIONS.md` as each phase lands, especially: the swap of
Kafka -> Redis Streams, the PostgreSQL repository swap, the worker/API process
split, and the SSE choice. Add config as `Settings` fields in `core/config.py`.
Keep every money path idempotent and audit-before-action, per AGENTS.md.
