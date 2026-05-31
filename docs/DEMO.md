# SentryOps — Demo Golden Path

This is the click-path to record a short demo GIF. It walks the four pillars
(CMDB, compliance, observability, AI incident triage) end to end against real,
seeded data. Every number on screen is computed by the backend from the seed
fixture, not hardcoded in the UI.

The seed fixture (`scripts/seed.py`) is deterministic (`random.seed(7)`), so the
service-status wall, the failing Billing incident, the AI triage hypothesis, the
compliance score, and the drift series look the same on every fresh run.

---

## 0. Bring the stack up and seed it

```bash
make demo
```

`make demo` builds and starts Postgres, Redis, the API, the RQ worker, and the
web app; waits for `GET /health` to go green; then runs `python -m scripts.seed`.
When it finishes it prints:

```
SentryOps is live and seeded:
  Dashboard : http://localhost:3000
  API docs  : http://localhost:8000/docs
  Login     : admin@sentryops.local / admin12345   (read-only: viewer@sentryops.local / viewer12345)
```

Point out: one command brings up the full stack with realistic data. AI triage
is OFF by default (no API key required to demo); the failing Billing incident
ships with a clearly-labelled illustrative triage result so the AI panel is
populated without spending a token.

---

## 1. Log in as admin

Open `http://localhost:3000`. You land on the login screen.

- Email: `admin@sentryops.local`
- Password: `admin12345`

Point out: there is also a read-only **viewer** account
(`viewer@sentryops.local` / `viewer12345`). Roles are enforced at the API
boundary (`require_role` in `app/api/deps.py`), not in the UI, so the viewer
physically cannot acknowledge, resolve, run a scan, or mutate an asset even if
they hit the API directly. Mention you will come back to that at the end.

---

## 2. Land on the NOC dashboard (Operations Overview)

After login you are on the dashboard at `/dashboard`. This is the operator's
hero screen, laid out bento-style. Let everything finish loading.

Point out, top to bottom:

- **Top metric row (five stats):** Open Incidents, MTTR, MTTA, Compliance score
  (with a score ring), and Total Assets. These come from
  `/incidents?status=open`, `/incidents/metrics/mtta-mttr`, `/compliance/score`,
  and `/assets`. With the seed fixture you should see **1 open incident**, a
  non-empty MTTA/MTTR (computed from the two resolved seed incidents), a
  compliance score in the low-to-mid range, and ~30 assets.
- **Service Status wall:** one tile per service with a live UP/DOWN dot, 24h
  uptime, SLO target, and open-incident count. The **Billing Service** tile is
  DOWN and pulsing; everything else is UP. This panel auto-refreshes every 30s.
- **Compliance Drift chart:** org compliance score over time, drawn from the
  historical run snapshots in the seed.
- **Open Incidents feed (bottom):** the single open critical, *Billing Service
  is failing health checks*.

Point out: the dashboard fans out all of these requests in parallel via SWR.
The MTTA/MTTR numbers are real definitions, not vanity counters — see step 5.

---

## 3. Open the failing Billing incident and read the AI triage

The polished incident-detail screen is served by the API; drive the lifecycle
through the interactive API docs so the GIF shows the real payloads.

Open `http://localhost:8000/docs` in a second tab (keep the dashboard tab open).

1. **Authorize.** `POST /api/v1/auth/login` with the admin credentials, copy the
   `access_token`, click **Authorize**, paste it.
2. **Find the incident.** `GET /api/v1/incidents?status=open`. Copy the `id` of
   *Billing Service is failing health checks* (severity `critical`,
   status `open`).
3. **Read the AI triage.** `GET /api/v1/incidents/{incident_id}/triage`. Expand
   the response and read it aloud:
   - **`root_cause_hypothesis`** — the model ties the outage to a recent
     `postgres-primary` config change (`max_connections` lowered 500 → 120 about
     three hours ago) recorded in the audit log, exhausting Billing's connection
     pool.
   - **`remediation_steps`** — ordered, priority-ranked, advisory actions
     (revert the change, restart workers, verify Postgres health).
   - **`stakeholder_comms_draft`** — a calm, blame-free status update ready to
     paste into a channel.
   - **`confidence`** (0.72) and **`severity_assessment`** (`critical`).
   - **`is_seeded: true`** — this particular result is the illustrative seed, so
     the demo works with AI disabled. With a real key and `ai_triage_enabled`,
     `POST /api/v1/incidents/{incident_id}/triage/run` produces a live result
     using the same schema and the same prompt-injection-hardened path.

Point out: the triage context is assembled from the dependency graph, the audit
log, current compliance failures, and recent check results
(`app/ai/context.py`). That is *why* it can reference the `postgres-primary`
change — Billing depends on `postgres-primary` in the seeded topology, and the
config change is a real audit entry. The output is advisory only; nothing is
executed automatically.

---

## 4. Acknowledge, then resolve — and watch MTTR update

Still in the API docs, with the same incident id:

1. **Acknowledge.** `POST /api/v1/incidents/{incident_id}/acknowledge`. The
   response flips `status` to `acknowledged` and stamps `acknowledged_at` /
   `acknowledged_by_id`. This is operator-gated and writes an immutable audit
   entry.
