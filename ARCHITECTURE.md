# SentryOps Architecture

SentryOps is a self-hosted IT operations command center. It collapses four disciplines that normally live in four separate tools into a single product backed by one data model: a CMDB (asset inventory plus a directed dependency graph), a security compliance engine, service observability (synthetic health checks and incidents), and AI-assisted incident triage.

## Why one data model shortens MTTR

Fragmentation is the thing that inflates mean-time-to-resolution. When an on-call engineer has to hop between a CMDB, a compliance dashboard, a status page, and a ticketing system, they spend their first minutes reconstructing context by hand: what is this asset, what depends on it, what changed recently, and is it compliant. SentryOps keeps all of that in one Postgres schema, so each pillar feeds the next:

| Pillar | What it owns | How it feeds MTTR |
|--------|--------------|-------------------|
| **CMDB** | `assets`, `tags`, `asset_dependencies`, `asset_checkouts` | The asset inventory and its directed dependency graph are the substrate for blast-radius reasoning. |
| **Compliance** | `compliance_runs`, `compliance_results`, plus the in-code rule registry | A severity-weighted org score and per-asset drift answer "is this asset in a known-bad posture" without a separate scan tool. |
| **Observability** | `services`, `health_checks`, `check_results`, `incidents`, `incident_events` | Synthetic probes detect failures and open incidents automatically, so detection is not a human step. |
| **Audit** | `audit_log` (append-only) | A single chronological "what changed" stream, queried by both compliance and triage. |
| **AI triage** | `ai_triage_results` | The capstone: it reads the unified model (asset, dependencies, recent audit, compliance failures, check history) to draft a root-cause hypothesis for a human to approve. |

Every pillar exists to shorten the path from "something broke" to "here is the likely cause and the fix." The AI layer is optional and advisory; it is flag-gated and off by default.

## System diagram

```mermaid
flowchart LR
    subgraph client["Browser"]
        web["web — Next.js 14 App Router"]
    end

    subgraph backend["Backend (FastAPI)"]
        api["api — FastAPI app\n/api/v1 + /health /ready /metrics"]
        worker["worker — scheduler thread\n+ RQ triage worker"]
        ai["app.ai — triage orchestrator\ncontext - client - schema clamp"]
    end

    subgraph data["State"]
        pg[("PostgreSQL 16")]
        redis[("Redis 7")]
    end

    anthropic["Anthropic Messages API"]
    grafana["Grafana"]

    web -->|"HTTPS JSON, Bearer JWT"| api
    api -->|"SQLAlchemy 2.0"| pg
    api -->|"enqueue triage job"| redis
    worker -->|"sync probes + writes"| pg
    worker -->|"RQ broker / consume jobs"| redis
    worker --> ai
    ai -->|"only if AI_TRIAGE_ENABLED + key"| anthropic
    api -->|"GET /metrics (Prometheus exposition)"| grafana
```

The `api` and `worker` services build from the same `backend/` image. The worker runs a scheduler thread (`app.workers.run.scheduler_loop`) alongside an RQ `Worker` consuming the `triage` queue. Redis is both the RQ broker and a rollup cache. The `/metrics` endpoint is plain Prometheus exposition (no response envelope) that a Grafana instance scrapes.

## Entity-relationship model

The ERD below reflects the real tables defined under `backend/app/models`. Primary keys are application-generated UUIDs (`UUIDMixin`); most tables carry server-managed `created_at`/`updated_at` (`TimestampMixin`), except the append-only `audit_log` and the time-series/result tables, which carry only `created_at`.

