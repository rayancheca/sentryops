# SentryOps — Interview Prep (PRIVATE)

> Private notes for the author. Not user-facing documentation. Keep this out of
> any public demo. Answers are grounded in the actual code in this repo.

## One-sentence pitch

SentryOps is a self-hosted IT operations command center that unifies a CMDB,
weighted compliance scoring, synthetic observability with auto-opened incidents,
and human-in-the-loop AI incident triage — so the same dependency graph and
immutable audit log that run your inventory also feed the AI that explains your
outages.

---

## Q1. Walk me through the architecture and the biggest tradeoff you made.

FastAPI + SQLAlchemy 2.0 (typed `Mapped[...]` models) on Postgres, Redis + RQ
for the background worker, Next.js 14 (App Router) frontend, all wired together
by Docker Compose. The backend is layered deliberately: thin API routers in
`app/api/v1/` own HTTP concerns and the transaction boundary (they call
`db.commit()`); a service layer (`app/services/`) owns business logic and
*flushes but never commits*; pure domains (`app/compliance/scoring.py`,
`app/ai/schema.py`) have zero framework or DB dependency so they unit-test in
isolation.

The biggest tradeoff: **the service layer never commits; the route does.** That
means a single request can compose several service calls into one atomic
transaction, and the audit record is written in the same transaction as the
mutation it describes — you can never end up with a state change that lacks its
audit entry, or vice versa. The cost is discipline: services must `flush()` so
callers can read generated IDs, and every router has to remember to commit. I
accepted that cost because atomicity between a mutation and its audit trail is a
hard requirement for a compliance tool, and a transaction-per-request pattern
would have forced either nested transactions or losing that guarantee.

## Q2. How is RBAC enforced, and why there?

Three roles ordered by rank: `viewer < operator < admin` (`app/models/enums.py`,
`Role.can_act_as`). Enforcement lives at the **API boundary** in
`app/api/deps.py` via a `require_role(...)` dependency factory and the
`RequireViewer` / `RequireOperator` / `RequireAdmin` aliases. Reads require any
authenticated user; mutations require operator; delete requires admin.

It is in the dependency layer, not the UI, on purpose: the frontend hiding a
button is a UX nicety, not a control. Because the check is a FastAPI dependency,
it runs for every request regardless of client, so a viewer hitting the API
directly with curl still gets a 403. Auth itself is JWT bearer: `get_current_user`
decodes the token, rejects non-`access` token types, loads the user, and refuses
inactive accounts. The demo proves it by logging in as the viewer and getting
403s on acknowledge / run-scan / create-asset.

## Q3. The AI triage takes untrusted operational data. How is it hardened against prompt injection?

This is the part I'd want a security-minded interviewer to push on, because the
threat is real: asset names, descriptions, audit entries, and check error
strings can be influenced by people other than the operator, and they all flow
into the model. Four layers, all in `app/ai/`:

1. **Fenced, labeled, untrusted-data framing.** `render_user_message` wraps every
   context section in explicit delimiters (`<<<ASSET_DATA ... >>>END_ASSET_DATA`),
   and the system prompt (`prompts/system_v1.md`) instructs the model to treat
   everything inside fences strictly as data and to *never* follow instructions
   found there — even ones disguised as system messages, role changes, or
   "ignore previous instructions". If injected text looks like a command, the
   model is told to flag it as a possible tampering signal in its analysis, not
   obey it.
2. **The output is itself untrusted.** `TriageOutput.parse_clamped` coerces types,
   clamps `confidence` to 0..1 and `priority` to 1..5, caps remediation steps at
   8, truncates long strings, maps off-spec severity labels onto the enum, and
   uses Pydantic `extra="forbid"` so the model cannot smuggle extra keys. It
   raises rather than persist garbage when there's no usable hypothesis.
3. **The output triggers no action.** It is advisory only; a human reviews every
   result. There is no code path that executes a remediation step.
