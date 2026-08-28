# AGENTS.md

Working instructions for coding agents in this repository. Read this before
changing anything.

## What this is

A revenue-recovery agent for the Razorpay AI Buildathon, Track 3. It detects
revenue at risk (failed payments, abandoned checkouts, failed subscription
renewals, overdue receivables), diagnoses the cause, chooses a **bounded**
intervention, executes it, and proves across a batch how much money it recovered.

**Current stage: scaffold.** Both services boot and communicate. There is no
detection, diagnosis, intervention, or recovery logic yet — the
`detection/`, `intervention/`, and `audit/` packages are intentionally empty.
Do not add product logic unless the task explicitly asks for it.

## Commands

Run from the repository root. All are in the `Makefile`.

| Task | Command |
| --- | --- |
| Install everything | `make install` |
| Run both services | `make dev` |
| Backend only | `make dev-backend` |
| Frontend only | `make dev-frontend` |
| Backend tests | `make test` |
| All lint + typecheck | `make lint` |
| Auto-format | `make format` |
| Everything CI runs | `make check` |

Per-service, if you need finer control:

```bash
# backend/  (uv manages the venv; never activate it manually)
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ruff format .
uv run mypy
uv run fastapi dev src/app/main.py

# frontend/
pnpm install
pnpm dev
pnpm lint
pnpm typecheck
pnpm format
pnpm build
```

Backend serves on `:8000`, frontend on `:5173`. The Vite dev server proxies
`/api/*` to the backend, so browser requests are same-origin in development.

## Money rules

These are the constraints an agent cannot infer from the code, and getting them
wrong is the failure mode that matters most in a payments tool.

- **Never use `float` for money.** `Decimal` in Python, integer minor units
  (paise) on the wire and in storage. Floats silently lose paise.
- **Every amount carries an explicit currency.** No implicit INR. A bare number
  is a bug.
- **All timestamps are timezone-aware UTC**, converted for display only.
  Settlement and cutoff logic is wrong without this.
- **Every money-affecting action must be idempotent** and keyed, so a retry
  cannot double-charge or double-refund.
- **Every money-affecting action must be audit-logged before it is attempted**,
  with the decision inputs that led to it — not just the outcome.
- **Recovery must be measured against a counterfactual**, not asserted. A batch
  needs a holdout arm, or "we recovered ₹X" means nothing.
- Interventions are **bounded**: explicit caps, stopping rules, and an escalation
  path. An unbounded retry loop is not a recovery strategy.

## Always

- Read `docs/DECISIONS.md` before changing architecture; append to it when you
  make a decision, and when something breaks and you fix it. It doubles as the
  build log.
- Add config as a field on `Settings` in `backend/src/app/core/config.py`.
- Use `structlog` via `app.core.logging.get_logger`, with event names like
  `intervention.attempted` and structured key-values.
- Type everything. `mypy --strict` and `eslint strictTypeChecked` both gate CI.
- Keep the frontend's backend calls in `frontend/src/lib/api.ts`.

## Never

- **Never commit `.env`.** Only `.env.example`, with dummy values.
- **Never call a provider SDK directly outside `backend/src/app/llm/client.py`.**
  That module is the single seam for model calls, cost accounting, and audit.
- **Never read `os.environ` outside `core/config.py`.**
- Never use `print()` — it won't appear in the structured audit trail.
- Never add a new FastAPI route assuming it is protected. **Routes are
  unauthenticated unless you add a dependency that authenticates them.**
- Never pin a dependency to `latest` without checking compatibility. Two live
  examples: `typescript` must stay `<6.1` because typescript-eslint cannot
  support TS 7's compiler API yet, and ruff's `select` must be `extend-select`
  or it silently disables most of the default rule set.
- Never use `httpx` in tests; use `httpx2`. Starlette 1.6 deprecated the former.
- Never commit real merchant data, real payment IDs, or real customer records.
  Synthetic fixtures only.

## Conventions

**Backend** — `src/` layout, package `app`. `core/` is cross-cutting (config,
logging, middleware). `llm/` is the only provider boundary. `detection/`,
`intervention/`, and `audit/` are the product domains. `api/routes/` holds one
module per resource, each exporting a `router`.

**Frontend** — `lib/` for non-visual logic, `components/ui/` for primitives,
`routes/` for pages. Import via the `@/` alias, not deep relative paths.

**Design tokens** live in `frontend/src/index.css` under `@theme`. Tailwind v4 is
CSS-first — there is no `tailwind.config.js`, and adding one would be wrong.
Money figures use the `money` utility or `font-mono`; both enable `tnum`.
Do not put `tabular-nums` on a `<table>` or `<tr>` — it compiles to a
`@property` with `inherits: false` and will not reach the cells.

**Status colors** map to the recovery lifecycle and are semantic, not decorative:
`recovered`, `pending`, `failed`, `escalated`.

## Verifying a change

A change is not done until this passes:

```bash
make check
```

For anything touching the money path, also state in your summary what you
verified and what you could not.
