"""Behavioral test for Prometheus metrics exposition (app/services/metrics_service.py).

``render_metrics`` opens its OWN ``SessionLocal`` (independent of the ``db``
fixture session), so the seeded data must be committed for it to be visible.
The test seeds assets, a service + health check with check results, an open
incident, and a finished compliance run, then asserts the rendered body carries
the documented gauge names with sane values.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.compliance import ComplianceRun
from app.models.enums import (
    AssetType,
    CheckStatus,
    CheckType,
    Environment,
    IncidentStatus,
)
from app.models.observability import CheckResult, HealthCheck, Incident, Service
from app.schemas.asset import AssetCreate
from app.services.asset_service import create_asset
from app.services.metrics_service import render_metrics

pytestmark = pytest.mark.integration

# Every gauge family documented in metrics_service that this fixture exercises.
_EXPECTED_METRIC_NAMES = (
    "sentryops_assets_total",
    "sentryops_compliance_score",
    "sentryops_open_incidents",
    "sentryops_check_up",
    "sentryops_mtta_seconds",
    "sentryops_mttr_seconds",
)


def _seed(db: Session) -> Service:
    # Two assets in different environments so the assets_total gauge has labels.
    create_asset(
        db, AssetCreate(name="web-01", asset_type=AssetType.host, environment=Environment.prod)
    )
    create_asset(
        db,
        AssetCreate(
            name="cache-01", asset_type=AssetType.cloud_resource, environment=Environment.staging
        ),
    )

    # A service + check with a latest UP result.
    service = Service(name="payments", slo_target=0.999)
    db.add(service)
    db.flush()
    check = HealthCheck(
        service_id=service.id,
        name="https probe",
        check_type=CheckType.http,
        target="https://payments.test.local/health",
        expected_status=200,
        latency_budget_ms=1000,
        enabled=True,
    )
    db.add(check)
    db.flush()
    now = datetime.now(UTC)
    db.add(
        CheckResult(
            health_check_id=check.id,
            status=CheckStatus.up,
            latency_ms=37.5,
            status_code=200,
            created_at=now - timedelta(minutes=1),
        )
    )

    # An incident opened, acknowledged, and resolved within the 24h window so
    # both MTTA and MTTR gauges have data to report.
    opened = now - timedelta(hours=2)
    db.add(
        Incident(
            service_id=service.id,
            health_check_id=check.id,
            title="payments degraded",
            status=IncidentStatus.open,
            opened_at=opened,
            acknowledged_at=opened + timedelta(minutes=5),
            resolved_at=opened + timedelta(minutes=30),
        )
    )

    # A finished compliance run so the compliance_score gauge is populated.
    run = ComplianceRun(
        started_at=now - timedelta(minutes=10),
        finished_at=now - timedelta(minutes=9),
        total_assets=2,
        org_score=87.5,
        passed_count=10,
        failed_count=2,
        not_applicable_count=1,
    )
    db.add(run)
    db.flush()
    return service


def test_render_metrics_returns_bytes_and_content_type(db: Session) -> None:
    # Arrange — seed and COMMIT so render_metrics' own session can see the data.
    _seed(db)
    db.commit()

    # Act
    body, content_type = render_metrics()

    # Assert — the exposition is bytes with the Prometheus text content type.
    assert isinstance(body, bytes)
    assert isinstance(content_type, str)
    assert "text/plain" in content_type
    assert b"# HELP" in body


def test_render_metrics_body_contains_documented_metric_names(db: Session) -> None:
    # Arrange
    _seed(db)
    db.commit()

    # Act
    body, _ = render_metrics()
    text = body.decode("utf-8")

    # Assert — every documented gauge family is present.
    for name in _EXPECTED_METRIC_NAMES:
        assert name in text, f"missing metric: {name}"


def test_render_metrics_reflects_seeded_values(db: Session) -> None:
    # Arrange
    _seed(db)
    db.commit()

    # Act
    body, _ = render_metrics()
    text = body.decode("utf-8")

    # Assert — concrete values derived from the seeded rows.
    # Compliance score from the finished run.
    assert "sentryops_compliance_score 87.5" in text
    # Exactly one open incident.
    assert "sentryops_open_incidents 1.0" in text
    # The latest check result was UP -> the check_up gauge carries a 1.
    assert 'sentryops_check_up{check="https probe",service="payments"} 1.0' in text
    # MTTA = 5 min = 300s, MTTR = 30 min = 1800s for the single incident.
    assert "sentryops_mtta_seconds 300.0" in text
    assert "sentryops_mttr_seconds 1800.0" in text


def test_render_metrics_empty_state_still_renders(db: Session) -> None:
    # Arrange — no seeded data; just ensure a clean committed state.
    db.commit()

    # Act — render against an empty database.
    body, content_type = render_metrics()
    text = body.decode("utf-8")

    # Assert — open-incidents gauge defaults to 0; never raises on empty data.
    assert "text/plain" in content_type
    assert "sentryops_open_incidents 0.0" in text
