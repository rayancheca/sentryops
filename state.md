# SentryOps — build state

Running log of decisions and progress so work resumes cleanly across sessions.

## Locked decisions (Phase 0)
- Repo: `rayancheca/sentryops`, MIT. $0 local-first deploy (docker compose + Playwright-captured screenshots); Terraform deferred to roadmap.
- AI triage: feature flag OFF by default; demo ships seeded illustrative triage (zero API calls); live with a user-supplied `ANTHROPIC_API_KEY`; tests mock the client.
- AI model default: `claude-sonnet-4-6` (env `ANTHROPIC_MODEL`).
- Approval gates waived by the user: full autonomous build, surface only the final deliverable.

## Stack
Backend: Python 3.12, FastAPI, SQLAlchemy 2.0 (typed), Alembic, Pydantic v2, Postgres (JSONB), Redis, RQ. Frontend: Next.js 14 App Router, TS strict, Tailwind, SWR, Recharts. JWT + RBAC (admin/operator/viewer) enforced at the API layer.

## Progress
- [x] Phase 0 — Plan (`docs/PLAN.md`, 1,565 lines).
- [x] Phase 1 — Scaffold: repo layout, docker-compose (postgres/redis/api/worker/web), multi-stage Dockerfiles, `.env.example`, Makefile, 5 CI workflows (added in Phase 7), pre-commit, Alembic. FastAPI `/health` + `/ready` + `/metrics`.
- [x] Phase 2 — Assets/CMDB: models, audit log (append-only), dependency graph (adjacency + cycle-safe BFS), tags + QR (segno), check-in/out, CSV import/export, auth + RBAC. 16 tables, initial migration applied.
- [x] Phase 3 — Compliance: data-driven rule registry, 16 rules (CIS/NIST), severity-weighted scoring, historical snapshots + drift + newly-failing, audit-ready report.
- [x] Phase 4 — Observability: HTTP/TCP synthetic checks, scheduler + RQ worker, uptime/SLO/error-budget, incident state machine (K-down open / M-up close), MTTA/MTTR, Prometheus `/metrics`.
- [x] Phase 5 — AI triage: context assembly (asset + deps + recent audit + compliance failures + check history), versioned prompt, prompt-injection hardening, schema clamping, feature flag, token/cost log, seeded illustrative output.
- [x] Backend verification: 138+ tests passing, ruff + black + mypy --strict clean, app imports, end-to-end smoke test green against real Postgres. Coverage pass in progress (target >=80%).
- [x] Seed (`scripts/seed.py`): 30 assets, 22 deps, 5 services, 300 check results, 3 incidents (1 open critical), 2 seeded triages, 7 compliance runs (drift), audit trail. Latest org score ~91%.
- [~] Phase 6 — Frontend: design system + shell + login + 4 pillar surfaces (workflow in progress).
- [~] Phase 7 — Docs: ARCHITECTURE, SECURITY, CONTRIBUTING, DECISIONS (ADRs), Grafana JSON, DEMO, INTERVIEW, GitHub templates (workflow in progress). README + CI workflows + screenshots pending.
- [ ] Phase 8 — Capture live screenshots (Playwright), write README, publish to GitHub.

## Local dev (this machine, no Docker daemon running)
- Native Postgres 16 + Redis via Homebrew. DBs: `sentryops` (dev/seed), `sentryops_test*` (tests). Role `sentryops`/`sentryops`.
- Backend venv: `/tmp/sentryops-venv`. Run API: `cd backend && DATABASE_URL=postgresql+psycopg://sentryops:sentryops@localhost:5432/sentryops PYTHONPATH=. /tmp/sentryops-venv/bin/uvicorn app.main:app`.
- End users run everything with `docker compose up` / `make demo`.

## Resume here
After the three workflows land: verify frontend build/typecheck, run the full stack seeded, capture screenshots, write the CI workflows + README, then commit (Conventional Commits) and publish to GitHub.
