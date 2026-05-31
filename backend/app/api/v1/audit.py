"""Audit-log read endpoints.

The audit log is append-only: this router exposes reads only — no create, update,
or delete routes exist. Any authenticated user may read the trail.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models.audit import AuditLog
from app.models.enums import AuditAction
from app.schemas.audit import AuditRead
from app.schemas.common import Envelope, Page, PaginationParams

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=Envelope[Page[AuditRead]], summary="List audit entries")
def list_audit(
    db: DbSession,
    _user: CurrentUser,
    pagination: Annotated[PaginationParams, Depends()],
    entity_type: Annotated[str | None, Query(max_length=50)] = None,
    entity_id: Annotated[uuid.UUID | None, Query()] = None,
    actor_id: Annotated[uuid.UUID | None, Query()] = None,
    action: Annotated[AuditAction | None, Query()] = None,
) -> Envelope[Page[AuditRead]]:
    stmt = select(AuditLog)
    if entity_type is not None:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = int(db.execute(count_stmt).scalar_one())

    rows = list(
        db.execute(
            stmt.order_by(AuditLog.created_at.desc())
            .limit(pagination.limit)
            .offset(pagination.offset)
        ).scalars()
    )
    page: Page[AuditRead] = Page(
        items=[AuditRead.model_validate(r) for r in rows],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Envelope.ok(page)


@router.get(
    "/{entity_type}/{entity_id}",
    response_model=Envelope[Page[AuditRead]],
    summary="Change history for one entity (newest first)",
)
def entity_history(
    entity_type: str,
    entity_id: uuid.UUID,
    db: DbSession,
    _user: CurrentUser,
    pagination: Annotated[PaginationParams, Depends()],
) -> Envelope[Page[AuditRead]]:
    stmt = (
        select(AuditLog)
        .where(AuditLog.entity_type == entity_type)
        .where(AuditLog.entity_id == entity_id)
    )
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = int(db.execute(count_stmt).scalar_one())

    rows = list(
        db.execute(
            stmt.order_by(AuditLog.created_at.desc())
            .limit(pagination.limit)
            .offset(pagination.offset)
        ).scalars()
    )
    page: Page[AuditRead] = Page(
        items=[AuditRead.model_validate(r) for r in rows],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Envelope.ok(page)