```mermaid
erDiagram
    users ||--o{ refresh_tokens : "has"
    users ||--o{ assets : "owns (owner_id, SET NULL)"
    users ||--o{ audit_log : "actor"

    assets ||--o{ asset_tags : ""
    tags ||--o{ asset_tags : ""
    assets ||--o{ asset_dependencies : "source"
    assets ||--o{ asset_dependencies : "target"
    assets ||--o{ asset_checkouts : ""
    assets ||--o{ compliance_results : ""
    assets ||--o{ services : "asset_id (SET NULL)"
    assets ||--o{ incidents : "asset_id (SET NULL)"

    compliance_runs ||--o{ compliance_results : "results"

    services ||--o{ health_checks : ""
    services ||--o{ incidents : ""
    health_checks ||--o{ check_results : ""
    health_checks ||--o{ incidents : "health_check_id (SET NULL)"

    incidents ||--o{ incident_events : "timeline"
    incidents ||--o{ ai_triage_results : "triage"

    users {
        uuid id PK
        string email UK
        string full_name
        string hashed_password
        enum role "viewer|operator|admin"
        bool is_active
        bool mfa_enabled
    }
    refresh_tokens {
        uuid id PK
        uuid user_id FK
        string jti UK
        datetime expires_at
        bool revoked
    }
    assets {
        uuid id PK
        string short_code UK
        string name
        enum asset_type
        enum lifecycle_state
        enum environment
        string location
        uuid owner_id FK
        jsonb attributes "security-posture facts"
        jsonb custom_fields
    }
    tags {
        uuid id PK
        string name UK
        string color
    }
    asset_tags {
        uuid asset_id PK_FK
        uuid tag_id PK_FK
    }
    asset_dependencies {
        uuid id PK
        uuid source_asset_id FK
        uuid target_asset_id FK
        string kind
    }
    asset_checkouts {
        uuid id PK
        uuid asset_id FK
        uuid holder_id FK
        uuid checked_out_by_id FK
        datetime checked_out_at
        datetime checked_in_at "NULL = current holder"
        string notes
    }
    audit_log {
        uuid id PK
        datetime created_at
        uuid actor_id FK
        enum action
        string entity_type
        uuid entity_id
        jsonb before
        jsonb after
        string source_ip
    }
    compliance_runs {
        uuid id PK
        datetime started_at
        datetime finished_at
        uuid triggered_by_id FK
        int total_assets
        float org_score
        int passed_count
        int failed_count
        int not_applicable_count
        jsonb severity_failing
    }
    compliance_results {
        uuid id PK
        datetime created_at
        uuid run_id FK
        uuid asset_id FK
        string rule_id
        enum status "pass|fail|not_applicable"
        enum severity "denormalized"
        jsonb evidence
    }
    services {
        uuid id PK
        string name UK
        string description
        uuid asset_id FK
        float slo_target
    }
    health_checks {
        uuid id PK
        uuid service_id FK
        string name
        enum check_type "http|tcp"
        string target
        string method
        int expected_status
        int latency_budget_ms
        int port
        int interval_seconds
        bool enabled
    }
    check_results {
        uuid id PK
        datetime created_at
        uuid health_check_id FK
        enum status "up|down"
        float latency_ms
        int status_code
        string error
    }
    incidents {
        uuid id PK
        uuid service_id FK
        uuid health_check_id FK
        uuid asset_id FK
        string title
        enum status "open|acknowledged|resolved|closed"
        enum severity
        datetime opened_at
        datetime acknowledged_at
        uuid acknowledged_by_id FK
        datetime resolved_at
        uuid resolved_by_id FK
        datetime closed_at
    }
    incident_events {
        uuid id PK
        datetime created_at
        uuid incident_id FK
        enum event_type
        string message
        uuid actor_id FK
        jsonb payload
    }
    ai_triage_results {
        uuid id PK
        datetime created_at
        uuid incident_id FK
        enum status "success|disabled|failed"
        string model
        string root_cause_hypothesis
        float confidence "0..1"
        enum severity_assessment
        jsonb remediation_steps
        string stakeholder_comms_draft
        int input_tokens
        int output_tokens
        float estimated_cost_usd
        bool is_seeded
        string error
        jsonb raw_output
    }
```

A few model facts worth calling out, because they drive behavior elsewhere:

- `assets.attributes` is the JSONB bag of security-posture facts the compliance rules read. A missing key means "cannot assess," never "non-compliant."
- `asset_dependencies` is a directed adjacency table (`source` depends on `target`) with a `UniqueConstraint(source, target)` and a `CheckConstraint(source <> target)` so an edge cannot be duplicated and an asset cannot depend on itself.
- `asset_checkouts` models check-in/out as an event log: the current holder is the row whose `checked_in_at IS NULL`.
- `compliance_results.severity` is denormalized from the rule definition so historical results survive later edits to a rule's severity.
- `incidents.asset_id` and `incidents.health_check_id` are denormalized links (both `SET NULL` on delete) so triage and blast-radius queries do not have to re-join through the service.

