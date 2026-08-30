# Data Pipeline Spec - The Entry Point of Data

Original spec for the entry point of data. Since superseded by the working
implementation recorded in `docs/DECISIONS.md` (Fast 202 ingress, durable FIFO
queue, fleet simulator, pipeline observability). Kept here as the design record;
the End-to-End Verification Contract is exercised by `backend/tests/test_pipeline.py`.

## Why this is the most important thing in the system

A revenue-recovery engine earns trust only if it can absorb a real, continuous,
flooding stream of payment-failure events without dropping or stalling, no
matter which downstream service is down. The web UI is a **view and a remote
control, not a processor**. Nothing in the system may depend on the browser
being open, a button being clicked, or a poll happening. The backend must
ingest, queue, process, and survive on its own.

Currently the UI drives the work: there is only a one-shot "Seed 50 Failures"
button, the webhook runs the whole pipeline inline in the request, and there is
no durable queue observable to anyone. This spec fixes that.

## How events get in (three sources, one pipe)

1. **Real Razorpay webhooks** (`POST /api/webhooks/razorpay`). Verify HMAC
   signature, validate the schema, dedupe by payment_id, then **enqueue and
   return 202 immediately**. No diagnosis, no LLM, no tool call in the request
   path.
2. **Continuous fleet simulator** (new). A backend-owned generator that emits a
   steady stream of synthetic failure events at a configurable rate, exactly as
   if a merchant's fleet were live. Start/stop/pause/rate come from `POST`
   endpoints; the generator itself lives in the backend so it keeps running
   when no browser is connected. This replaces the one-shot seed as the demo's
   primary data source.
3. **Single event POST** (new) for demos and tests: one event at a time through
   the same validation and queue path.

All three enqueue into the same durable inbox and then the same processing
pipeline. There is no side door.

## Durable queue (how events flow with no Redis)

Decide and record: for this scale the durable queue is the SQLite `jobs`
table (already present) used as a strict FIFO, **claimed with
`SELECT ... WHERE status = 'PENDING' AND due_at <= now ORDER BY due_at LIMIT 1`
under a per-row lock, with no Redis required**. Redis Streams stays optional;
if it is ever added it wraps this exact pipeline and the SQLite inbox remains
the fallback. The definition of done does not depend on Redis.

Queue states must be honest and observable:

- `QUEUED` - event accepted, not yet claimed.
- `PROCESSING` - claimed by a worker, job in flight.
- `DONE` - fully processed (diagnosis, plan, gate, intervention scheduled or
  executed, audit written) in one transaction.
- `FAILED` - terminal after bounded retries.
- `DEAD` - poison event that hit the retry cap; visible in the UI, never
  silently dropped.

There is no implicit "active_recovery_queue" count anymore. Every number on a
dashboard comes from counting these states.

## Processing pipeline (worker)

A standalone worker (`make worker`) claims jobs one at a time and runs:

1. Load case, re-check state machine validity.
2. Diagnose (LLM or deterministic fallback - see LLM Observability Spec).
3. Build plan, run deterministic policy gate.
4. Execute or schedule the intervention with idempotency key.
5. Append audit entry and persist in **one transaction** with the state-commit.
6. Mark job DONE only after the commit succeeds. On any exception, mark FAILED
   and schedule the retry with exponential backoff, up to a bound.

Crash recovery: on worker startup, reclaim every job stuck in PROCESSING
(worker died mid-job) - re-run it because every operation is idempotent and
audit-before-action makes replays safe. This is the "system died mid-recovery"
answer: nothing is lost, nothing is double-applied.

## Resilience (everything queues; nothing drops)

- **LLM down or misconfigured**: diagnosis uses deterministic fallback, the
  job is recorded with `used_fallback`, and processing continues. The event is
  already in the queue, so it is never lost.
- **Razorpay / API down (network error or 5xx)**: the intervention is *not*
  executed; the job is requeued with backoff (`next_run_at`). A circuit breaker
  stops hammering a dead provider and the job stays queued until it recovers.
- **Notification channel down (WhatsApp/SMS/email)**: outreach job requeued
  with backoff; retry cap still enforces boundedness.
