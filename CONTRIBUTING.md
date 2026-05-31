# Contributing to SentryOps

Thanks for working on SentryOps. This guide gets you from a clean clone to a
green PR. Everything here is accurate to the repository as it stands; where a
command depends on tooling you must have installed, that is called out.

SentryOps is a monorepo:

- `backend/` — FastAPI + SQLAlchemy 2.0 + Postgres + Redis/RQ (Python 3.12).
- `web/` — Next.js 14 (App Router) + TypeScript + Tailwind (pnpm).
- Orchestrated by `docker-compose.yml`, driven by the root `Makefile`.

---

## 1. Development setup

You need Docker (with Compose v2) for the recommended path, or a local Postgres
16 + Redis 7 for the native path. The first time you set up, create your `.env`:

```bash
make env        # copies .env.example -> .env if it does not exist
```

`.env` is gitignored. Never commit it. Generate a real `SECRET_KEY` before any
non-local use:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### Option A — Docker Compose (recommended)

This brings up Postgres, Redis, the API, the observability worker, and the web
app, runs migrations on the API container at boot, and exposes everything
locally.

```bash
make up         # build + start the full stack (runs `make env` first)
# API docs -> http://localhost:8000/docs
# Web       -> http://localhost:3000
```

To get a populated dashboard in one command (up, wait for `/health`, seed):

```bash
make demo
```

After `make demo` you can log in with the demo accounts printed by the target:

- `admin@sentryops.local` / `admin12345` (admin)
- `viewer@sentryops.local` / `viewer12345` (read-only)

These are **demo credentials** — see `SECURITY.md` before exposing any instance.

Useful lifecycle targets:

```bash
make logs       # tail service logs
make ps         # show running services
make restart    # restart api + worker
make down       # stop the stack (keeps volumes)
make nuke       # stop AND delete volumes (destroys data)
```

### Option B — Native (no Docker for the app)

You still need Postgres 16 and Redis 7 reachable. The simplest path is to run
just those two via Compose and run the app processes on your host:

```bash
docker compose up -d postgres redis
```

Point your `.env` at them (the defaults already match Compose):

```ini
DATABASE_URL=postgresql+psycopg://sentryops:sentryops@localhost:5432/sentryops
REDIS_URL=redis://localhost:6379/0
```

**Backend** (Python 3.12, virtualenv):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"        # installs runtime + dev deps from pyproject.toml
alembic upgrade head           # apply migrations
python -m scripts.seed         # optional: load demo data
uvicorn app.main:app --reload --port 8000
```

Run the observability worker in a second shell:

```bash
cd backend && source .venv/bin/activate
python -m app.workers.run
```

**Frontend** (pnpm):

```bash
cd web
pnpm install
NEXT_PUBLIC_API_URL=http://localhost:8000 pnpm dev   # -> http://localhost:3000
```

---

## 2. Makefile targets

The `Makefile` is the canonical entrypoint. `make help` lists everything; the
targets you will use most:

| Target | What it does |
| --- | --- |
| `make env` | Create `.env` from `.env.example` if absent |
| `make up` | Build and start the full stack |
| `make down` | Stop the stack (volumes survive) |
| `make build` | Build all images |
| `make demo` | Up + wait for health + seed (one-command live demo) |
| `make seed` | Load demo data (assets, dependencies, services, violations, incidents, seeded AI triage) |
| `make migrate` | `alembic upgrade head` inside the API container |
| `make makemigration m="msg"` | Autogenerate a migration |
| `make test` | Run all tests (backend + frontend) |
| `make test-backend` | `pytest -q --cov=app --cov-report=term-missing` |
| `make test-frontend` | `pnpm test run` in `web/` |
| `make cov` | Backend coverage HTML report |
| `make lint` | Lint backend (ruff + black --check) and web (eslint) |
| `make fmt` | Auto-format backend (ruff --fix + black) and web (prettier) |
| `make typecheck` | `mypy app` (strict) and `pnpm typecheck` (tsc) |
| `make capture` | Capture demo screenshots/GIF via Playwright (stack must be seeded) |
| `make clean` | Remove local caches and build artifacts |
| `make nuke` | Stop the stack and delete volumes (destroys data) |

> Note: `make test-backend`, `make cov`, and `make migrate` shell into the
> running `api` container, so the stack must be up. `make test-frontend`,
> `make lint`, `make fmt`, and `make typecheck` run the backend halves with
> `cd backend` and the web halves with `cd web`, so you need the local
> toolchains (venv for backend, pnpm for web) installed for those.

---

## 3. Commit conventions

Use **[Conventional Commits](https://www.conventionalcommits.org/)**:

```
<type>: <description>