## Request lifecycle

Middleware is registered in `app.main.create_app`. Starlette runs middleware in reverse registration order, so the effective request path is:

```mermaid
sequenceDiagram
    participant C as Client
    participant RID as RequestIDMiddleware
    participant CORS as CORSMiddleware
    participant SEC as SecurityHeadersMiddleware
    participant R as Route handler
    participant D as Dependencies (auth, RBAC, DB)

    C->>RID: HTTP request
    RID->>RID: accept or mint X-Request-ID and bind to structlog
    RID->>CORS: forward
    CORS->>SEC: forward (origin checks)
    SEC->>R: forward
    R->>D: resolve get_current_user -> require_role -> get_db
    D-->>R: User + Session (or AppError)
    R-->>SEC: Envelope[...] JSON
    SEC->>SEC: add nosniff / DENY / Referrer-Policy / strict CSP (+ HSTS in prod)
    SEC-->>CORS: response
    CORS-->>RID: response
    RID->>RID: set X-Request-ID header and reset log context
    RID-->>C: response
```

1. **Request ID.** `RequestIDMiddleware` accepts an inbound `X-Request-ID` or mints one, stores it on `request.state.request_id`, binds it into the structlog context for the duration of the request, and echoes it back on the response header. It is the outermost middleware so every log line is tagged.
2. **CORS.** `CORSMiddleware` enforces the configured origin allowlist (`cors_origins`, default `http://localhost:3000`) and exposes `X-Request-ID`.
3. **Security headers.** `SecurityHeadersMiddleware` sets `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, a `Permissions-Policy` that disables camera/microphone/geolocation, and a strict `Content-Security-Policy` (`default-src 'none'; frame-ancestors 'none'`, because the API serves JSON only). `Strict-Transport-Security` is added only when `environment == production`.
4. **Auth dependency.** `get_current_user` (in `app/api/deps.py`) reads the bearer token, decodes it, requires `type == "access"`, parses the `sub` claim as a UUID, and loads an active `User`. Anything wrong raises `AuthError` (401).
5. **RBAC dependency.** `require_role(required)` is a dependency factory. Roles are an ordered enum (`viewer < operator < admin`) with a `can_act_as` check; mutating routes declare `RequireOperator` or `RequireAdmin`. Authorization lives at the API boundary, not the UI, so it holds regardless of the calling client.
6. **Envelope response.** Domain endpoints return `Envelope[T]` (`app/schemas/common.py`): `{ success, data, error, meta }`. List endpoints wrap `Page[T]` inside the envelope. Platform endpoints (`/health`, `/ready`, `/metrics`) intentionally bypass the envelope.
7. **Typed exceptions.** Handlers registered by `register_exception_handlers` map `AppError` subclasses (`NotFoundError` 404, `ConflictError` 409, `PermissionDeniedError` 403, `AuthError` 401, `ValidationAppError` 422, `FeatureDisabledError` 409) and FastAPI/Starlette errors onto the same error envelope, always including the request ID. The catch-all logs full context server-side and returns a generic 500 body so internal detail never leaks.

## Incident-to-AI-triage data flow

Detection and triage are fully automated up to the point of human review. The scheduler thread probes due checks; the incident service decides when to open; an RQ job builds context and calls the model; the clamped output is persisted and rendered on the incident timeline.

```mermaid
sequenceDiagram
    participant SCH as scheduler_loop (worker thread)
    participant PROBE as observability.checks
    participant OBS as observability_service
    participant INC as incident_service
    participant Q as RQ "triage" queue (Redis)
    participant JOB as run_triage_job (RQ worker)
    participant CTX as ai.context.build_context
    participant CL as AnthropicTriageClient
    participant AN as Anthropic API
    participant SCH2 as ai.schema.parse_clamped
    participant DB as Postgres
    participant UI as Incident timeline (web)

    SCH->>PROBE: run_check_sync(check) for each due check
    PROBE-->>OBS: outcome (up/down, latency, error)
    OBS->>DB: insert check_results row
    SCH->>INC: evaluate_after_result(check)
    Note over INC: open only if the most recent K results (incident_open_threshold, default 3) are all DOWN and the service has no live incident
    INC->>DB: insert incident (open) plus opened event
    INC-->>SCH: new incident id
    SCH->>Q: enqueue_triage(incident_id)
    Q->>JOB: run_triage_job(incident_id)
    JOB->>CTX: build_context(db, incident)
    CTX->>DB: asset summary, deps (depth<=2, cycle-safe), recent audit, latest-run compliance failures, recent check_results
    CTX-->>JOB: sanitized, size-bounded bundle (fenced)
    alt AI inactive (flag off or no key)
        JOB->>DB: persist AITriageResult status=disabled (no API call)
    else AI active and within daily token budget
        JOB->>CL: call(system_prompt, fenced_user_message)
        CL->>AN: messages.create (prefill open brace)
        AN-->>CL: text (untrusted)
        CL->>SCH2: extract first balanced JSON object
        SCH2-->>JOB: TriageOutput (types coerced, ranges clamped, steps capped, strings truncated)
        JOB->>DB: persist AITriageResult status=success plus tokens/cost
    end
    JOB->>DB: append ai_triaged event
    UI->>DB: GET /api/v1/incidents/{id}/triage
    Note over UI: advisory output shown for a human to approve. NO automated remediation is taken
