"""Observability analytics: record results, uptime, SLO/error budget, MTTA/MTTR.

These functions are read-mostly aggregations over the ``check_results`` and
``incidents`` tables plus a single insert path (:func:`record_check_result`).
They take a ``Session`` and never commit; callers own the transaction.

Definitions used throughout:
    * uptime  — fraction of recorded results that were UP within a window
      (0..1), defaulting to 1.0 when there is no data to judge against.
    * MTTA    — mean (acknowledged_at - opened_at) over incidents opened in the
      window that were acknowledged. Unacknowledged incidents are excluded.
    * MTTR    — mean (resolved_at - opened_at) over incidents resolved in the
      window. Still-open / never-resolved incidents are excluded.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.enums import CheckStatus, IncidentStatus
from app.models.observability import (
    CheckResult,
    HealthCheck,
    Incident,
    Service,
)
from app.observability.checks import CheckOutcome

# Window for the status grid's per-service uptime column.
_STATUS_GRID_WINDOW = timedelta(hours=24)


def _now() -> datetime:
    return datetime.now(UTC)


def record_check_result(db: Session, check: HealthCheck, outcome: CheckOutcome) -> CheckResult:
    """Persist a probe outcome as a ``CheckResult`` row (flushes; no commit)."""
    result = CheckResult(
        health_check_id=check.id,
        status=outcome.status,
        latency_ms=outcome.latency_ms,
        status_code=outcome.status_code,
        error=outcome.error,
    )
    db.add(result)
    db.flush()
    return result


def uptime_ratio(db: Session, health_check_id: uuid.UUID, window: timedelta) -> float:
    """Fraction of UP results for one check over ``window`` (0..1).

    Returns 1.0 when there is no data in the window (nothing observed yet means
    nothing is known to be down).
    """
    since = _now() - window
    total, up = db.execute(
        select(
            func.count(CheckResult.id),
            func.count(CheckResult.id).filter(CheckResult.status == CheckStatus.up),
        ).where(
            CheckResult.health_check_id == health_check_id,
            CheckResult.created_at >= since,
        )
    ).one()
    if not total:
        return 1.0
    return float(up) / float(total)


def service_uptime(db: Session, service_id: uuid.UUID, window: timedelta) -> float:
    """Aggregate uptime for a service across all its checks' results in ``window``.

    Uptime is computed over the pooled result set (every result from every check
    on the service), so a service with one flapping check among several reflects
    that proportionally. Returns 1.0 when there is no data.
    """
    since = _now() - window
    total, up = db.execute(
        select(
            func.count(CheckResult.id),
            func.count(CheckResult.id).filter(CheckResult.status == CheckStatus.up),
        )
        .join(HealthCheck, HealthCheck.id == CheckResult.health_check_id)
        .where(
            HealthCheck.service_id == service_id,
            CheckResult.created_at >= since,
        )
    ).one()
    if not total:
        return 1.0
    return float(up) / float(total)


def error_budget(slo_target: float, observed_uptime: float) -> dict[str, float]:
    """Compute SLO error-budget figures from a target and observed uptime.

    Returns a dict with:
        budget     — allowed unavailability fraction (1 - slo_target).
        consumed   — unavailability actually observed (1 - observed_uptime),
                     never negative.
        burn_rate  — consumed / budget; 0.0 when the budget is zero (a 100% SLO
                     has no budget to burn against, so we report 0.0 rather than
                     dividing by zero).
        remaining  — budget - consumed (may be negative when the SLO is breached).
    """
    budget = max(0.0, 1.0 - slo_target)
    consumed = max(0.0, 1.0 - observed_uptime)
    burn_rate = consumed / budget if budget > 0 else 0.0
    remaining = budget - consumed
    return {
        "budget": budget,
        "consumed": consumed,
        "burn_rate": burn_rate,
        "remaining": remaining,
    }


def _mean_seconds(deltas: list[float]) -> float | None:
    return sum(deltas) / len(deltas) if deltas else None


def _incidents_in_window(window: timedelta | None) -> Select[tuple[Incident]]:
    """Base select for incidents opened within ``window`` (all-time when None)."""
    stmt = select(Incident)
    if window is not None:
        stmt = stmt.where(Incident.opened_at >= _now() - window)
    return stmt


def compute_mtta_mttr(
    db: Session, window: timedelta | None = None
) -> tuple[float | None, float | None]:
    """Return (MTTA seconds, MTTR seconds) over incidents opened in ``window``.

    ``window=None`` means all-time. Each metric is ``None`` when no incident
    qualifies for it:
        * MTTA averages ``acknowledged_at - opened_at`` only over acknowledged
          incidents; unacknowledged (including still-open) incidents are skipped.
        * MTTR averages ``resolved_at - opened_at`` only over resolved incidents;
          still-open / unresolved incidents are skipped.
    """
    incidents = db.execute(_incidents_in_window(window)).scalars().all()

    ack_deltas: list[float] = []
    resolve_deltas: list[float] = []
    for incident in incidents:
        if incident.acknowledged_at is not None:
            ack_deltas.append((incident.acknowledged_at - incident.opened_at).total_seconds())
        if incident.resolved_at is not None:
            resolve_deltas.append((incident.resolved_at - incident.opened_at).total_seconds())

    return _mean_seconds(ack_deltas), _mean_seconds(resolve_deltas)


def _latest_status_for_check(db: Session, health_check_id: uuid.UUID) -> CheckStatus | None:
    """Most recent recorded status for a single check, or None if never run."""
    return db.execute(
        select(CheckResult.status)
        .where(CheckResult.health_check_id == health_check_id)
        .order_by(CheckResult.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _open_incident_count(db: Session, service_id: uuid.UUID) -> int:
    count = db.execute(
        select(func.count(Incident.id)).where(
            Incident.service_id == service_id,
            Incident.status.in_((IncidentStatus.open, IncidentStatus.acknowledged)),
        )
    ).scalar_one()
    return int(count or 0)


def status_grid(db: Session) -> list[dict[str, Any]]:
    """Per-service current health: derived status + 24h uptime + open incidents.

    A service is DOWN if any of its enabled checks' latest result is DOWN;
    otherwise UP (a service with no results yet is treated as UP since nothing
    is known to be failing). Returned dicts match ``StatusGridItem``.
    """
    services = db.execute(select(Service).order_by(Service.name)).scalars().all()

    grid: list[dict[str, Any]] = []
    for service in services:
        checks = (
            db.execute(select(HealthCheck).where(HealthCheck.service_id == service.id))
            .scalars()
            .all()
        )

        derived = CheckStatus.up
        last_checked_at: datetime | None = None
        for check in checks:
            latest = db.execute(
                select(CheckResult)
                .where(CheckResult.health_check_id == check.id)
                .order_by(CheckResult.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if latest is None:
                continue
            if last_checked_at is None or latest.created_at > last_checked_at:
                last_checked_at = latest.created_at
            if check.enabled and latest.status == CheckStatus.down:
                derived = CheckStatus.down

        grid.append(
            {
                "service_id": service.id,
                "service_name": service.name,
                "asset_id": service.asset_id,
                "status": derived,
                "uptime_24h": service_uptime(db, service.id, _STATUS_GRID_WINDOW),
                "slo_target": service.slo_target,
                "check_count": len(checks),
                "open_incidents": _open_incident_count(db, service.id),
                "last_checked_at": last_checked_at,
            }
        )
    return grid
