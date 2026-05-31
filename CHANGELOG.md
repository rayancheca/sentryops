# Changelog

All notable changes to SentryOps are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-05-31

Initial release. SentryOps is a self-hosted IT operations command center built
around four pillars on a shared CMDB, dependency graph, and immutable audit log.

### Added

#### Pillar 1 — CMDB (asset inventory)

- Typed asset model with lifecycle state, environment, owner, tags, free-form
  custom fields, and a JSONB `attributes` bag of security-posture facts.
- Full CRUD with role-gated mutations, lifecycle state changes, full-text and
  faceted filtering, and CSV import/export.
- Human-friendly per-asset short codes with on-demand QR label generation
  (`/assets/{id}/qr.png` and `.svg`).
- Directed dependency graph (`source depends on target`) with cycle-safe
  upstream/downstream/full-neighborhood traversal endpoints.

#### Pillar 2 — Compliance

- Data-driven rule registry: each control self-registers via a decorator and
  maps to a real framework reference (NIST SP 800-53, CIS Benchmark) across
  identity, encryption, patching, network, endpoint, and logging/backup domains.
- Severity-weighted scoring (low 1 / medium 2 / high 5 / critical 10) with
  not-applicable controls excluded from the math; org rollup is the unweighted
  mean of per-asset scores.
- Immutable per-run snapshots with denormalized evidence, a score-over-time
  drift series, newly-failing detection, and an audit-ready report endpoint.

#### Pillar 3 — Observability

- Services and HTTP/TCP health checks with a time-series check-result store.
- Uptime, SLO error-budget/burn-rate, and a per-service status grid.
- Automatic incident open/recover from consecutive check results, plus
  operator-driven acknowledge, comment, and resolve with a full event timeline.
- MTTA and MTTR computed from incident timestamps over a configurable window.

#### Pillar 4 — AI incident triage

- Human-in-the-loop, advisory-only triage that produces a root-cause hypothesis,
  calibrated confidence, severity assessment, prioritized remediation steps, and
  a stakeholder communications draft.
- Context assembled from the failing asset, its dependency neighbors, recent
  audit changes (field names only, never values), current compliance failures,
  and recent check results.
- Prompt-injection hardening: untrusted context is fenced and the system prompt
  forbids following embedded instructions; model output is type-coerced,
  clamped, length-bounded, and `extra`-forbidden before persistence.
- Off by default and degrades gracefully; per-call output cap and a daily token
  budget; every result logs token usage and estimated USD cost. Ships a
  clearly-labelled illustrative seed result so the surface is populated at $0.

#### Platform & infrastructure

- FastAPI + SQLAlchemy 2.0 backend on PostgreSQL, with a consistent response
  envelope and pagination contract.
- JWT bearer auth with access/refresh tokens and three RBAC roles
  (viewer < operator < admin) enforced at the API boundary.
- Append-only audit log written atomically with the mutation it records.
- Redis + RQ background worker; Alembic migrations.
- Prometheus `/metrics` exposition (compliance score, open incidents, MTTA/MTTR,
  per-check up/latency, assets by type and environment) and an importable
  Grafana dashboard.
- Next.js 14 (App Router) operator console: NOC dashboard, assets, compliance,
  and observability surfaces.
- Docker Compose stack, a `make demo` one-command bring-up + seed, deterministic
  demo data, and tooling targets for tests, coverage, lint, type-check, and
  Playwright screenshot capture.

[Unreleased]: https://github.com/your-org/sentryops/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/your-org/sentryops/releases/tag/v0.1.0
