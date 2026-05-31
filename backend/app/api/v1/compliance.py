"""Compliance API (Pillar 2): rules catalogue, runs, scoring, drift, reports.

Read endpoints accept any authenticated user. Triggering a run is a privileged,
rate-limited operation requiring operator+. Every mutation commits the
transaction and relies on the service layer for auditing.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import CurrentUser, DbSession, RequireOperator
from app.compliance.registry import get_rules
from app.core.rate_limit import SCAN_LIMIT, limiter
from app.schemas.common import Envelope, Meta, Page, PaginationParams
from app.schemas.compliance import (
    DriftPoint,
    NewlyFailingItem,
    ReportRead,
    ResultRead,
    RuleRead,
    RunRead,
    ScoreRead,
)
from app.services import compliance_service

router = APIRouter(prefix="/compliance", tags=["compliance"])

Pagination = Annotated[PaginationParams, Depends(PaginationParams)]


@router.get("/rules", response_model=Envelope[Page[RuleRead]])
def list_rules(_user: CurrentUser) -> Envelope[Page[RuleRead]]:
    """List every registered compliance rule (the static control catalogue)."""
    rules = get_rules()
    items = [RuleRead.model_validate(rule) for rule in rules]
    page: Page[RuleRead] = Page(items=items, total=len(items), limit=len(items), offset=0)
    return Envelope.ok(page)


@router.post("/runs", response_model=Envelope[RunRead])
@limiter.limit(SCAN_LIMIT)
def trigger_run(
    request: Request,
    db: DbSession,
    user: RequireOperator,
) -> Envelope[RunRead]:
    """Trigger a full compliance evaluation across all in-scope assets."""
    run = compliance_service.run_evaluation(db, triggered_by=user)
    db.commit()
    db.refresh(run)
    return Envelope.ok(RunRead.model_validate(run))


@router.get("/runs", response_model=Envelope[Page[RunRead]])
def list_runs(
    db: DbSession,
    _user: CurrentUser,
    pagination: Pagination,
) -> Envelope[Page[RunRead]]:
    """Paginated run history, newest first."""
    from sqlalchemy import func, select

    from app.models.compliance import ComplianceRun  # local import: avoid cycle

    total = db.scalar(select(func.count()).select_from(ComplianceRun)) or 0
    stmt = (
        select(ComplianceRun)
        .order_by(ComplianceRun.started_at.desc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    runs = list(db.scalars(stmt).all())
    items = [RunRead.model_validate(run) for run in runs]
    page: Page[RunRead] = Page(
        items=items, total=int(total), limit=pagination.limit, offset=pagination.offset
    )
    meta = Meta(total=int(total), limit=pagination.limit, offset=pagination.offset)
    return Envelope.ok(page, meta=meta)


@router.get("/runs/latest", response_model=Envelope[RunRead])
def get_latest_run(db: DbSession, _user: CurrentUser) -> Envelope[RunRead]:
    """The most recent run snapshot."""
    from app.core.exceptions import NotFoundError

    run = compliance_service.latest_run(db)
    if run is None:
        raise NotFoundError("No compliance run has been recorded yet.")
    return Envelope.ok(RunRead.model_validate(run))


@router.get("/score", response_model=Envelope[ScoreRead])
def get_score(db: DbSession, _user: CurrentUser) -> Envelope[ScoreRead]:
    """Organisation rollup score derived from the latest run."""
    run = compliance_service.latest_run(db)
    if run is None:
        score = ScoreRead(
            run_id=None,
            org_score=100.0,
            total_assets=0,
            passed_count=0,
            failed_count=0,
            not_applicable_count=0,
            severity_failing={},
            started_at=None,
        )
        return Envelope.ok(score)
    score = ScoreRead(
        run_id=run.id,
        org_score=run.org_score,
        total_assets=run.total_assets,
        passed_count=run.passed_count,
        failed_count=run.failed_count,
        not_applicable_count=run.not_applicable_count,
        severity_failing=dict(run.severity_failing or {}),
        started_at=run.started_at,
    )
    return Envelope.ok(score)


@router.get("/drift", response_model=Envelope[Page[DriftPoint]])
def get_drift(
    db: DbSession,
    _user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> Envelope[Page[DriftPoint]]:
    """Org-score-over-time drift series (oldest-first)."""
    series = compliance_service.drift_series(db, limit=limit)
    items = [DriftPoint.model_validate(point) for point in series]
    page: Page[DriftPoint] = Page(items=items, total=len(items), limit=limit, offset=0)
    return Envelope.ok(page)


@router.get("/newly-failing", response_model=Envelope[Page[NewlyFailingItem]])
def get_newly_failing(db: DbSession, _user: CurrentUser) -> Envelope[Page[NewlyFailingItem]]:
    """Controls that started failing in the latest run versus the previous one."""
    items_raw = compliance_service.newly_failing(db)
    items = [NewlyFailingItem.model_validate(item) for item in items_raw]
    page: Page[NewlyFailingItem] = Page(items=items, total=len(items), limit=len(items), offset=0)
    return Envelope.ok(page)


@router.get("/assets/{asset_id}/results", response_model=Envelope[Page[ResultRead]])
def get_asset_results(
    asset_id: uuid.UUID,
    db: DbSession,
    _user: CurrentUser,
) -> Envelope[Page[ResultRead]]:
    """Latest-run compliance results for a single asset."""
    results = compliance_service.get_results(db, asset_id=asset_id)
    items = [ResultRead.model_validate(r) for r in results]
    page: Page[ResultRead] = Page(items=items, total=len(items), limit=len(items), offset=0)
    return Envelope.ok(page)


@router.get("/report", response_model=Envelope[ReportRead])
def get_report(
    db: DbSession,
    _user: CurrentUser,
    run_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Envelope[ReportRead]:
    """Audit-ready compliance report for the latest run (or ``?run_id=``)."""
    payload = compliance_service.report(db, run_id=run_id)
    return Envelope.ok(ReportRead.model_validate(payload))