4. **Secrets never leak.** The API key goes only to the SDK constructor; neither
   the key nor the prompt body is ever logged, and failure messages are scrubbed
   and truncated before they're persisted.

There are also hard safety limits independent of injection: the feature is off
unless `ai_triage_enabled` *and* a key is present, and there's a daily token
budget (`ai_daily_token_budget`, default 200k) that degrades to a persisted
`failed`/`disabled` result instead of erroring.

## Q4. Define MTTA and MTTR precisely. Where can they mislead?

- **MTTA** = mean of `acknowledged_at − opened_at`, averaged only over incidents
  that were acknowledged in the window. Unacknowledged (including still-open)
  incidents are excluded.
- **MTTR** = mean of `resolved_at − opened_at`, averaged only over incidents that
  were resolved in the window. Still-open incidents are excluded.

Single source of truth: `observability_service.compute_mtta_mttr`, reused by the
`/incidents/metrics/mtta-mttr` endpoint and the `sentryops_mtta_seconds` /
`sentryops_mttr_seconds` Prometheus gauges (24h window). The honest caveat:
because both metrics exclude incidents that haven't reached the relevant state,
they're survivorship-biased — a long-running unresolved outage *improves* MTTR
until it's finally closed, at which point it lands as one big delta. I'd pair
them with an open-incident-age panel in production so a festering incident can't
hide behind a flattering MTTR. I deliberately surface MTTR as "time to resolve"
(open→close), not "time to recover" (open→first-recovery), and documented that
in the service so nobody misreads it.

## Q5. Walk me through the compliance scoring math and why it's shaped that way.

Pure functions in `app/compliance/scoring.py`. Each rule has a severity weight:
low 1, medium 2, high 5, critical 10. Per asset:

```
asset_score = 100 × Σ weight(passed applicable) / Σ weight(passed + failed applicable)
```

Three design decisions worth defending:

- **Not-applicable is excluded from the denominator entirely.** A missing
  attribute means "cannot assess", never an automatic fail. We don't penalize an
  asset for data we simply don't have — that keeps the score honest and avoids
  punishing teams for incomplete telemetry rather than actual violations.
- **When no rule applies, the score is 100, not 0.** No evidence of a violation
  is treated as compliant. (Arguable, but penalizing "unknown" as "failing"
  would make the org score meaningless for sparsely-attributed assets.)
- **Org rollup is the *unweighted mean* of per-asset scores**, so one asset with
  twenty failing controls can't dominate a 30-asset fleet. Every asset counts
  once.

Each result also stores a denormalized severity and an evidence dict (observed
value vs. threshold) so a historical result survives later rule edits and stays
audit-defensible. Runs are immutable snapshots, which is what makes the drift
chart a true time series rather than a recomputation.

## Q6. Why $0, local-first, self-hosted?

Three reasons. First, the buyers for this kind of tool (security/ops teams) are
exactly the people who can't ship their CMDB and audit log to a third-party SaaS;
self-hosted on their own Postgres is a feature, not a limitation. Second, it
makes the project trivially demoable and reviewable — `make demo` brings up the
whole stack with realistic seeded data and no external accounts. Third, the AI is
opt-in and degrades gracefully: with no key it's simply off, and the seed ships a
clearly-labelled illustrative triage result so the AI surface is populated for
$0. When you do turn it on, you point it at your own Anthropic key with a model
choice (`anthropic_model`, default `claude-sonnet-4-6`), a per-call output cap,
and a daily token budget, so cost is bounded and visible (every triage row logs
input/output tokens and an estimated USD cost from a documented price table).

## Q7. How exactly do the dependency graph and audit log feed AI triage?

