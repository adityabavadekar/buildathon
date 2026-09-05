# FORTX - Flow Orchestration & Revenue Trust eXecution

FORTX finds revenue at risk (failed payments, abandoned checkouts, failed
subscription renewals, overdue receivables), works out why, runs a bounded
recovery action, and measures what it recovered against a 10% holdout control
arm, so the figure is a counterfactual rather than an assertion.

Built for the Razorpay AI Buildathon, Track 3 (AI Revenue Recovery).

For the source, visit the
[project repository](https://github.com/adityabavadekar/buildathon).


## Table of contents

- Requirements
- Installation
- Configuration
- Maintainers


## Requirements

- Python 3.13, pinned in `backend/.python-version`
- [uv](https://docs.astral.sh/uv/) 0.11+, manages the Python env and lockfile
- Node 22, since 20.x is EOL as of April 2026
- pnpm 11, via corepack
- PostgreSQL 16+, migrations applied at startup
- An LLM provider key is optional; without one the agent falls back to
  deterministic rules


## Installation

```bash
make install     # backend deps via uv, frontend deps via pnpm
make dev         # backend :8000, frontend :5173
make worker      # queue-draining daemon, not started by make dev
```

Without the worker, queued jobs stay QUEUED. Run `make help` for the rest,
including `make check` and `make benchmark`.


## Configuration

Read from the environment, every variable prefixed `APP_` except provider keys.
Add fields to `backend/src/app/core/config.py`, never read the environment
elsewhere. Nothing is required locally: `cp backend/.env.example backend/.env`.

- `APP_OPERATOR_PASSWORD` gates the dashboard. **Unset, the gate is disabled and
  the dashboard is open to anyone who can reach the port.**
- `APP_SESSION_SECRET` signs session cookies. Unset, restarts log everyone out.
- `DATABASE_URL` defaults to
  `postgresql://postgres:postgres@127.0.0.1:5432/fortx`.
- `APP_RAZORPAY_KEY_ID` and `APP_RAZORPAY_KEY_SECRET` enable live gateway calls.
  Without them, interventions are simulated and recorded as simulated.

Recovery policy (contact caps, cooldowns, maximum discount, allowed channels,
holdout percentage) is set in the dashboard and enforced by a policy gate that
re-derives every cap.

For containers, `cp .env.prod.example .env` and `make prod-up`. Terminate TLS in
front: under `APP_ENV=production` the session cookie is `Secure`, so a browser
on plain HTTP will not store it.

Architecture is documented in [docs/FORTX_MASTER.md](docs/FORTX_MASTER.md), with
the build log in [docs/DECISIONS.md](docs/DECISIONS.md) and agent instructions
in [AGENTS.md](AGENTS.md).


## Maintainers

- Aditya Bavadekar - [adityabavadekar](https://github.com/adityabavadekar)