- **Past the retry cap**: job moves to DEAD, surfaced to the operator.
- **Worker crashes**: PROCESSING reclaim on startup (above).
- **Backend restarts**: queued jobs persist (SQLite), worker resumes.

Every one of these paths ends with the job still in the queue or DEAD in the
queue. There is no path where an accepted event silently vanishes.

## Live processing observability (the "I see it working" surface)

New read endpoints (UI is view-only):

1. `GET /api/pipeline/overview` - counts by state (QUEUED, PROCESSING, DONE,
   FAILED, DEAD), events received (total, last minute), events processed
   (total, last minute), current processing rate, backlog depth, oldest
   queued event age, last event timestamp. Polled by the UI.
2. `GET /api/pipeline/timeseries?bucket_minutes=...` - events received and
   processed per bucket over 24h, for the events-per-day chart.
3. `GET /api/pipeline/heatmap` - events per hour-of-day x day-of-week, so
   operators can see **high times** and detect flood windows.
4. `GET /api/pipeline/queued` - the actual queue listing with per-case status,
   model used, retry count, next_run_at, age.

There is also an SSE/WebSocket live feed (secondary to the above, but real):
pushes "event queued", "job claimed", "job done", "job failed" changes so the
UI shows processing moving in realtime, not just on a 10s poll.

## Fleet simulator control endpoints

- `POST /api/simulation/fleet/start` - body: event rate per minute, rails to
  include, amount range, `use_llm` flag, optional `experiment_id`.
- `POST /api/simulation/fleet/stop` and `/pause` / `/resume`.
- `GET /api/simulation/fleet/status` - running state, events emitted, rate.
- Remove the paper over: the current one-shot seed stays, but the demo data
  source becomes the continuous fleet.

The simulator writes through the same inbox the webhook uses, so a fleet run
exercises the exact production path.

## Webhook ingress security (storms and bad actors)

- HMAC verify on every real webhook (already exists - keep it).
- Schema validation per event type before enqueue.
- Dedupe by payment_id at the inbox (unique constraint, already present on
  cases; extend to the inbox so a duplicate 202 does not double-enqueue).
- Flood handling: if the inbox grows above a bound, the ingress still accepts
  and queues (it is just inserts), and the worker applies backpressure by
  bounding its batch. Ingress must never do heavy work.
- Untrusted fields cleansed before they ever reach a log line or an LLM
  prompt (incoming IDs sanitized - only safe characters).

## Scalability statement

Because the queue is row-level-locked FIFO and all work is idempotent, the
worker can run as multiple processes over the same SQLite/Postgres backend
(compare-and-swap claim) without double execution. The spec's design does not
require Redis or Kafka to scale to a demo fleet; if the run rate grows, the
first upgrade is a real DB, then an optional stream, keeping the same worker.

## End-to-end Verification Contract (MANDATORY)

The implementer must actually run the system and demonstrate each of these
before claiming done, and must state the exact words: "I have verified this
completely end to end." Minimal proof set:

1. With no browser/tab and no frontend running, start backend + worker, POST a
   batch of 200 events through the webhook endpoint, and confirm all 200
   reach DONE with audit entries and zero dropped.
2. Start the fleet simulator at N/minute, confirm steady-state QUEUED and DONE
   counts rising with no accumulation, and that queued/processed charts move.
3. Kill the worker mid-processing, restart it, and confirm PROCESSING jobs were
   reclaimed and completed exactly once (idempotency proven, no double
   intervention).
4. Revoke/blank the LLM key (or point it at a dead host) and confirm:
   processing continues via fallback, `used_fallback` is set, and the summary
   says FAILED backoffs happen to DEAD only after the cap.
5. Point the payment-link provider at a dead host and confirm the job is
   requeued with backoff, never executed against the dead host, and eventually
   DONE or DEAD per policy.
6. Send duplicate webhooks for the same payment_id and confirm exactly one
   case is created.
7. Confirm every number on the pipeline screens is fetched from the API - no
   hardcoded values, per repo rules.
8. Confirm the UI cannot drive processing (closing the browser changes
   nothing; no processing function lives in the frontend).

Report the results of all 8 with the verification phrase. Do not mark this
doc's requirements complete otherwise.