`app/ai/context.py` builds a sanitized, size-bounded bundle for the failing
asset. The dependency section does a **bidirectional, cycle-safe BFS** over
`AssetDependency` (depth ≤ 2, capped node count) to capture both what the asset
depends on and what depends on it. The audit section pulls the most recent
changes (capped at 15) for the asset *and its direct dependency neighbors* — and
critically, it sends *which fields changed*, never the values, to avoid leaking
data. Then current compliance failures and the last ~10 check results.

That's the whole trick behind the demo's "wow" moment: Billing depends on
`postgres-primary`, and a `max_connections` change to `postgres-primary` is a
real audit entry on a neighbor. Because the context walks the graph to that
neighbor and includes its recent changes, the model can name a specific upstream
root cause instead of producing generic SRE boilerplate. The graph and audit log
were built for the CMDB and compliance pillars first; making them the AI's
context was reuse, not new infrastructure.

## Q8. What's your testing strategy?

Pyramid, with the heavy logic pushed into pure functions so it's cheap to test.
Unit tests cover the scoring math (`compliance/scoring.py`), the defensive
output parsing (`ai/schema.py` — type coercion, clamping, off-spec severity,
injection-shaped extra keys), and the MTTA/MTTR/uptime/error-budget math. The AI
client isolates the actual SDK call in a single `_invoke` method specifically so
tests monkeypatch it and exercise the whole triage path — context build, prompt
render, JSON extraction, clamping, persistence, event logging — with **no
network and no key**. Integration tests hit the API with a real test DB to verify
RBAC (viewer 403s), the envelope/pagination contract, and the auto-open/recover
incident logic. The repo enforces this with `make test` (pytest + coverage),
`make lint` (ruff + black), `make typecheck` (mypy strict + tsc), and a Playwright
`capture` flow for screenshots. The `/metrics` renderer is built to be testable
too: it constructs a fresh `CollectorRegistry` per scrape and opens its own
session, so there's no global registry state to leak between tests.

## Q9. Show me something non-obvious in the implementation.

Two:

1. **Route ordering in `incidents.py`.** The static-prefix routes
   (`/incidents/metrics/mtta-mttr`, `/incidents/assets/{asset_id}`) are declared
   *before* the parameterized `/{incident_id}` route, with a comment saying why:
   otherwise FastAPI would match `/incidents/metrics/mtta-mttr` against the UUID
   path param and 422 on "metrics" not being a UUID. It's a small thing that
   bites everyone once.
2. **JSON extraction from the model is brace-balanced, not `json.loads`.** Even
   with a `{` prefill to steer the model, `app/ai/client.py` doesn't trust the
   response to be clean JSON — `_scan_balanced_object` walks the string tracking
   string/escape state and returns the first balanced object, so trailing prose
   or a markdown fence can't break parsing. The model is untrusted at every hop:
   the prompt, the transport parse, and the schema clamp.

## Q10. What would you do next?

In priority order:

1. **Build out the incident-detail and asset-detail *pages*.** The backend
   endpoints and the React components (`asset-qr.tsx`, `dependency-graph.tsx`,
   the incident lifecycle actions) all exist; today the demo drives incident
   ack/resolve and the dependency-graph/QR through the API docs. Wiring the
   `/incidents/{id}` and `/assets/{id}` routes is the highest-leverage UI gap.
2. **Real synthetic probes on a schedule.** The worker + auto-open/recover logic
   is there; the next step is the RQ scheduler running HTTP/TCP checks on each
   check's `interval_seconds` against real targets, so incidents open from live
   data rather than seeded history.
3. **Live AI triage in CI-safe form** with response caching keyed on the context
   bundle hash, so repeated triage of an unchanged incident doesn't re-spend
   tokens (the `force` flag in `run_triage` is the seam I left for this).
4. **Alerting + on-call routing** off the same incident events, and an
   open-incident-age panel to counter the MTTR survivorship bias from Q4.
5. **Compliance frameworks as data** — the rules already carry framework/control
   references (NIST 800-53, CIS); exposing framework-grouped coverage reports is
   a natural extension of the existing registry.
