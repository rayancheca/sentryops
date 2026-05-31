<!--
Thanks for contributing to SentryOps. Keep PRs focused; split unrelated changes.
-->

## Summary

What does this PR change, and why? One or two sentences.

Closes #

## Type of change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] Feature (non-breaking change that adds capability)
- [ ] Breaking change (fix or feature that changes existing behavior or API contract)
- [ ] Refactor / internal (no behavior change)
- [ ] Docs / chore / CI

## Affected area

- [ ] CMDB / assets
- [ ] Compliance
- [ ] Observability / incidents
- [ ] AI triage
- [ ] Auth / RBAC
- [ ] Metrics / Grafana
- [ ] Frontend (web)
- [ ] Infra / Docker / migrations

## How it was tested

Describe what you ran and what you observed. Reference specific tests where
relevant.

- [ ] `make test` (backend pytest + frontend unit tests)
- [ ] `make lint` (ruff + black + eslint)
- [ ] `make typecheck` (mypy strict + tsc)
- [ ] Manually verified against a fresh `make demo`
- [ ] Visual / responsive check (frontend changes)

## Checklist

- [ ] Mutating endpoints declare the correct minimum role (`Require*`) and the
      transaction is committed at the route, not the service.
- [ ] State changes write an audit record in the same transaction.
- [ ] No secrets, tokens, or prompt bodies are logged.
- [ ] If the model output or AI context changed, the clamping/fencing safeguards
      still hold.
- [ ] Added or updated tests; coverage stays at or above target.
- [ ] Added a database migration if the schema changed.
- [ ] Updated `CHANGELOG.md` under `[Unreleased]`.
- [ ] Updated docs (DEMO, API, ADR) if behavior or contract changed.

## Screenshots / output

For UI changes, attach before/after screenshots. For API changes, paste a sample
request/response envelope.

## Notes for reviewers

Anything that needs extra eyes: a tradeoff you made, a risky migration, or a
follow-up you intentionally deferred.
