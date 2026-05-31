# Free-tier hosting (optional appendix)

SentryOps is **self-hosted by design**. The canonical way to run it is on your own
machine or server with `docker compose up` / `make demo`. There is intentionally no
always-on public URL in v1: that is a deliberate $0, no-account cost decision, not an
oversight. The committed screenshots and [DEMO.md](../DEMO.md) prove the workflow with
real data, and anyone can reproduce it in one command.

If you do want a hosted instance, these free tiers can work, each with caveats. None
are required, and none are wired into CI.

## Fly.io (free allowance)

Fly runs containers close to the compose model. The free allowance covers small VMs,
but Fly requires a **credit card on file** even when you stay within $0 of usage.

Sketch:

1. `fly launch --no-deploy` in `backend/` and `web/` (or use a single app per service).
2. Provision managed Postgres (`fly postgres create`) and Upstash Redis (`fly redis create`).
3. Set secrets: `fly secrets set SECRET_KEY=... DATABASE_URL=... REDIS_URL=... AI_TRIAGE_ENABLED=false`.
4. Deploy the API and worker from `backend/Dockerfile`, and the web app from `web/Dockerfile`
   with `NEXT_PUBLIC_API_URL` pointing at the API's public hostname.
5. Tighten `CORS_ORIGINS` to the web app's origin.

## Render (free web service)

Render's free web services need **no card**, but they **spin down after ~15 minutes** of
inactivity (cold start ~50s), and the free Postgres has a limited lifetime. That cold start
makes it a poor fit for a "click and it just works" demo, but it is fine for kicking the tires.

## Production hardening checklist

Wherever you deploy, before exposing it publicly:

- Generate a strong `SECRET_KEY` (`python -c "import secrets; print(secrets.token_urlsafe(48))"`).
- Set `ENVIRONMENT=production` (enables HSTS) and lock `CORS_ORIGINS` to your real origin.
- Put the API behind TLS (a reverse proxy or the platform's edge).
- Keep `AI_TRIAGE_ENABLED=false` unless you supply a key and accept the per-incident cost,
  and rate-limit or restrict the triage endpoint to operators.
- Rotate the seeded demo accounts or do not seed in production.

## Terraform / IaC

A minimal Terraform module for one-command VPS provisioning is on the [roadmap](../../README.md#roadmap),
deferred from v1 to keep the initial scope on the four pillars.
