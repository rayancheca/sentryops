"""Prometheus metrics exposition.

``render_metrics`` builds a fresh ``CollectorRegistry`` on every scrape (no
process-global default registry state) and opens its own DB session, so it is
safe to call from the metrics endpoint without sharing the request session.
"""

from __future__ import annotations

from datetime import timedelta

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Gauge, generate_latest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.ai import AITriageResult  # noqa: F401  (ensure mapper registration)
from app.models.asset import Asset
from app.models.compliance import ComplianceRun
from app.models.enums import CheckStatus, IncidentStatus
from app.models.observability import CheckResult, HealthCheck, Incident, Service
from app.services.observability_service import compute_mtta_mttr

# 24h window for the gauges that summarize recent reliability.
_MTTA_MTTR_WINDOW = timedelta(hours=24)


def _collect_asset_counts(db: Session, registry: CollectorRegistry) -> None:
    gauge = Gauge(
        "sentryops_assets_total",
        "Total assets by type and environment.",
        labelnames=("type", "environment"),
        registry=registry,
    )
    rows = db.execute(
        select(Asset.asset_type, Asset.environment, func.count(Asset.id)).group_by(
            Asset.asset_type, Asset.environment
        )
    ).all()
    for asset_type, environment, count in rows:
        gauge.labels(type=str(asset_type), environment=str(environment)).set(count)


def _collect_compliance_score(db: Session, registry: CollectorRegistry) -> None:
    gauge = Gauge(
        "sentryops_compliance_score",
        "Latest organization-wide compliance score (0..100).",
        registry=registry,
    )
    latest = db.execute(
        select(ComplianceRun.org_score)
        .where(ComplianceRun.finished_at.is_not(None))
        .order_by(ComplianceRun.started_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest is not None:
        gauge.set(float(latest))


def _collect_open_incidents(db: Session, registry: CollectorRegistry) -> None:
    gauge = Gauge(
        "sentryops_open_incidents",
        "Number of incidents currently open or acknowledged.",
        registry=registry,
    )
    count = db.execute(
        select(func.count(Incident.id)).where(
            Incident.status.in_((IncidentStatus.open, IncidentStatus.acknowledged))
        )
    ).scalar_one()
    gauge.set(int(count or 0))


def _collect_check_gauges(db: Session, registry: CollectorRegistry) -> None:
    up_gauge = Gauge(
        "sentryops_check_up",
        "Whether a check's latest result was UP (1) or DOWN (0).",
        labelnames=("service", "check"),
        registry=registry,
    )
    latency_gauge = Gauge(
        "sentryops_check_latency_ms",
        "Latency in milliseconds from a check's latest result.",
        labelnames=("service", "check"),
        registry=registry,
    )
    rows = db.execute(
        select(HealthCheck, Service.name)
        .join(Service, Service.id == HealthCheck.service_id)
        .order_by(Service.name, HealthCheck.name)
    ).all()
    for check, service_name in rows:
        latest = db.execute(
            select(CheckResult)
            .where(CheckResult.health_check_id == check.id)
            .order_by(CheckResult.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest is None:
            continue
        labels = {"service": service_name, "check": check.name}
        up_gauge.labels(**labels).set(1.0 if latest.status == CheckStatus.up else 0.0)
        if latest.latency_ms is not None:
            latency_gauge.labels(**labels).set(latest.latency_ms)


def _collect_mtta_mttr(db: Session, registry: CollectorRegistry) -> None:
    mtta_gauge = Gauge(
        "sentryops_mtta_seconds",
        "Mean time to acknowledge over the last 24h (seconds).",
        registry=registry,
    )
    mttr_gauge = Gauge(
        "sentryops_mttr_seconds",
        "Mean time to resolve over the last 24h (seconds).",
        registry=registry,
    )
    mtta, mttr = compute_mtta_mttr(db, _MTTA_MTTR_WINDOW)
    if mtta is not None:
        mtta_gauge.set(mtta)
    if mttr is not None:
        mttr_gauge.set(mttr)


def render_metrics() -> tuple[bytes, str]:
    """Render the current metric snapshot as Prometheus exposition text.

    Returns ``(body, content_type)`` ready for a ``Response``. Opens and closes
    its own session so it never touches a request-scoped one.
    """
    registry = CollectorRegistry()
    db = SessionLocal()
    try:
        _collect_asset_counts(db, registry)
        _collect_compliance_score(db, registry)
        _collect_open_incidents(db, registry)
        _collect_check_gauges(db, registry)
        _collect_mtta_mttr(db, registry)
    finally:
        db.close()
    return generate_latest(registry), CONTENT_TYPE_LATEST
