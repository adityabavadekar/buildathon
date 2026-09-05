# FORTX - Flow Orchestration & Revenue Trust eXecution

FORTX finds revenue at risk (failed payments, abandoned checkouts, failed
renewals, overdue receivables), diagnoses why, runs a bounded recovery action,
and measures the result against a 10% holdout control arm.

Built for the Razorpay AI Buildathon, Track 3 (AI Revenue Recovery).


## Requirements

- Python 3.13, pinned in `backend/.python-version`
- [uv](https://docs.astral.sh/uv/) 0.11+, manages the Python env and lockfile
- Node 22, since 20.x is EOL as of April 2026
- pnpm 11, via corepack
- PostgreSQL 16+, migrations applied at startup
- An LLM provider key is optional; without one it falls back to rules


## Installation

```bash
make setup       # deps for both services, plus the database in docker
make dev         # backend :8000, frontend :5173
make worker      # queue-draining daemon, not started by make dev
```

`make setup` starts PostgreSQL from `docker-compose.dev.yml`, and the backend
applies its migrations at startup. Without the worker, queued jobs stay QUEUED.
`make help` lists the rest.


## Configuration

`cp backend/.env.example backend/.env`. Nothing is required locally.

- `APP_OPERATOR_PASSWORD` gates the dashboard. **Unset, it is open to anyone.**
- `APP_SESSION_SECRET` signs cookies.
- `DATABASE_URL` defaults to `postgres:postgres@127.0.0.1:5432/fortx`.
- `APP_RAZORPAY_KEY_ID`, `APP_RAZORPAY_KEY_SECRET` enable live gateway calls.


## Maintainers

- Aditya Bavadekar - [adityabavadekar](https://github.com/adityabavadekar)
