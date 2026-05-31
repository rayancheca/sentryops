"""Incident lifecycle: auto open/recover from check results, ack, resolve, comment.

The auto open/recover logic in :func:`evaluate_after_result` is the bridge from
the synthetic-monitoring layer (check results) to operator-facing incidents:

    * Open  — the most recent ``incident_open_threshold`` results for a check are
      all DOWN and the service has no live (open/acknowledged) incident.
    * Recover — the most recent ``incident_close_threshold`` results are all UP
      and a live incident exists; we mark it recovered + resolved + closed.

All mutators flush (so callers can read generated ids) but never commit; the
route owns the transaction and calls ``record_audit`` for the human-initiated
state changes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.enums import (
    CheckStatus,
    IncidentEventType,
    IncidentStatus,
    Severity,
)
from app.models.observability import (
    CheckResult,
    HealthCheck,
    Incident,
    IncidentEvent,
)
from app.models.user import User

# Statuses that mean "this incident is still demanding attention"; a service may
# only have one of these at a time, so we never open a duplicate.
_LIVE_STATUSES: tuple[IncidentStatus, ...] = (
    IncidentStatus.open,
    IncidentStatus.acknowledged,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _recent_statuses(db: Session, health_check_id: uuid.UUID, n: int) -> list[CheckStatus]:
    """Return the statuses of the most recent ``n`` results, newest first."""
    rows = db.execute(
        select(CheckResult.status)
        .where(CheckResult.health_check_id == health_check_id)
        .order_by(CheckResult.created_at.desc())
        .limit(n)
    ).all()
    return [row[0] for row in rows]


def _live_incident_for_service(db: Session, service_id: uuid.UUID) -> Incident | None:
    """The current open/acknowledged incident for a service, if any."""
    return db.execute(
        select(Incident)
        .where(
            Incident.service_id == service_id,
            Incident.status.in_(_LIVE_STATUSES),
        )
        .order_by(Incident.opened_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def record_event(
    db: Session,
    incident: Incident,
    event_type: IncidentEventType,
    message: str | None = None,
    actor_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> IncidentEvent:
    """Append an event to an incident's timeline (flushes; no commit)."""
    event = IncidentEvent(
        incident_id=incident.id,
        event_type=event_type,
        message=message,
        actor_id=actor_id,
        payload=payload,
    )
    db.add(event)
    db.flush()
    return event


def evaluate_after_result(db: Session, check: HealthCheck) -> Incident | None:
    """Open or recover an incident based on this check's most recent results.

    Returns the newly opened :class:`Incident` when one is created, otherwise
    ``None`` (including on recovery, where the live incident is closed out).
    """
    settings = get_settings()
    service = check.service

    # --- Recovery: most recent M results all UP closes a live incident. ----
    live = _live_incident_for_service(db, check.service_id)
    if live is not None:
        recent_up = _recent_statuses(db, check.id, settings.incident_close_threshold)
        if len(recent_up) >= settings.incident_close_threshold and all(
            status == CheckStatus.up for status in recent_up
        ):
            now = _now()
            live.resolved_at = now
            live.closed_at = now
            live.status = IncidentStatus.closed
            db.add(live)
            record_event(db, live, IncidentEventType.recovered, message="Check recovered.")
            record_event(db, live, IncidentEventType.resolved, message="Auto-resolved on recovery.")
            record_event(db, live, IncidentEventType.closed, message="Auto-closed on recovery.")
            db.flush()
        return None

    # --- Open: most recent K results all DOWN with no live incident. --------
    recent_down = _recent_statuses(db, check.id, settings.incident_open_threshold)
    if len(recent_down) >= settings.incident_open_threshold and all(
        status == CheckStatus.down for status in recent_down
    ):
        service_name = service.name if service is not None else "service"
        incident = Incident(
            service_id=check.service_id,
            health_check_id=check.id,
            asset_id=service.asset_id if service is not None else None,
            title=f"{service_name}: {check.name} failing",
            status=IncidentStatus.open,
            severity=Severity.high,
            opened_at=_now(),
        )
        db.add(incident)
        db.flush()
        record_event(
            db,
            incident,
            IncidentEventType.opened,
            message=(
                f"Opened after {settings.incident_open_threshold} consecutive "
                f"DOWN results for check '{check.name}'."
            ),
            payload={
                "health_check_id": str(check.id),
                "threshold": settings.incident_open_threshold,
            },
        )
        db.flush()
        return incident

    return None


def acknowledge_incident(db: Session, incident: Incident, actor: User) -> Incident:
    """Mark an incident acknowledged by ``actor`` (idempotent on timestamp)."""
    if incident.acknowledged_at is None:
        incident.acknowledged_at = _now()
    incident.acknowledged_by_id = actor.id
    incident.status = IncidentStatus.acknowledged
    db.add(incident)
    record_event(
        db,
        incident,
        IncidentEventType.acknowledged,
        message=f"Acknowledged by {actor.email}.",
        actor_id=actor.id,
    )
    db.flush()
    return incident


def resolve_incident(db: Session, incident: Incident, actor: User) -> Incident:
    """Resolve and close an incident by ``actor``."""
    now = _now()
    if incident.resolved_at is None:
        incident.resolved_at = now
    incident.resolved_by_id = actor.id
    incident.closed_at = now
    incident.status = IncidentStatus.closed
    db.add(incident)
    record_event(
        db,
        incident,
        IncidentEventType.resolved,
        message=f"Resolved by {actor.email}.",
        actor_id=actor.id,
    )
    record_event(
        db,
        incident,
        IncidentEventType.closed,
        message=f"Closed by {actor.email}.",
        actor_id=actor.id,
    )
    db.flush()
    return incident


def add_comment(db: Session, incident: Incident, actor: User, message: str) -> IncidentEvent:
    """Append an operator comment to an incident's timeline."""
    return record_event(
        db,
        incident,
        IncidentEventType.comment,
        message=message,
        actor_id=actor.id,
    )
