"""Observability API: services, health checks, results, uptime, and status grid."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, RequireOperator
from app.core.exceptions import ConflictError, NotFoundError
from app.core.rate_limit import SCAN_LIMIT, limiter
from app.models.enums import AuditAction
from app.models.observability import CheckResult, HealthCheck, Service
from app.observability.checks import run_check_sync
from app.schemas.common import Envelope, Page, PaginationParams
from app.schemas.observability import (
    CheckResultRead,
    HealthCheckCreate,
    HealthCheckRead,
    HealthCheckUpdate,
    ServiceCreate,
    ServiceRead,
    StatusGridItem,
    UptimeRead,
)
from app.services import observability_service
from app.services.audit_service import record_audit, snapshot
from app.services.incident_service import evaluate_after_result

router = APIRouter(prefix="/observability", tags=["observability"])

_DEFAULT_UPTIME_WINDOW_HOURS = 24
_MAX_UPTIME_WINDOW_HOURS = 24 * 90  # 90 days


def _get_service_or_404(db: DbSession, service_id: uuid.UUID) -> Service:
    service = db.get(Service, service_id)
    if service is None:
        raise NotFoundError("Service not found.")
    return service


def _get_check_or_404(db: DbSession, check_id: uuid.UUID) -> HealthCheck:
    check = db.get(HealthCheck, check_id)
    if check is None:
        raise NotFoundError("Health check not found.")
    return check


# --------------------------------------------------------------------------- #
# Services
# --------------------------------------------------------------------------- #
@router.get("/services", response_model=Envelope[Page[ServiceRead]])
def list_services(
    db: DbSession,
    _user: CurrentUser,
    pagination: Annotated[PaginationParams, Depends()],
) -> Envelope[Page[ServiceRead]]:
    total = db.execute(select(func.count(Service.id))).scalar_one()
    services = (
        db.execute(
            select(Service).order_by(Service.name).limit(pagination.limit).offset(pagination.offset)
        )
        .scalars()
        .all()
    )
    items = [ServiceRead.model_validate(s) for s in services]
    return Envelope.ok(
        Page(items=items, total=int(total), limit=pagination.limit, offset=pagination.offset)
    )


@router.post("/services", response_model=Envelope[ServiceRead], status_code=201)
def create_service(
    payload: ServiceCreate,
    db: DbSession,
    user: RequireOperator,
    request: Request,
) -> Envelope[ServiceRead]:
    existing = db.execute(select(Service).where(Service.name == payload.name)).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("A service with that name already exists.")
    service = Service(
        name=payload.name,
        description=payload.description,
        asset_id=payload.asset_id,
        slo_target=payload.slo_target,
    )
    db.add(service)
    db.flush()
    record_audit(
        db,
        action=AuditAction.create,
        entity_type="service",
        entity_id=service.id,
        actor_id=user.id,
        after=snapshot(service),
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(service)
    return Envelope.ok(ServiceRead.model_validate(service))


@router.get("/services/{service_id}", response_model=Envelope[ServiceRead])
def get_service(
    service_id: uuid.UUID,
    db: DbSession,
    _user: CurrentUser,
) -> Envelope[ServiceRead]:
    service = _get_service_or_404(db, service_id)
    return Envelope.ok(ServiceRead.model_validate(service))


@router.patch("/services/{service_id}", response_model=Envelope[ServiceRead])
def update_service(
    service_id: uuid.UUID,
    payload: ServiceCreate,
    db: DbSession,
    user: RequireOperator,
    request: Request,
) -> Envelope[ServiceRead]:
    service = _get_service_or_404(db, service_id)
    before = snapshot(service)
    if payload.name != service.name:
        clash = db.execute(
            select(Service).where(Service.name == payload.name, Service.id != service.id)
        ).scalar_one_or_none()
        if clash is not None:
            raise ConflictError("A service with that name already exists.")
    service.name = payload.name
    service.description = payload.description
    service.asset_id = payload.asset_id
    service.slo_target = payload.slo_target
    db.add(service)
    db.flush()
    record_audit(
        db,
        action=AuditAction.update,
        entity_type="service",
        entity_id=service.id,
        actor_id=user.id,
        before=before,
        after=snapshot(service),
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(service)
    return Envelope.ok(ServiceRead.model_validate(service))


# --------------------------------------------------------------------------- #
# Health checks
# --------------------------------------------------------------------------- #
@router.get(
    "/services/{service_id}/checks",
    response_model=Envelope[Page[HealthCheckRead]],
)
def list_checks(
    service_id: uuid.UUID,
    db: DbSession,
    _user: CurrentUser,
    pagination: Annotated[PaginationParams, Depends()],
) -> Envelope[Page[HealthCheckRead]]:
    _get_service_or_404(db, service_id)
    total = db.execute(
        select(func.count(HealthCheck.id)).where(HealthCheck.service_id == service_id)
    ).scalar_one()
    checks = (
        db.execute(
            select(HealthCheck)
            .where(HealthCheck.service_id == service_id)
            .order_by(HealthCheck.name)
            .limit(pagination.limit)
            .offset(pagination.offset)
        )
        .scalars()
        .all()
    )
    items = [HealthCheckRead.model_validate(c) for c in checks]
    return Envelope.ok(
        Page(items=items, total=int(total), limit=pagination.limit, offset=pagination.offset)
    )


@router.post(
    "/services/{service_id}/checks",
    response_model=Envelope[HealthCheckRead],
    status_code=201,
)
def create_check(
    service_id: uuid.UUID,
    payload: HealthCheckCreate,
    db: DbSession,
    user: RequireOperator,
    request: Request,
) -> Envelope[HealthCheckRead]:
    _get_service_or_404(db, service_id)
    check = HealthCheck(
        service_id=service_id,
        name=payload.name,
        check_type=payload.check_type,
        target=payload.target,
        method=payload.method,
        expected_status=payload.expected_status,
        latency_budget_ms=payload.latency_budget_ms,
        port=payload.port,
        interval_seconds=payload.interval_seconds,
        enabled=payload.enabled,
    )
    db.add(check)
    db.flush()
    record_audit(
        db,
        action=AuditAction.create,
        entity_type="health_check",
        entity_id=check.id,
        actor_id=user.id,
        after=snapshot(check),
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(check)
    return Envelope.ok(HealthCheckRead.model_validate(check))


@router.patch("/checks/{check_id}", response_model=Envelope[HealthCheckRead])
def update_check(
    check_id: uuid.UUID,
    payload: HealthCheckUpdate,
    db: DbSession,
    user: RequireOperator,
    request: Request,
) -> Envelope[HealthCheckRead]:
    check = _get_check_or_404(db, check_id)
    before = snapshot(check)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(check, field, value)
    db.add(check)
    db.flush()
    record_audit(
        db,
        action=AuditAction.update,
        entity_type="health_check",
        entity_id=check.id,
        actor_id=user.id,
        before=before,
        after=snapshot(check),
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(check)
    return Envelope.ok(HealthCheckRead.model_validate(check))


@router.post("/checks/{check_id}/run", response_model=Envelope[CheckResultRead])
@limiter.limit(SCAN_LIMIT)
def run_check_now(
    check_id: uuid.UUID,
    db: DbSession,
    user: RequireOperator,
    request: Request,
) -> Envelope[CheckResultRead]:
    """Probe a check synchronously, record the result, and evaluate incidents."""
    check = _get_check_or_404(db, check_id)
    outcome = run_check_sync(check)
    result = observability_service.record_check_result(db, check, outcome)
    evaluate_after_result(db, check)
    record_audit(
        db,
        action=AuditAction.state_change,
        entity_type="health_check",
        entity_id=check.id,
        actor_id=user.id,
        after={"status": outcome.status.value, "latency_ms": outcome.latency_ms},
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(result)
    return Envelope.ok(CheckResultRead.model_validate(result))


@router.get("/checks/{check_id}/results", response_model=Envelope[Page[CheckResultRead]])
def list_check_results(
    check_id: uuid.UUID,
    db: DbSession,
    _user: CurrentUser,
    pagination: Annotated[PaginationParams, Depends()],
) -> Envelope[Page[CheckResultRead]]:
    _get_check_or_404(db, check_id)
    total = db.execute(
        select(func.count(CheckResult.id)).where(CheckResult.health_check_id == check_id)
    ).scalar_one()
    results = (
        db.execute(
            select(CheckResult)
            .where(CheckResult.health_check_id == check_id)
            .order_by(CheckResult.created_at.desc())
            .limit(pagination.limit)
            .offset(pagination.offset)
        )
        .scalars()
        .all()
    )
    items = [CheckResultRead.model_validate(r) for r in results]
    return Envelope.ok(
        Page(items=items, total=int(total), limit=pagination.limit, offset=pagination.offset)
    )


# --------------------------------------------------------------------------- #
# Uptime + status grid
# --------------------------------------------------------------------------- #
@router.get("/services/{service_id}/uptime", response_model=Envelope[UptimeRead])
def get_service_uptime(
    service_id: uuid.UUID,
    db: DbSession,
    _user: CurrentUser,
    window_hours: Annotated[
        int, Query(ge=1, le=_MAX_UPTIME_WINDOW_HOURS)
    ] = _DEFAULT_UPTIME_WINDOW_HOURS,
) -> Envelope[UptimeRead]:
    service = _get_service_or_404(db, service_id)
    window = timedelta(hours=window_hours)
    observed = observability_service.service_uptime(db, service_id, window)
    budget = observability_service.error_budget(service.slo_target, observed)
    return Envelope.ok(
        UptimeRead(
            window_hours=window_hours,
            uptime=observed,
            slo_target=service.slo_target,
            error_budget=budget,
        )
    )


@router.get("/status", response_model=Envelope[Page[StatusGridItem]])
def get_status_grid(
    db: DbSession,
    _user: CurrentUser,
) -> Envelope[Page[StatusGridItem]]:
    grid = observability_service.status_grid(db)
    items = [StatusGridItem.model_validate(row) for row in grid]
    return Envelope.ok(Page(items=items, total=len(items), limit=len(items), offset=0))
