# AGENTS.md

Working instructions for coding agents in this repository. Read this before
changing anything.

## What this is

A revenue-recovery agent for the Razorpay AI Buildathon, Track 3. It detects
revenue at risk (failed payments, abandoned checkouts, failed subscription
renewals, overdue receivables), diagnoses the cause, chooses a **bounded**
intervention, executes it, and proves across a batch how much money it recovered.

**Current stage: Full Implementation.** Both services are fully active.
The `detection/`, `intervention/`, and `audit/` packages are implemented, typed,
and backed by deterministic policy gates, contract tests, and a 10% holdout control arm.

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
| Benchmark + write report | `make benchmark` |

Per-service, if you need finer control:

```bash
# backend/  (uv manages .venv; never activate it manually)
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
  with the decision inputs that led to it - not just the outcome.
- **Recovery must be measured against a counterfactual**, not asserted. A batch
  needs a holdout arm, or "we recovered ₹X" means nothing.
- Interventions are **bounded**: explicit caps, stopping rules, and an escalation
  path. An unbounded retry loop is not a recovery strategy.

## Style

**No emojis, em-dashes, en-dashes, smart quotes, arrows, or other non-ASCII
characters in code, comments, config, or commit messages.** Use `-` for a dash,
`...` for an ellipsis, `->` for an arrow, straight quotes, and `INR` rather than
the rupee sign. ASCII only outside Markdown prose, so that terminals, diffs, and
log pipelines render identically everywhere.

**Comments explain why, never what.** If a comment restates the line below it,
delete it. Write a comment when the reason is not visible in the code: a
non-obvious constraint, a library behaviour that surprises, a decision that looks
wrong until explained. Section-divider banners are noise; group with blank lines
instead.

```python
# Bad, restates the code:
# Set the request ID header
headers.append((REQUEST_ID_HEADER, request_id))

# Good, explains a constraint you cannot see:
# Incoming IDs are untrusted input: keep only characters safe to put in a log
# line and echo back in a header.
```

## Always

- Read `docs/FORTX_MASTER.md` first - it is the single source of truth for
  architecture, implemented state, and every pending spec with its verification
  contract. Archived/superseded docs live under `docs/_archive/`.
- Read `docs/DECISIONS.md` before changing architecture; append to it when you
  make a decision, and when something breaks and you fix it. It doubles as the
  build log.
- Add config as a field on `Settings` in `backend/src/app/core/config.py`.
- Use `structlog` via `app.core.logging.get_logger`, with event names like
  `intervention.attempted` and structured key-values.
- Type everything. `mypy --strict` and `eslint strictTypeChecked` both gate CI.
- Keep the frontend's backend calls in `frontend/src/lib/api.ts`.
- Comprehensive Audit Trails: Persist timestamped LLM outputs.
- Every action taken by system, should be logged in the database and should be visilble in audit trail
- Strong Typing: Use strict typing and typed catch blocks (e.g., in TypeScript or Python) consistently.
- Utils: Move cross-cutting helpers into a shared utils or helpers module.
- Use strict enums

## Never

- **NEVER EVER HARDCODE ANYTHING IN FRONTEND.** All metrics, statuses, URLs, policy rules, breakdown percentages, failure category distributions, models, and configuration MUST be fetched dynamically from the backend API or loaded from explicit environment configuration. Hardcoding dummy values, static percentages, static URLs, or static policy tables in UI components is strictly prohibited.
- Hardcoding random values, spread accross files. Use a constants file for such cases.
- Add code boundaries like "----". Keep code clean and compactly documented ONLY where needed.
- **Never commit `.env`.** Only `.env.example`, with dummy values.
- **Never call a provider SDK directly outside `backend/src/app/llm/client.py`.**
  That module is the single seam for model calls, cost accounting, and audit.
- **Never read `os.environ` outside `core/config.py`.**
- Never use `print()` - it won't appear in the structured audit trail.
- Never add a new FastAPI route assuming it is protected. **Routes are
  unauthenticated unless you add a dependency that authenticates them.**
- Never pin a dependency to `latest` without checking compatibility. Two live
  examples: `typescript` must stay `<6.1` because typescript-eslint cannot
  support TS 7's compiler API yet, and ruff's `select` must be `extend-select`
  or it silently disables most of the default rule set.
- Never use `httpx` in tests; use `httpx2`. Starlette 1.6 deprecated the former.
- Never commit real merchant data, real payment IDs, or real customer records.
  Synthetic fixtures only.
- NEVER use emojis, em-dashes (—), or non-standard special characters in technical responses, comments, or documentation.
- Avoid subjective qualifiers (e.g., "high-impact", "professional", "optimized", "refined", "clean", "solid").
- Do not use markdown backticks in Git commit subject lines.

### 6. LOGGING

- **Bash Scripts Standard**: Bash automation scripts must implement and use this exact logging block:
  ```bash
  log() {
    printf '[ INFO ] %s\n' "$*"
  }
  ok() {
    printf '[  OK  ] %s\n' "$*"
  }
  warn() {
    printf '[ WARN ] %s\n' "$*"
  }
  err() {
    printf '[ ERR  ] %s\n' "$*"
  }
  ```
  _Constraint_: Timestamps (ISO format) should only be used in long-running background daemon logs, not general automation.
- **App/API Logging Standards**:
  - **Node.js/TypeScript**: Use `pino` with `pino-pretty` for highly readable structured output across environments.
  - **Python**: Use `loguru` or a custom logging utility (e.g., `source/assistant_logging/logger.py`). Never import the built-in `logging` module directly.
  - **Go/Rust**: Use lightweight color-coded internal terminal writers.
  - **Kotlin**: Use `Timber` or standard JVM logging.
- **Log Structure**: Log messages must include structured, rich metadata (e.g., target, timeTaken, model, query, response) rather than plain strings.

## Conventions

**Backend** - `src/` layout, package `app`. `core/` is cross-cutting (config,
logging, middleware). `llm/` is the only provider boundary. `detection/`,
`intervention/`, and `audit/` are the product domains. `api/routes/` holds one
module per resource, each exporting a `router`.

**Frontend** - `lib/` for non-visual logic, `components/ui/` for primitives,
`routes/` for pages. Import via the `@/` alias, not deep relative paths.

**Design tokens** live in `frontend/src/index.css` under `@theme`. Tailwind v4 is
CSS-first - there is no `tailwind.config.js`, and adding one would be wrong.
Money figures use the `money` utility or `font-mono`; both enable `tnum`.
Do not put `tabular-nums` on a `<table>` or `<tr>` - it compiles to a
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