2. **(Optional) Comment.** `POST /api/v1/incidents/{incident_id}/comment` with a
   short message to show the incident timeline growing.
3. **Resolve.** `POST /api/v1/incidents/{incident_id}/resolve`. The response
   flips `status` to `closed` and stamps `resolved_at` / `resolved_by_id`.

Now switch back to the dashboard tab and reload (or wait for the 30s status
refresh):

- **Open Incidents** drops from 1 to **0** and the feed shows the
  "No open incidents" empty state.
- The **Billing Service** tile is no longer counted as having an open incident.
- **MTTR / MTTA** shift, because the incident you just acknowledged and resolved
  now contributes its `acknowledged_at − opened_at` and `resolved_at − opened_at`
  deltas to the rolling means.

Point out: ack and resolve are real state transitions through
`incident_service.py`, each wrapped in an audit record (`state_change`). The
metric movement is the proof the loop is closed — you fixed a real incident and
the operations math reflects it.

---

## 5. What MTTA and MTTR actually mean (say this on camera)

- **MTTA** = mean of `acknowledged_at − opened_at` over incidents *that were
  acknowledged* in the window. Unacknowledged incidents are excluded.
- **MTTR** = mean of `resolved_at − opened_at` over incidents *that were
  resolved* in the window. Still-open incidents are excluded.

Both are computed in `observability_service.compute_mtta_mttr`, exposed at
`/incidents/metrics/mtta-mttr`, and re-derived for Prometheus as the
`sentryops_mtta_seconds` / `sentryops_mttr_seconds` gauges over a 24h window.
Same definition everywhere.

---

## 6. Compliance — drift over time and a failing critical control

Back in the web app, click **Compliance** in the sidebar (`/compliance`).

Point out:

- **Org score + posture summary** from the latest compliance run
  (`/compliance/score`): the org score, total assets, passed / failed /
  not-applicable counts, and failing controls bucketed by severity.
- **Drift chart** (`/compliance/drift`): the org score across the historical run
  snapshots from the seed. It dips and recovers — that is configuration drift
  made visible.
- **Newly-failing / failing controls table** (`/compliance/newly-failing` and
  per-asset results): point at a **critical** failure. The seed guarantees
  critical hits such as:
  - `os-supported` (NIST SI-2) failing on `vpn-gateway-01` and `legacy-erp`
    (end-of-life OS).
  - `owner-mfa` (NIST IA-2) failing where an asset owner has MFA disabled.
  - `no-default-credentials` (NIST IA-5) failing on `redis-cache`
    (`default_credentials: true`).

Point out the scoring model: each rule carries a severity weight
(low 1, medium 2, high 5, critical 10). An asset's score is
`100 × Σ weight(passed) / Σ weight(passed + failed)`; not-applicable rules are
excluded entirely (a missing attribute is "cannot assess", never an automatic
fail). The org score is the unweighted mean of per-asset scores, so one noisy
host cannot dominate the fleet. This is the same math a human auditor would
defend, and the evidence dict on each result records the observed value versus
the threshold.

If you want to show drift moving live: `POST /api/v1/compliance/runs` (operator+)
triggers a fresh evaluation and appends a new point to the drift series.

---

## 7. Assets — inventory, dependency graph, and QR labels

Click **Assets** in the sidebar (`/assets`).

Point out:

- The **inventory table**: ~30 assets across hosts, services, network devices,
  cloud resources, and software licenses, with type / environment / lifecycle
  filters that live in the URL (shareable, back-button safe), full-text search,
  and CSV **Import** / **Export**.
- Each row shows the human-friendly **short code** (e.g. `SER-…`, `HOS-…`) that
  is printed on the asset's QR label.

Asset detail brings together the **dependency graph** and the **QR label**:

- The **dependency graph** is served by `/api/v1/dependencies/graph/{asset_id}`
  — the directed "source depends on target" topology around an asset, traversed
  up and down. This is the same graph the AI triage walks to reason about blast
  radius. To show it raw on camera, call that endpoint in the API docs for the
  `billing-service` asset and point out its edge to `postgres-primary` — the
  exact dependency the AI triage blamed in step 3.
- The **QR label** is generated on demand at `/api/v1/assets/{asset_id}/qr.png`
  (and `.svg`); it encodes the asset's short code so a tech can scan a physical
  rack tag and pull the record. Open the PNG endpoint to show it in the GIF.

Point out the through-line: the dependency graph and the append-only audit log
are not just CMDB features — they are the structured context that lets the AI
triage in step 3 name a specific upstream cause instead of guessing.

---

## 8. Close on RBAC (read-only viewer)

Log out and log back in as the **viewer** (`viewer@sentryops.local` /
`viewer12345`).

Point out: the viewer sees the same dashboards, compliance posture, assets, and
incident detail — full read access — but every privileged action is refused. In
the API docs, authorizing as the viewer and calling
`POST /api/v1/incidents/{incident_id}/acknowledge`,
`POST /api/v1/compliance/runs`, or `POST /api/v1/assets` returns
**403 Permission denied**. Authorization is enforced server-side via
`require_role`, so it holds no matter which client calls the API.

That is the full loop: inventory → compliance drift → live incident →
AI-assisted triage → human ack/resolve → metrics close the loop, with RBAC and
an immutable audit trail underneath all of it.
