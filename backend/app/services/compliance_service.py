"""Compliance evaluation, persistence, drift, and reporting.

The service owns the orchestration around the pure pieces:

* it walks every *active* asset (retired/disposed assets are out of scope),
* runs every registered :class:`~app.compliance.registry.Rule`,
* persists one :class:`~app.models.compliance.ComplianceResult` per
  (asset, rule) — denormalising severity so historical results survive rule
  edits,
* computes per-asset scores via :func:`app.compliance.scoring.asset_score` and
  an org rollup via :func:`app.compliance.scoring.org_rollup`,
* writes a :class:`~app.models.compliance.ComplianceRun` snapshot (each run is
  one drift datapoint), and
* records an audit entry for the run.

Reads (results, latest run, drift series, newly-failing diff, audit report) are
plain ORM queries layered on top of those snapshots.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.compliance.registry import Rule, get_rule, get_rules
from app.compliance.scoring import (
    aggregate_status_counts,
    asset_score,
    org_rollup,
    severity_failing_counts,
)
from app.models.asset import Asset
from app.models.compliance import ComplianceResult, ComplianceRun
from app.models.enums import (
    AuditAction,
    ComplianceStatus,
    LifecycleState,
    Severity,
)
from app.models.user import User
from app.services.audit_service import record_audit

# Lifecycle states excluded from evaluation (no longer operationally relevant).
_OUT_OF_SCOPE_STATES = (LifecycleState.retired, LifecycleState.disposed)

# Default number of recent runs returned by the drift series.
DEFAULT_DRIFT_LIMIT = 20


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #
def _active_assets(db: Session) -> list[Asset]:
    """Load in-scope assets with their owner eagerly loaded (owner-MFA rule)."""
    stmt = (
        select(Asset)
        .where(Asset.lifecycle_state.notin_(_OUT_OF_SCOPE_STATES))
        .options(selectinload(Asset.owner))
        .order_by(Asset.created_at)
    )
    return list(db.scalars(stmt).all())


def run_evaluation(db: Session, triggered_by: User | None) -> ComplianceRun:
    """Evaluate every active asset against all rules and persist a run snapshot.

    Caller owns the transaction boundary; this flushes but does not commit.
    """
    rules = get_rules()
    assets = _active_assets(db)

    run = ComplianceRun(
        started_at=datetime.now(tz=UTC),
        triggered_by_id=triggered_by.id if triggered_by is not None else None,
        total_assets=len(assets),
    )
    db.add(run)
    db.flush()  # assign run.id before attaching result rows

    per_asset_scores: list[float] = []
    all_statuses: list[ComplianceStatus] = []
    failing_for_counts: list[tuple[Severity, ComplianceStatus]] = []

    for asset in assets:
        asset_evals: list[tuple[Severity, ComplianceStatus]] = []
        for rule in rules:
            evaluation = rule.evaluate(asset)
            result = ComplianceResult(
                run_id=run.id,
                asset_id=asset.id,
                rule_id=rule.id,
                status=evaluation.status,
                severity=rule.severity,
                evidence=evaluation.evidence or None,
            )
            db.add(result)
            asset_evals.append((rule.severity, evaluation.status))
            all_statuses.append(evaluation.status)
            failing_for_counts.append((rule.severity, evaluation.status))
        per_asset_scores.append(asset_score(asset_evals))

    status_counts = aggregate_status_counts(all_statuses)
    run.org_score = org_rollup(per_asset_scores)
    run.passed_count = status_counts[ComplianceStatus.passed.value]
    run.failed_count = status_counts[ComplianceStatus.failed.value]
    run.not_applicable_count = status_counts[ComplianceStatus.not_applicable.value]
    run.severity_failing = severity_failing_counts(failing_for_counts)
    run.finished_at = datetime.now(tz=UTC)
    db.flush()

    record_audit(
        db,
        action=AuditAction.create,
        entity_type="compliance_run",
        entity_id=run.id,
        actor_id=triggered_by.id if triggered_by is not None else None,
        after={
            "org_score": run.org_score,
            "total_assets": run.total_assets,
            "passed_count": run.passed_count,
            "failed_count": run.failed_count,
            "not_applicable_count": run.not_applicable_count,
            "severity_failing": run.severity_failing,
        },
    )
    return run


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #
def latest_run(db: Session) -> ComplianceRun | None:
    """The most recent run by ``started_at`` (None when nothing has run yet)."""
    stmt = select(ComplianceRun).order_by(ComplianceRun.started_at.desc()).limit(1)
    return db.scalars(stmt).first()


def _previous_run(db: Session, before: ComplianceRun) -> ComplianceRun | None:
    """The run immediately preceding ``before`` chronologically."""
    stmt = (
        select(ComplianceRun)
        .where(ComplianceRun.started_at < before.started_at)
        .order_by(ComplianceRun.started_at.desc())
        .limit(1)
    )
    return db.scalars(stmt).first()


def get_results(
    db: Session,
    run_id: uuid.UUID | None = None,
    asset_id: uuid.UUID | None = None,
) -> list[ComplianceResult]:
    """Fetch result rows, optionally scoped to a run and/or an asset.

    When ``run_id`` is omitted, the latest run is used so callers get the
    current picture by default; if no run exists the result is empty.
    """
    if run_id is None:
        current = latest_run(db)
        if current is None:
            return []
        run_id = current.id

    stmt = select(ComplianceResult).where(ComplianceResult.run_id == run_id)
    if asset_id is not None:
        stmt = stmt.where(ComplianceResult.asset_id == asset_id)
    stmt = stmt.order_by(ComplianceResult.asset_id, ComplianceResult.rule_id)
    return list(db.scalars(stmt).all())


def drift_series(db: Session, limit: int = DEFAULT_DRIFT_LIMIT) -> list[dict[str, Any]]:
    """Org-score-over-time series, oldest-first, of the last ``limit`` runs.

    Each point is ``{run_id, org_score, started_at, severity_failing}``. We
    fetch newest-first to honour ``limit``, then reverse so a chart reads left
    (older) to right (newer).
    """
    bounded = max(1, min(limit, 200))
    stmt = select(ComplianceRun).order_by(ComplianceRun.started_at.desc()).limit(bounded)
    runs = list(db.scalars(stmt).all())
    runs.reverse()
    return [
        {
            "run_id": run.id,
            "org_score": run.org_score,
            "started_at": run.started_at,
            "severity_failing": run.severity_failing or {},
        }
        for run in runs
    ]


def newly_failing(db: Session) -> list[dict[str, Any]]:
    """(asset_id, rule_id) pairs failing in the latest run but not the previous.

    "Newly failing" is defined precisely as the set difference of failing
    (asset, rule) keys: present-and-failing in the latest run minus
    present-and-failing in the immediately preceding run. A pair that was
    not_applicable or absent before and now fails counts as newly failing; a
    pair that was already failing does not.
    """
    current = latest_run(db)
    if current is None:
        return []
    previous = _previous_run(db, current)

    current_results = get_results(db, run_id=current.id)
    current_failing = {
        (r.asset_id, r.rule_id): r for r in current_results if r.status is ComplianceStatus.failed
    }

    previous_failing_keys: set[tuple[uuid.UUID, str]] = set()
    if previous is not None:
        previous_failing_keys = {
            (r.asset_id, r.rule_id)
            for r in get_results(db, run_id=previous.id)
            if r.status is ComplianceStatus.failed
        }

    items: list[dict[str, Any]] = []
    for (asset_id, rule_id), result in current_failing.items():
        if (asset_id, rule_id) in previous_failing_keys:
            continue
        rule = get_rule(rule_id)
        items.append(
            {
                "asset_id": asset_id,
                "rule_id": rule_id,
                "severity": result.severity,
                "title": rule.title if rule else rule_id,
                "control": rule.control if rule else "",
            }
        )
    items.sort(key=lambda i: (str(i["asset_id"]), i["rule_id"]))
    return items


# --------------------------------------------------------------------------- #
# Audit-ready report
# --------------------------------------------------------------------------- #
def _rule_meta(rule_id: str) -> tuple[str, str, str, str]:
    """(title, framework, control, remediation) for a rule id, with fallbacks."""
    rule: Rule | None = get_rule(rule_id)
    if rule is None:
        return (rule_id, "", "", "")
    return (rule.title, rule.framework, rule.control, rule.remediation)


def report(db: Session, run_id: uuid.UUID | None = None) -> dict[str, Any]:
    """Assemble a structured, audit-ready report for a run (latest by default).

    Returns org score, status + per-severity tallies, a per-asset breakdown
    (score and pass/fail/NA counts), and the failing controls with their
    framework control references and remediation guidance.
    """
    run = db.get(ComplianceRun, run_id) if run_id is not None else latest_run(db)
    if run is None:
        # No run exists: return a well-formed empty report rather than raising,
        # so the UI can render an "awaiting first scan" state.
        return {
            "run_id": None,
            "generated_for": datetime.now(tz=UTC),
            "org_score": 100.0,
            "total_assets": 0,
            "status_counts": aggregate_status_counts([]),
            "severity_failing": severity_failing_counts([]),
            "per_asset": [],
            "failing_controls": [],
        }

    results = get_results(db, run_id=run.id)

    per_asset: dict[uuid.UUID, dict[str, Any]] = {}
    failing_controls: list[dict[str, Any]] = []

    for r in results:
        bucket = per_asset.setdefault(
            r.asset_id,
            {
                "asset_id": r.asset_id,
                "evals": [],
                "passed": 0,
                "failed": 0,
                "not_applicable": 0,
            },
        )
        bucket["evals"].append((r.severity, r.status))
        if r.status is ComplianceStatus.passed:
            bucket["passed"] += 1
        elif r.status is ComplianceStatus.failed:
            bucket["failed"] += 1
            title, framework, control, remediation = _rule_meta(r.rule_id)
            failing_controls.append(
                {
                    "asset_id": r.asset_id,
                    "rule_id": r.rule_id,
                    "title": title,
                    "framework": framework,
                    "control": control,
                    "severity": r.severity.value,
                    "remediation": remediation,
                    "evidence": r.evidence or {},
                }
            )
        else:
            bucket["not_applicable"] += 1

    per_asset_payload: list[dict[str, Any]] = []
    for asset_id, bucket in per_asset.items():
        per_asset_payload.append(
            {
                "asset_id": asset_id,
                "score": asset_score(bucket["evals"]),
                "passed": bucket["passed"],
                "failed": bucket["failed"],
                "not_applicable": bucket["not_applicable"],
            }
        )
    per_asset_payload.sort(key=lambda a: a["score"])

    failing_controls.sort(
        key=lambda c: (-Severity(c["severity"]).weight, str(c["asset_id"]), c["rule_id"])
    )

    return {
        "run_id": run.id,
        "generated_for": datetime.now(tz=UTC),
        "org_score": run.org_score,
        "total_assets": run.total_assets,
        "status_counts": {
            ComplianceStatus.passed.value: run.passed_count,
            ComplianceStatus.failed.value: run.failed_count,
            ComplianceStatus.not_applicable.value: run.not_applicable_count,
        },
        "severity_failing": run.severity_failing or severity_failing_counts([]),
        "per_asset": per_asset_payload,
        "failing_controls": failing_controls,
    }
