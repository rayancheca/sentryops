"""Incident API: list/detail, acknowledge, comment, resolve, and MTTA/MTTR.

Route ordering matters here: the static-prefix GET routes (``/metrics/...`` and
``/assets/...``) are declared BEFORE the parameterized ``/{incident_id}`` route
so a path like ``/incidents/metrics/mtta-mttr`` is never mis-matched against the
UUID path parameter.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, RequireOperator
from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import AuditAction, IncidentStatus
from app.models.observability import Incident
from app.schemas.common import Envelope, Page, PaginationParams
from app.schemas.incident import (
    CommentCreate,
    IncidentDetailRead,
    IncidentEventRead,
    IncidentRead,
    MttaMttrRead,
)
from app.services import incident_service, observability_service
from app.services.audit_service import record_audit, snapshot

router = APIRouter(prefix="/incidents", tags=["incidents"])

_MAX_MTTA_MTTR_WINDOW_HOURS = 24 * 365  # 1 year


def _get_incident_or_404(db: DbSession, incident_id: uuid.UUID) -> Incident:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise NotFoundError("Incident not found.")
    return incident


# --------------------------------------------------------------------------- #
# Collection + static-prefix routes (declared before /{incident_id})
# --------------------------------------------------------------------------- #
@router.get("", response_model=Envelope[Page[IncidentRead]])
def list_incidents(
    db: DbSession,
    _user: CurrentUser,
    pagination: Annotated[PaginationParams, Depends()],
    status: Annotated[IncidentStatus | None, Query()] = None,
) -> Envelope[Page[IncidentRead]]:
    count_stmt = select(func.count(Incident.id))
    list_stmt = select(Incident).order_by(Incident.opened_at.desc())
    if status is not None:
        count_stmt = count_stmt.where(Incident.status == status)
        list_stmt = list_stmt.where(Incident.status == status)
    total = db.execute(count_stmt).scalar_one()
    incidents = (
        db.execute(list_stmt.limit(pagination.limit).offset(pagination.offset)).scalars().all()
    )
    items = [IncidentRead.model_validate(i) for i in incidents]
    return Envelope.ok(
        Page(items=items, total=int(total), limit=pagination.limit, offset=pagination.offset)
    )


@router.get("/metrics/mtta-mttr", response_model=Envelope[MttaMttrRead])
def mtta_mttr(
    db: DbSession,
    _user: CurrentUser,
    window_hours: Annotated[int | None, Query(ge=1, le=_MAX_MTTA_MTTR_WINDOW_HOURS)] = None,
) -> Envelope[MttaMttrRead]:
    window = timedelta(hours=window_hours) if window_hours is not None else None
    mtta_seconds, mttr_seconds = observability_service.compute_mtta_mttr(db, window)
    return Envelope.ok(
        MttaMttrRead(
            mtta_seconds=mtta_seconds,
            mttr_seconds=mttr_seconds,
            window_hours=window_hours,
        )
    )


@router.get("/assets/{asset_id}", response_model=Envelope[Page[IncidentRead]])
def incidents_for_asset(
    asset_id: uuid.UUID,
    db: DbSession,
    _user: CurrentUser,
    pagination: Annotated[PaginationParams, Depends()],
) -> Envelope[Page[IncidentRead]]:
    total = db.execute(
        select(func.count(Incident.id)).where(Incident.asset_id == asset_id)
    ).scalar_one()
    incidents = (
        db.execute(
            select(Incident)
            .where(Incident.asset_id == asset_id)
            .order_by(Incident.opened_at.desc())
            .limit(pagination.limit)
            .offset(pagination.offset)
        )
        .scalars()
        .all()
    )
    items = [IncidentRead.model_validate(i) for i in incidents]
    return Envelope.ok(
        Page(items=items, total=int(total), limit=pagination.limit, offset=pagination.offset)
    )


# --------------------------------------------------------------------------- #
# Single-incident detail + lifecycle actions
# --------------------------------------------------------------------------- #
@router.get("/{incident_id}", response_model=Envelope[IncidentDetailRead])
def get_incident(
    incident_id: uuid.UUID,
    db: DbSession,
    _user: CurrentUser,
) -> Envelope[IncidentDetailRead]:
    incident = _get_incident_or_404(db, incident_id)
    detail = IncidentDetailRead.model_validate(
        {
            **IncidentRead.model_validate(incident).model_dump(),
            "events": [IncidentEventRead.model_validate(e) for e in incident.events],
        }
    )
    return Envelope.ok(detail)


@router.post("/{incident_id}/acknowledge", response_model=Envelope[IncidentRead])
def acknowledge(
    incident_id: uuid.UUID,
    db: DbSession,
    user: RequireOperator,
    request: Request,
) -> Envelope[IncidentRead]:
    incident = _get_incident_or_404(db, incident_id)
    if incident.status in (IncidentStatus.resolved, IncidentStatus.closed):
        raise ConflictError("Cannot acknowledge a resolved or closed incident.")
    before = snapshot(incident)
    incident_service.acknowledge_incident(db, incident, user)
    record_audit(
        db,
        action=AuditAction.state_change,
        entity_type="incident",
        entity_id=incident.id,
        actor_id=user.id,
        before=before,
        after=snapshot(incident),
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(incident)
    return Envelope.ok(IncidentRead.model_validate(incident))


@router.post("/{incident_id}/comment", response_model=Envelope[IncidentEventRead], status_code=201)
def comment(
    incident_id: uuid.UUID,
    payload: CommentCreate,
    db: DbSession,
    user: RequireOperator,
    request: Request,
) -> Envelope[IncidentEventRead]:
    incident = _get_incident_or_404(db, incident_id)
    event = incident_service.add_comment(db, incident, user, payload.message)
    record_audit(
        db,
        action=AuditAction.update,
        entity_type="incident",
        entity_id=incident.id,
        actor_id=user.id,
        after={"event": "comment"},
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(event)
    return Envelope.ok(IncidentEventRead.model_validate(event))


@router.post("/{incident_id}/resolve", response_model=Envelope[IncidentRead])
def resolve(
    incident_id: uuid.UUID,
    db: DbSession,
    user: RequireOperator,
    request: Request,
) -> Envelope[IncidentRead]:
    incident = _get_incident_or_404(db, incident_id)
    if incident.status == IncidentStatus.closed:
        raise ConflictError("Incident is already closed.")
    before = snapshot(incident)
    incident_service.resolve_incident(db, incident, user)
    record_audit(
        db,
        action=AuditAction.state_change,
        entity_type="incident",
        entity_id=incident.id,
        actor_id=user.id,
        before=before,
        after=snapshot(incident),
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(incident)
    return Envelope.ok(IncidentRead.model_validate(incident))
