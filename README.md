# FORTX - Flow Orchestration & Revenue Trust eXecution

FORTX is an agent that finds revenue at risk - failed payments, abandoned
checkouts, failed subscription renewals, overdue receivables - works out why,
runs a bounded recovery action, and proves how much it actually recovered.
Recovery is measured across a batch against a 10% holdout control arm, so the
figure it reports is a counterfactual rather than an assertion.

Built for the Razorpay AI Buildathon, Track 3 (AI Revenue Recovery).

For the source and to report problems, visit the
[project repository](https://github.com/adityabavadekar/buildathon).


## Table of contents

- Requirements
- Installation
- Configuration
- Troubleshooting
- FAQ
- Maintainers


## Requirements

| Tool | Version | Notes |
| --- | --- | --- |
| Python | 3.13 | pinned in `backend/.python-version` |
| [uv](https://docs.astral.sh/uv/) | 0.11+ | manages the Python env and lockfile |
| Node | 22 | 20.x is EOL as of April 2026 |
| pnpm | 11 | via corepack |
| PostgreSQL | 16+ | schema migrations are applied at startup |

An LLM provider key is optional. Without one the agent falls back to
deterministic rule-based classification, and the test suite needs no key.


## Installation

```bash
make install
```

This installs backend dependencies with uv and frontend dependencies with pnpm.
PostgreSQL must be running and reachable; the application applies its own
Alembic migrations at startup, so no separate migration step is needed.

To run both services:

```bash
make dev
```

The backend serves on port 8000 and the frontend on 5173. Next rewrites `/api/*`
to the backend, so browser requests are same-origin in development.

The recovery worker is a third process and is not started by `make dev`:

```bash
make worker
```

Without it, jobs enqueued by the engine stay QUEUED and nothing is ever
executed.

Run `make help` for the full target list, including `make check` (everything CI
runs) and `make benchmark` (replay the fixed dataset and write a report).


## Configuration

Configuration is read from the environment. Every variable is prefixed `APP_`,
except provider API keys, which keep their conventional names so the provider
SDKs pick them up unchanged. Add a field to `backend/src/app/core/config.py`
rather than reading the environment anywhere else.

```bash
cp backend/.env.example backend/.env
```

Nothing must be set to run locally. The settings that change behaviour most:

- `APP_OPERATOR_PASSWORD` gates the whole dashboard behind a single shared
  operator password. **Left unset, the gate is disabled and the dashboard is
  open to anyone who can reach the port.**
- `APP_SESSION_SECRET` signs session cookies. Unset, each process invents its
  own key, so a restart logs everyone out and two replicas reject each other's
  cookies.
- `DATABASE_URL` points at PostgreSQL. Defaults to
  `postgresql://postgres:postgres@127.0.0.1:5432/fortx`.
- `APP_RAZORPAY_KEY_ID` and `APP_RAZORPAY_KEY_SECRET` enable live gateway calls.
  Without them, and outside production, interventions run against a simulation
  and are recorded as simulated.

Recovery policy - contact caps, cooldowns, maximum discount, allowed channels,
holdout percentage - is configured in the dashboard, not the environment, and is
enforced by a deterministic policy gate that re-derives every cap.


### Production

Four containers: PostgreSQL, the backend API, the recovery worker, and the
dashboard. Only the dashboard port is published.

```bash
cp .env.prod.example .env
openssl rand -hex 32
make prod-up
```

`make prod-up` refuses to start while the template placeholders remain in
`.env`, or while `APP_OPERATOR_PASSWORD` is empty.

Terminate TLS at a reverse proxy in front of the published port. Under
`APP_ENV=production` the session cookie is set `Secure`, so a browser served
over plain HTTP silently refuses to store it.

The backend runs a single uvicorn worker, because the login throttle and fleet
simulator hold process-local state. Scale out only once that state moves into
PostgreSQL.


## Troubleshooting

**The queue count grows but nothing is processed.** The recovery worker is not
running. Start it with `make worker`, or `docker compose ps` to check the
`worker` service.

**Backend tests all fail at collection with a connection error.** PostgreSQL is
not running or `DATABASE_URL` is wrong. The audit store is SQL-backed and there
is no in-memory fallback to test against.

**Login appears to do nothing in production.** The session cookie is `Secure`
under `APP_ENV=production` and the browser is on plain HTTP. Put TLS in front.

**Changing `BACKEND_HOST` has no effect on the built frontend.** Next resolves
the `/api/*` rewrite into `routes-manifest.json` during `next build`, so it is a
build-time value. Rebuild rather than restart.

**Interventions fail with `PAYMENT_LINK_MISSING_CREDENTIALS`.** Expected under
`APP_ENV=production` with no Razorpay credentials: rather than fabricate a
simulated link, the tool fails honestly. Supply credentials, or run outside
production to use the simulation path.


## FAQ

**Q: Is there a signup or user registration?**

**A:** No. Authentication is a single shared operator password with no user
accounts or roles, which means access cannot be revoked for one person without
rotating the password for everyone.

**Q: Are the recovery figures real money?**

**A:** They are real measurements of whatever rails were used. The dashboard
states the live/simulated mix alongside the recovery figure, and simulated
interventions are recorded as simulated in the audit trail. Without Razorpay
credentials, no live call is made.

**Q: Why a holdout arm instead of just reporting what was recovered?**

**A:** Some failed payments recover on their own. Without an uncontacted control
group there is no way to separate the agent's contribution from that baseline,
so "we recovered X" would be unfalsifiable.

**Q: Where is the architecture documented?**

**A:** [docs/FORTX_MASTER.md](docs/FORTX_MASTER.md) is the source of truth for
architecture and implemented state. [docs/DECISIONS.md](docs/DECISIONS.md) is
the decision and build log, including what broke and why things changed.
[AGENTS.md](AGENTS.md) holds working instructions for coding agents.


## Maintainers

- Aditya Bavadekar - [adityabavadekar](https://github.com/adityabavadekar)
