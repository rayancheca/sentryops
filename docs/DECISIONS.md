# Architecture Decision Records

Lightweight ADRs (MADR-style) for SentryOps. Each records a decision that shaped
the codebase, the alternatives weighed against it, and the consequences we now
live with. They describe what the code actually does, not aspirations.

| # | Decision | Status |
|---|----------|--------|
| [1](#adr-1-fastapi-for-the-api-layer) | FastAPI for the API layer | Accepted |
| [2](#adr-2-postgresql--jsonb-over-a-document-store) | PostgreSQL + JSONB over a document store | Accepted |
| [3](#adr-3-rq-over-celery-for-background-work) | RQ over Celery for background work | Accepted |
| [4](#adr-4-dependency-graph-as-an-edge-table-traversed-in-app-code) | Dependency graph as an edge table traversed in app code | Accepted |
| [5](#adr-5-rbac-enforced-at-the-api-layer) | RBAC enforced at the API layer | Accepted |
| [6](#adr-6-ai-triage-as-an-optional-flag-gated-hardened-module) | AI triage as an optional, flag-gated, hardened module | Accepted |
| [7](#adr-7-jwt-accessrefresh-with-refresh-rotation-over-server-side-sessions) | JWT access/refresh with rotation over server sessions | Accepted |
| [8](#adr-8-data-driven-compliance-rule-registry-with-severity-weighted-scoring) | Data-driven compliance rule registry with severity-weighted scoring | Accepted |

---

## ADR-1: FastAPI for the API layer

**Context.** The backend is a typed, IO-bound service: it serves CRUD over a
CMDB, runs synchronous compliance scans, and fronts an external LLM call. We
wanted Python (it matches the SQLAlchemy 2.0 typed style and the data work),
first-class request/response validation, and a free OpenAPI export for the
reference docs without hand-maintaining a spec.

**Decision.** Use FastAPI. Request dependencies (`app/api/deps.py`) express
auth, DB session, and role guards as composable `Depends(...)` callables;
Pydantic v2 schemas (`app/schemas/`) validate at the boundary and become the
OpenAPI model set; typed exceptions (`app/core/exceptions.py`) map to a single
error envelope. The app exposes both sync DB sessions for CRUD and an async path
where it helps.

**Alternatives considered.**
- *Django + DRF.* Batteries included, but the ORM and admin are weight we do not
  need, and serializer-based validation is less ergonomic than Pydantic for the
  strict AI-output and request schemas we wanted.
- *Flask.* Minimal, but validation, dependency injection, and OpenAPI all become
  bolt-ons we would assemble and maintain ourselves.

**Consequences.** Validation, DI, and the OpenAPI export come for free, and the
dependency system is what makes ADR-5 (RBAC at the boundary) clean. The cost: we
mix sync ORM work inside an async framework, so blocking DB calls must stay off
the event loop or run in threadpools, and FastAPI's "magic" dependency wiring
has a learning curve for contributors used to explicit controllers.

---

## ADR-2: PostgreSQL + JSONB over a document store

**Context.** The data model is the spine of the product (assets, owners,
dependency edges, compliance runs/results, health checks, incidents, audit log).
Most of it is genuinely relational, with foreign keys and join tables. But asset
security posture and user-defined metadata are open-shaped and vary by asset
type.

**Decision.** PostgreSQL as the single datastore, with JSONB for the parts that
are legitimately schemaless. `assets` carries two JSONB columns: `attributes`
(security-posture facts the compliance engine reads, GIN-friendly) and
`custom_fields` (arbitrary user metadata the engine ignores). Audit diffs
(`audit_log.before` / `after`), compliance evidence
(`compliance_results.evidence`), and the per-run severity tallies
(`compliance_runs.severity_failing`) are also JSONB. Everything with integrity
requirements stays relational: `asset_dependencies` enforces
`UNIQUE(source, target)` and `CHECK(source <> target)`; owner FKs use
`ON DELETE SET NULL`; results cascade from their run.

**Alternatives considered.**
- *MongoDB / document store.* Flexible attributes are trivial, but the
  dependency graph, the audit trail, and run/result relationships need real
  foreign keys and cascade semantics. Reimplementing referential integrity in
  application code is exactly the bug surface we wanted to avoid.

**Consequences.** One datastore to run, back up, and reason about; the relational
core gives us cascades and uniqueness for free while JSONB absorbs the open
fields. The tradeoff: JSONB columns are validated only shape-deep at the Pydantic
boundary, so a typo'd attribute key surfaces as `not_applicable` at scan time
rather than a write-time error, and heavy JSONB querying needs deliberate GIN
indexing rather than coming for free.

---

## ADR-3: RQ over Celery for background work

**Context.** Background work is small and well-bounded: a scheduler tick that
probes due health checks and opens/closes incidents, plus an AI triage job
enqueued when an incident opens. Redis is already in the stack as broker and
rollup cache.

**Decision.** Use RQ. `app/workers/queue.py` is the entire broker setup: a Redis
connection and a single `triage` queue. `app/workers/run.py` runs a plain daemon
thread for the health-check scheduler loop and an `rq.Worker` for triage jobs in
one process. Enqueue is one line (`triage_queue.enqueue(...)`).

**Alternatives considered.**
- *Celery + beat.* The standard heavyweight choice. More mature routing,
  retries, result backends, and a real distributed scheduler — but a much larger
  operational and conceptual surface (app config, beat process, broker/result
  semantics) than this workload justifies.

**Honest tradeoff.** This is a deliberate downgrade in capability. RQ gives us no
native cron-style scheduler, so we run the periodic loop as a `time.sleep`
thread in the worker process rather than a hardened scheduler. RQ's retry and
routing story is thinner than Celery's, and the single in-process scheduler
thread is a single point of failure with no leader election. For a self-hosted,
single-worker deployment that is an acceptable trade; a multi-node deployment
would likely outgrow it and want Celery or a dedicated scheduler.

---

## ADR-4: Dependency graph as an edge table traversed in app code

**Context.** Assets form a directed dependency graph ("source depends on
target"). Operators need upstream (what an asset depends on) and downstream
(what depends on it, i.e. blast radius) neighborhoods, and the AI triage context
needs a bounded slice of both. Graphs in the wild contain cycles
(A → B → A) and the data must not let a traversal loop forever. The expected
scale is modest: a single organization's inventory, not a hyperscale graph.

**Decision.** Store edges in a single relational table (`asset_dependencies`)
and traverse in application code. `app/services/dependency_service.py` runs a
breadth-first search with a `visited` set and a `max_depth` bound, so cycles and
deep chains both terminate; only unvisited neighbours are enqueued. The DB
enforces no self-loops and no duplicate edges; longer cycles are handled purely
at traversal time. The AI context builder (`app/ai/context.py`) runs its own
cycle-safe, depth-2, node-capped BFS for the same data.

**Alternatives considered.**
- *Graph database (Neo4j, etc.).* Native traversal and path queries, but it
  introduces a second datastore to operate, back up, and secure — for a graph
  whose depth we deliberately bound and whose size is small. Not worth the
  operational cost at this scale.
- *Recursive CTE in Postgres.* Keeps it in one datastore and pushes traversal to
  the DB, but the cycle guard and per-node truncation we want (cap nodes, bound
  depth, shape the response) are clearer and easier to test as explicit Python
  than as recursive SQL. We kept the traversal in code.

**Consequences.** No new datastore, the cycle/depth guards are unit-tested
directly (`tests/unit/test_dependency_tree.py`), and the traversal returns
exactly the response shape the API needs. The cost: each BFS issues a query per
frontier hop rather than one set-based query, so it would not scale to very large
or very deep graphs — acceptable given the bounded depth and modest size, and a
known place to swap in a CTE if the graph grows.

---

## ADR-5: RBAC enforced at the API layer

**Context.** Three roles exist — `viewer`, `operator`, `admin` — ordered by
privilege. Authorization must hold no matter which client calls the API; the web
UI is just one consumer, and hiding a button is not a security control.

**Decision.** Enforce RBAC at the API boundary via FastAPI dependencies in
`app/api/deps.py`. `require_role(required)` is a dependency factory that checks
`Role(user.role).can_act_as(required)` (a rank comparison defined on the `Role`
enum) and raises `PermissionDeniedError` otherwise. Routes declare the minimum
role they need through the `RequireViewer` / `RequireOperator` / `RequireAdmin`
annotated aliases. The UI mirrors these roles for affordance only; it never
substitutes for the server check.

**Alternatives considered.**
- *Enforce in the UI / client.* Trivially bypassed by calling the API directly.
  Rejected outright as a security boundary.
- *A separate policy engine / middleware layer.* More flexible for complex,
  attribute-based rules, but overkill for a three-role ordered model; the
  dependency aliases keep the required role legible right at the route
  definition.

**Consequences.** Authorization lives next to the route, is independent of the
client, and is covered by integration tests (`tests/integration/test_auth_rbac.py`).
The model is a simple ordered hierarchy (admin > operator > viewer), so anything
needing finer-grained or resource-scoped permissions (e.g. "owns this asset")
would need to grow beyond the current `can_act_as` rank check.

---

## ADR-6: AI triage as an optional, flag-gated, hardened module

**Context.** The capstone feature reads the unified model and drafts an incident
root-cause hypothesis with remediation steps. It calls an external LLM with
operational data, which makes it a cost, a dependency, and a prompt-injection
surface. The product must run, demo, and pass CI with the feature off and no API
key present.

**Decision.** Keep AI triage optional and defense-in-depth hardened.

- *Flag-gated and self-disabling.* `settings.ai_active` is true only when
  `ai_triage_enabled` is set **and** an `anthropic_api_key` is present
  (`app/core/config.py`). With no key, `run_triage` persists a `disabled`
  result and records an incident event — it never raises.
- *Untrusted input, fenced.* `app/ai/context.py` builds a size-bounded,
  truncated context bundle and `render_user_message` wraps every section in
  explicit `<<<SECTION ... >>>END_SECTION` fences; the system prompt instructs
  the model to treat fenced content as data and never follow instructions inside
  it. Audit diffs expose changed field *names*, never values, to avoid leaking
  data into the prompt.
- *Untrusted output, clamped.* The model response is parsed defensively
  (`app/ai/client.py` extracts the first brace-balanced JSON object) and coerced
  through `TriageOutput.parse_clamped` (`app/ai/schema.py`), which forbids extra
  keys, clamps confidence to 0..1, caps remediation steps, and truncates strings.
- *Human in the loop.* Output is advisory only and triggers no automated action.
- *Budget guard.* A daily token budget short-circuits before the call.
- *Secrets discipline.* The API key and full prompt body are never logged; only
  coarse metadata (model, token counts) is emitted.
- *Tests never spend.* The SDK call is isolated in `AnthropicTriageClient._invoke`
  so tests monkeypatch one method with no network; seeded demo triage is marked
  `is_seeded=True` and makes no API call.

**Alternatives considered.**
- *AI always on / core dependency.* Would make the demo require a paid key and
  put an external service on the critical path of opening an incident. Rejected.
- *Trust model output and act on it.* Auto-remediation from an injectable model
  is a non-starter for an ops tool; advisory + human review is the only safe
  posture.

**Consequences.** The product is fully usable and testable with zero AI spend,
and the injection surface is narrowed at both the prompt and the parse. The cost:
real fences and clamps are mitigations, not guarantees — a determined injection
or a degraded model can still produce misleading *advice*, which is precisely why
output stays advisory and a human approves every result.

---

## ADR-7: JWT access/refresh with refresh rotation over server-side sessions

**Context.** A Next.js frontend and potentially other API clients need to
authenticate. We wanted stateless verification on the hot path without a session
lookup per request, but still the ability to revoke a leaked long-lived
credential.

**Decision.** Issue a short-lived access token plus a longer-lived refresh
token, both HS256 JWTs (`app/core/security.py`). Access tokens carry `sub`,
`role`, `type`, and a `jti` and are verified statelessly on every request in
`get_current_user`. Refresh tokens are **single-use with rotation**
(`app/services/auth_service.py`): each refresh `jti` is persisted in
`refresh_tokens`; `rotate_refresh` validates the presented token, revokes its
`jti`, and mints a brand-new pair, so a leaked refresh token is usable at most
once. Logout revokes the `jti` idempotently. Passwords are hashed with argon2id.

**Alternatives considered.**
- *Server-side sessions.* Trivial revocation, but a session-store read on every
  request and shared mutable session state across instances — overhead we did
  not want on the read-heavy CRUD path.
- *Long-lived non-rotating JWTs.* Stateless and simple, but a leaked token is
  valid until expiry with no recourse. Rotation buys revocation back.

**Consequences.** Access-token checks need no DB round trip; refresh rotation
gives us a revocation point and limits the blast radius of a stolen refresh
token. The tradeoffs are the usual JWT ones: an issued **access** token cannot
be revoked before it expires (we keep its lifetime short to bound this), and the
HMAC `secret_key` is a single critical secret that must come from the environment
and rotate carefully. The refresh table also needs periodic pruning of expired
and revoked rows.

---

## ADR-8: Data-driven compliance rule registry with severity-weighted scoring

**Context.** Pillar 2 ships a set of framework-mapped controls (encryption,
patching, identity, network, logging/backup, endpoint) and must grow over time.
Adding a control should not require touching the engine, the schema, or the
scoring math.

**Decision.** Make rules a **code-defined, self-registering registry** and keep
scoring pure and separate.

- *Registry.* `app/compliance/registry.py` defines a `@rule(...)` decorator that
  registers a check (id, title, framework, control, severity, remediation, and an
  `evaluate(asset) -> RuleEvaluation` function) into a module-level dict at
  import time. Adding a control is adding one decorated function in
  `app/compliance/rules/`; duplicate ids raise at registration. Rules are pure
  with respect to the DB — they read only the in-memory asset — and a missing
  attribute returns `not_applicable` ("cannot assess"), never a failure.
- *Scoring.* `app/compliance/scoring.py` holds framework-free math. Severity
  weights are `low=1, medium=2, high=5, critical=10`. The per-asset score is:

  ```text
  asset_score = 100 * Σ weight(passed applicable rules)
                     / Σ weight(passed + failed applicable rules)
  ```

  `not_applicable` results are excluded from both numerator and denominator; an
  asset with no applicable rule scores `100.0` (no evidence of violation, not
  penalized for missing data). The org rollup is the **unweighted mean** of
  per-asset scores, so one noisy host cannot dominate a fleet.
- *Reproducibility.* Each `ComplianceResult` denormalizes the rule's severity at
  evaluation time, so retuning a rule's severity later never rewrites historical
  run scores. Each `ComplianceRun` persists its own `org_score` and per-severity
  failing counts as a frozen drift datapoint.

**Alternatives considered.**
- *Rules as database rows / config DSL.* Editable without a deploy, but it turns
  every check into an interpreter problem and a validation surface. Python
  functions are testable, type-checked, and reviewable. We chose code; the
  `enabled` toggle still lets an operator scope a control out without deleting
  history.
- *Recompute scores on read.* Simpler storage, but historical drift would shift
  whenever rules or scoring changed. Persisting the score per run keeps drift
  honest.

**Consequences.** New controls are additive (a decorated function plus a unit
test), the scoring is isolated and heavily tested
(`tests/unit/test_scoring.py`), and drift history is immutable. The cost: because
rules live in code, *changing the rule set is a deploy*, not a config edit, and
because evidence and severity are snapshotted, the result tables grow with
`assets × rules` per run and need retention management over time.