```

Key properties of this path, verified against the code:

- **Opening is debounced.** `incident_service.evaluate_after_result` opens an incident only when the most recent `incident_open_threshold` (default 3) check results are all `down` *and* the service has no live (open or acknowledged) incident. Recovery is the mirror image: the most recent `incident_close_threshold` (default 2) results all `up` auto-resolves and closes the live incident.
- **The feature flag is a hard gate.** `Settings.ai_active` is `ai_triage_enabled AND a key is present`. When inactive, `run_triage` persists an `AITriageResult` with `status=disabled` and an explanatory `error`, records the event, and returns. It never raises and never calls the API. There is also a hard daily token budget (`ai_daily_token_budget`, default 200,000) checked before any call.
- **The model is untrusted at both ends.** Context is fenced (`<<<SECTION ... >>>END_SECTION`) and the system prompt instructs the model to treat fenced content strictly as data. The model's reply is then run through `_extract_json_object` (scan for a brace-balanced object) and `TriageOutput.parse_clamped`, which coerces types, clamps `confidence` to 0..1 and `priority` to 1..5, caps `remediation_steps` at 8, truncates long strings, and rejects irrecoverable output with `ValidationAppError`.
- **Human in the loop.** Output is advisory only. It triggers no automated action; an operator reads the timeline and decides. Seeded demo incidents carry illustrative triage flagged `is_seeded=True` so dashboards look alive with zero API spend.
- **No secrets in logs.** The Anthropic key is handed only to the SDK constructor; neither the key nor the prompt body is ever logged. On failure, the persisted `error` and the structlog line carry only the exception type and message, truncated.

## The composite indexes that matter

Two composite indexes are deliberate, because they serve the two hottest read paths in the product. Both are leading-column-narrows-then-time-orders indexes.

**`check_results (health_check_id, created_at)`** — `Index("ix_check_results_check_recent", ...)`. Every uptime and SLO computation asks the same shape of question: "all results for *this* check within the last 24h / 7d / 30d." The leading `health_check_id` narrows to a single check; the trailing `created_at` lets Postgres range-scan the time window and serve the newest-first ordering without a sort. `check_results` is the highest-write, highest-read table in the system (one row per check per interval), so this is the workhorse index. The incident open/recover logic and the triage context's recent-check lookup ride the same index.

**`audit_log (entity_type, entity_id, created_at)`** — `Index("ix_audit_entity_recent", ...)`. The audit log is append-only and grows without bound, but the two consumers that read it want only "the most recent N changes for one specific entity": the per-entity history view in the UI, and the AI context bundle's "what changed recently" section. Leading on `(entity_type, entity_id)` pins the query to one entity; the trailing `created_at` serves the `ORDER BY created_at DESC LIMIT N`. Without this composite, those reads would degrade to a scan-and-sort over an ever-growing table.

The same pattern appears on `compliance_results (asset_id, created_at)` (`ix_compliance_results_asset_recent`) for per-asset history, on `(run_id, asset_id)` for report assembly, on `incidents (status, opened_at)` for the open-incident board, and on `asset_checkouts (asset_id, checked_in_at)` for the "who currently holds asset X" lookup. The principle is consistent: put the equality-filtered columns first and the range/ordering column last.
