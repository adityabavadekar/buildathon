# Architecture

> Skeleton. Filled in as the system is built — see [DECISIONS.md](DECISIONS.md)
> for the reasoning behind each choice, and the repository README for how to run
> what exists today.

## System Overview

Two services: a Python backend that does the work, and a React dashboard that
makes the work legible.

```
┌──────────────┐        /api/*         ┌──────────────────────┐
│  Dashboard   │ ────────────────────► │  Backend (FastAPI)   │
│ React + Vite │ ◄──────────────────── │                      │
└──────────────┘        JSON           └──────────┬───────────┘
                                                  │
                                    ┌─────────────┼─────────────┐
                                    ▼             ▼             ▼
                               detection    intervention      audit
                                    │             │             │
                                    └──────┬──────┘             │
                                           ▼                    ▼
                                    LLM (litellm)        append-only log
```

Currently implemented: the transport, `/health`, request-ID correlation, and the
LLM seam. The three domain packages are empty.

### Components

| Component | Responsibility | Status |
| --- | --- | --- |
| `app.api.routes` | HTTP surface | `/health` only |
| `app.core.config` | Environment-backed settings, validated at startup | done |
| `app.core.logging` | structlog, JSON in deployment, request-ID correlation | done |
| `app.core.middleware` | Binds a request ID to every request and response | done |
| `app.llm.client` | The only place a model provider is called | seam only |
| `app.detection` | Finds at-risk revenue; diagnoses cause | **empty** |
| `app.intervention` | Chooses and executes a bounded recovery action | **empty** |
| `app.audit` | Append-only decision record; batch measurement | **empty** |

## Data Flow

_To be filled in. The intended shape:_

1. **Ingest** — a batch of synthetic records (payments, checkouts, subscriptions,
   invoices) enters the system.
2. **Detect** — each record is classified as at-risk or not, with a reason.
3. **Diagnose** — the cause is determined (soft decline, insufficient funds,
   expired mandate, abandoned at payment step, …).
4. **Decide** — an intervention is selected, subject to bounds: caps, retry
   limits, stopping rules, and an escalation path when bounds are hit.
5. **Execute** — the intervention runs against Razorpay test-mode APIs.
6. **Measure** — outcomes are compared against a holdout arm to establish what
   was actually recovered rather than what merely succeeded.

## Audit Trail Design

_To be filled in. The requirements it must satisfy:_

- **Append-only.** Records are never mutated or deleted.
- **Every money-affecting action is logged before it is attempted**, with the
  inputs that justified it, so an action is explainable after the fact.
- **Correlated.** Every entry carries the request ID bound by middleware, so an
  action traces back to what triggered it. Verified working: uvicorn's own access
  logs already carry `request_id`.
- **Bounded actions are visibly bounded** — the log shows the cap that applied
  and how close the action came to it.
- **Failures are first-class.** A gracefully handled failure is a required
  deliverable, so the trail must record what broke and what the system did next.
- **Reproducible.** Given the same batch and seed, the same decisions.

## Measurement

_To be filled in. The one non-negotiable:_

Recovery is measured against a **counterfactual holdout**, not asserted. A batch
is split; the agent acts on one arm and not the other. "Recovered" means the
difference between arms, not the sum of successful interventions — otherwise the
number counts revenue that would have arrived anyway.

Reported per batch: recovery rate against holdout, absolute amount recovered,
intervention attempts per recovery, false-positive cost (interventions on records
that were never actually at risk), and unresolved exceptions.
