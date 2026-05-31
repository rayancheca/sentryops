---
name: Bug report
about: Report a defect in SentryOps
title: "[Bug]: "
labels: ["bug", "needs-triage"]
assignees: []
---

## Summary

A clear, one-sentence description of what is wrong.

## Affected area

Which pillar or surface is impacted? (check all that apply)

- [ ] CMDB / assets
- [ ] Compliance
- [ ] Observability / incidents
- [ ] AI triage
- [ ] Auth / RBAC
- [ ] Metrics / Grafana
- [ ] Frontend (web)
- [ ] Infra / Docker / migrations

## Steps to reproduce

1. Go to '...'
2. Run / click '...'
3. See error

Start from a clean seed where possible: `make nuke && make demo`.

## Expected behavior

What you expected to happen.

## Actual behavior

What actually happened. Include the exact error message and the response
envelope if it was an API call.

## Affected endpoint or screen

- Route / URL:
- HTTP method (if API):
- Role used (viewer / operator / admin):

## Logs and evidence

```
Paste relevant API logs, worker logs, or browser console output here.
Scrub any secrets, tokens, or real customer data first.
```

## Environment

- SentryOps version / commit:
- How it was started (`make demo`, `make up`, manual):
- OS / Docker version:
- Browser (for frontend bugs):
- AI triage enabled? (yes / no)

## Additional context

Anything else that helps — screenshots, related issues, recent changes.
