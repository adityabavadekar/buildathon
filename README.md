# FORTX - Flow Orchestration & Revenue Trust eXecution

An agent that finds revenue at risk, works out why, runs a bounded recovery
action, and proves - across a batch, with an audit trail - how much it actually
recovered.

Built for the Razorpay AI Buildathon, Track 3 (AI Revenue Recovery).

> **Current stage: scaffold.** The services boot, talk to each other, and are
> linted, type-checked, and tested. There is deliberately **no** detection,
> diagnosis, intervention, or recovery logic yet.

## Quickstart

Two commands, from the repository root:

```bash
make install     # backend deps via uv, frontend deps via pnpm
make dev         # backend on :8000, frontend on :5173
```

Then open <http://localhost:5173>. The page shows the live result of the
backend's `/health` endpoint - if it says "Online", both services are talking.

No `.env` file is required to run the scaffold. To add LLM provider keys later:

```bash
cp backend/.env.example backend/.env    # then fill in
```

## Commands

| Command | Does |
| --- | --- |
| `make install` | Install dependencies for both services |
| `make dev` | Run both services (backend :8000, frontend :5173) |
| `make dev-backend` | Backend only |
| `make dev-frontend` | Frontend only |
| `make test` | Backend tests |
| `make lint` | Ruff + mypy + ESLint + Prettier checks |
| `make format` | Auto-format both services |
| `make build` | Production frontend build |
| `make check` | Everything CI runs, locally |

## Layout

```
backend/          FastAPI service, managed with uv
  src/app/
    core/         config, logging, middleware
    llm/          the only place that calls a model provider
    detection/    finds at-risk revenue         (empty)
    intervention/ chooses + runs recovery       (empty)
    audit/        decision log + measurement    (empty)
    api/routes/   HTTP endpoints
  tests/
frontend/         React + Vite dashboard, managed with pnpm
  src/
    lib/api.ts    typed backend client
    components/   UI primitives
docs/             architecture, decisions, research
```

## Docs

- [docs/DECISIONS.md](docs/DECISIONS.md) - decision log, including what broke and why things changed
- [docs/BUILDATHON.md](docs/BUILDATHON.md) - the brief this is built against
- [docs/RESEARCH.md](docs/RESEARCH.md) - verified research on Razorpay's APIs, the regulatory constraints, and dataset availability
- [AGENTS.md](AGENTS.md) - working instructions for coding agents

## Requirements

| Tool | Version used | Notes |
| --- | --- | --- |
| Python | 3.13 | pinned in `backend/.python-version` |
| [uv](https://docs.astral.sh/uv/) | 0.12.5 | manages the Python env and lockfile |
| Node | 22.23.2 | 20.x is EOL as of April 2026 |
| pnpm | 11.24.0 | via corepack |

`make install` handles everything below that.

## Environment setup performed on this machine

Recorded so the environment can be reproduced, and so nothing installed here is
a surprise later.

**System packages (via apt, needed sudo):**

```bash
# Node 22 LTS - the system had 20.19.2, which reached end-of-life in April 2026
# and is below what current Vite 8 tooling expects.
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo bash -
sudo apt-get install -y nodejs        # -> node 22.23.2, npm 10.9.8
sudo corepack enable pnpm             # -> pnpm 11.24.0
```

**Installed during verification, not required to run or build this project:**

- `chromium-headless-shell` via `npx playwright install chromium --with-deps`
  (~115 MB, cached in `~/.cache/ms-playwright/`). Used once to confirm the page
  really renders live backend data in a browser rather than only in `curl`.
  Remove with `rm -rf ~/.cache/ms-playwright` if you don't want it.
- `tesseract-ocr`, `tesseract-ocr-eng`, `tesseract-ocr-osd`, `libtesseract5` -
  installed by a research subagent to OCR scanned NPCI circulars. **Not used by
  this project.** Remove with
  `sudo apt remove tesseract-ocr tesseract-ocr-eng tesseract-ocr-osd`.

**Considered and removed:** `fnm` (Node version manager) was installed to
`~/.local/share/fnm`, then deleted once Node 22 went in system-wide instead. It
left no shell-profile changes.

**Helper scripts, outside this repo:** `/tmp/websearch.py` and `/tmp/fetch.py`
were written during research because the built-in web search was returning
errors. They are throwaway tools for gathering the material in
`docs/RESEARCH.md`, are not part of the project, and can be deleted.

**Git configuration** is repo-local only (`git config --local`); global config
was left untouched. Commits are signed with an SSH key
(`~/.ssh/id_ed25519`) rather than GPG, because the `signingkey` referenced in
the machine's dotfiles has no corresponding secret key present. To make signed
commits show as "Verified" on GitHub, the public key needs registering as a
signing key:

```bash
gh auth refresh -h github.com -s admin:ssh_signing_key   # interactive
gh ssh-key add ~/.ssh/id_ed25519.pub --type signing
```