<optional body>
```

Allowed types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`.

Examples:

```
feat: add tls-cert-expiry compliance rule
fix: revoke presented refresh token before minting its replacement
docs: document prompt-injection posture in SECURITY.md
```

Keep commits focused and the subject line in the imperative mood. There is no
automated `commit-msg` hook in the repo yet, so this is a reviewer-enforced
convention; please hold the line in your PRs.

---

## 4. Pre-commit hooks

The repo ships `.pre-commit-config.yaml`. Install the hooks once so they run on
every `git commit`:

```bash
pip install pre-commit
pre-commit install
```

Run them across the whole tree on demand:

```bash
pre-commit run --all-files
```

Configured hooks:

- **pre-commit-hooks**: trailing-whitespace, end-of-file-fixer, check-yaml,
  check-added-large-files (`--maxkb=1024`), check-merge-conflict,
  **detect-private-key**.
- **ruff** (`--fix`) on `backend/`.
- **black** on `backend/`.
- **mypy** (strict) on `backend/` — runs `cd backend && mypy app`.
- **prettier** (`--check`) on `web/`.
- **eslint** on `web/`.

The local `mypy`, `prettier`, and `eslint` hooks use your installed project
tooling, so make sure the backend venv and `pnpm install` are in place before
committing, or those hooks will fail to launch.

---

## 5. Running tests

### Backend (pytest)

Tests live under `backend/tests/` split into `unit/`, `integration/`,
`coverage/`, and `ai/`. Markers `unit` and `integration` are defined in
`pyproject.toml`.

```bash
# Inside the stack:
make test-backend

# Native (from backend/, venv active):
pytest -q --cov=app --cov-report=term-missing
pytest -m unit                     # pure-logic tests, no database
pytest -m integration              # exercises the DB + HTTP layer
pytest tests/ai                    # AI triage / schema / client tests
```

The AI tests do **not** hit the network. `AnthropicTriageClient._invoke` is the
single seam tests monkeypatch, so no API key is needed and no spend occurs.

Coverage target is 80%+. Generate the HTML report with `make cov` (writes to
`backend/htmlcov/`).

### Frontend (vitest)

Vitest is configured (`web/vitest.config.ts`, jsdom environment, `@` alias) to
pick up `**/*.test.{ts,tsx}` under `lib/` and `components/`.

```bash
make test-frontend            # pnpm test run
# or, from web/:
pnpm test                     # watch mode
pnpm test:run                 # single run (CI mode)
```

> Heads up: the vitest harness is wired but the suite is still thin — adding
> tests alongside the components and `lib/` utilities you touch is welcome and
> expected. End-to-end/visual capture runs through Playwright via `make capture`
> once the stack is seeded.

---

## 6. Lint and type-check gates

Before opening a PR, your change must pass:

```bash
make lint        # ruff check + black --check (backend); eslint (web)
make typecheck   # mypy --strict on app/ (backend); tsc --noEmit (web)
```

If lint complains about formatting, `make fmt` fixes most of it
(ruff `--fix` + black on the backend, prettier on the web). Standards:

- **Backend**: ruff (lint, including the `S`/flake8-bandit security ruleset),
  black (formatting, 100 cols), mypy `strict`. Config is in
  `backend/pyproject.toml`.
- **Frontend**: eslint (`next/core-web-vitals`), prettier (with the Tailwind
  plugin), TypeScript `strict`.

---

## 7. Pull request checklist

Before requesting review, confirm:

- [ ] Branch is up to date with the target branch and free of merge conflicts.
- [ ] Commits follow Conventional Commits (§3).
- [ ] `make lint` passes (backend + web).
- [ ] `make typecheck` passes (mypy strict + tsc).
- [ ] `make test` passes; new behavior has tests; coverage stays at 80%+.
- [ ] `pre-commit run --all-files` is clean.
- [ ] No secrets, credentials, or `.env` files are committed (the
      `detect-private-key` hook helps, but check manually).
- [ ] Security-sensitive changes (auth, RBAC, the AI triage path, compliance
      rules) call out the impact in the PR description and respect the posture
      in `SECURITY.md` — RBAC stays enforced in `backend/app/api/deps.py`, and AI
      triage stays advisory and human-in-the-loop with untrusted-data fencing
      intact.
- [ ] If you added a DB column or table, you generated a migration
      (`make makemigration m="..."`) and it applies cleanly from a fresh
      `alembic upgrade head`.
- [ ] User-facing or workflow changes are reflected in the docs and, for UI
      work, in the screenshots/GIF where relevant.

Open the PR against `main`. Keep the description specific: what changed, why, and
how you verified it. Thanks for contributing.
