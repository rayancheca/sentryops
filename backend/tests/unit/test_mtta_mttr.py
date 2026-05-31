"""MTTA / MTTR computation tests (logic-with-data, uses the db fixture).

Semantics from app/services/observability_service.py::compute_mtta_mttr:

    * Incidents considered are those opened within ``window`` (all-time when
      window is None), via ``Incident.opened_at >= now - window``.
    * MTTA = mean(acknowledged_at - opened_at) over incidents whose
      acknowledged_at is set; unacknowledged (incl. still-open) are excluded.
    * MTTR = mean(resolved_at - opened_at) over incidents whose resolved_at is
      set; unresolved are excluded.
    * Returns (None, None) when nothing qualifies for the respective metric.

All datetimes are timezone-aware UTC. We assert exact mean seconds.
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.enums import IncidentStatus
from app.models.observability import Incident, Service
from app.services.observability_service import compute_mtta_mttr

pytestmark = pytest.mark.unit

_names = itertools.count(1)

# A fixed anchor well in the past so default windows comfortably include it,
# yet recent enough to fall inside a multi-day test window.
_BASE = datetime(2026, 5, 30, 12, 0, 0, tzinfo=UTC)


def _make_service(db: Session) -> Service:
    service = Service(name=f"svc-{next(_names)}", slo_target=0.999)
    db.add(service)
    db.flush()
    return service


def _make_incident(
    db: Session,
    service: Service,
    *,
    opened_at: datetime,
    acknowledged_at: datetime | None = None,
    resolved_at: datetime | None = None,
    status: IncidentStatus = IncidentStatus.open,
) -> Incident:
    incident = Incident(
        service_id=service.id,
        title="boom",
        status=status,
        opened_at=opened_at,
        acknowledged_at=acknowledged_at,
        resolved_at=resolved_at,
    )
    db.add(incident)
    db.flush()
    return incident


# --------------------------------------------------------------------------- #
# Empty / no qualifying incidents                                             #
# --------------------------------------------------------------------------- #


def test_returns_none_none_when_no_incidents(db: Session) -> None:
    # Arrange: empty incidents table.
    # Act
    mtta, mttr = compute_mtta_mttr(db)

    # Assert
    assert mtta is None
    assert mttr is None


def test_returns_none_none_when_only_open_incident_exists(db: Session) -> None:
    # Arrange: a single still-open incident, never acknowledged or resolved.
    service = _make_service(db)
    _make_incident(db, service, opened_at=_BASE, status=IncidentStatus.open)

    # Act
    mtta, mttr = compute_mtta_mttr(db)

    # Assert: it contributes to neither metric.
    assert mtta is None
    assert mttr is None


# --------------------------------------------------------------------------- #
# MTTA: only acknowledged incidents count                                     #
# --------------------------------------------------------------------------- #


def test_mtta_averages_only_acknowledged_incidents(db: Session) -> None:
    # Arrange: two acknowledged (60s and 120s to ack) plus one never-acked open.
    service = _make_service(db)
    _make_incident(
        db,
        service,
        opened_at=_BASE,
        acknowledged_at=_BASE + timedelta(seconds=60),
        status=IncidentStatus.acknowledged,
    )
    _make_incident(
        db,
        service,
        opened_at=_BASE,
        acknowledged_at=_BASE + timedelta(seconds=120),
        status=IncidentStatus.acknowledged,
    )
    _make_incident(db, service, opened_at=_BASE, status=IncidentStatus.open)

    # Act
    mtta, mttr = compute_mtta_mttr(db)

    # Assert: mean of 60 and 120 = 90s; no resolved incidents -> MTTR None.
    assert mtta == 90.0
    assert mttr is None


def test_resolved_but_unacknowledged_does_not_count_toward_mtta(db: Session) -> None:
    # Arrange: an incident resolved directly without an explicit ack timestamp.
    service = _make_service(db)
    _make_incident(
        db,
        service,
        opened_at=_BASE,
        acknowledged_at=None,
        resolved_at=_BASE + timedelta(seconds=300),
        status=IncidentStatus.resolved,
    )

    # Act
    mtta, mttr = compute_mtta_mttr(db)

    # Assert: excluded from MTTA, counted for MTTR.
    assert mtta is None
    assert mttr == 300.0


# --------------------------------------------------------------------------- #
# MTTR: only resolved incidents count                                         #
# --------------------------------------------------------------------------- #


def test_mttr_averages_only_resolved_incidents(db: Session) -> None:
    # Arrange: two resolved (300s and 900s) plus one acknowledged-but-open.
    service = _make_service(db)
    _make_incident(
        db,
        service,
        opened_at=_BASE,
        acknowledged_at=_BASE + timedelta(seconds=30),
        resolved_at=_BASE + timedelta(seconds=300),
        status=IncidentStatus.resolved,
    )
    _make_incident(
        db,
        service,
        opened_at=_BASE,
        acknowledged_at=_BASE + timedelta(seconds=30),
        resolved_at=_BASE + timedelta(seconds=900),
        status=IncidentStatus.resolved,
    )
    _make_incident(
        db,
        service,
        opened_at=_BASE,
        acknowledged_at=_BASE + timedelta(seconds=45),
        status=IncidentStatus.acknowledged,
    )

    # Act
    mtta, mttr = compute_mtta_mttr(db)

    # Assert: MTTR mean of 300 and 900 = 600s. MTTA mean of 30, 30, 45 = 35s.
    assert mttr == 600.0
    assert mtta == pytest.approx(35.0)


def test_still_open_incident_is_excluded_from_mttr(db: Session) -> None:
    # Arrange: one resolved (240s) and one still-open acknowledged incident.
    service = _make_service(db)
    _make_incident(
        db,
        service,
        opened_at=_BASE,
        acknowledged_at=_BASE + timedelta(seconds=10),
        resolved_at=_BASE + timedelta(seconds=240),
        status=IncidentStatus.resolved,
    )
    _make_incident(
        db,
        service,
        opened_at=_BASE,
        acknowledged_at=_BASE + timedelta(seconds=10),
        resolved_at=None,
        status=IncidentStatus.acknowledged,
    )

    # Act
    mtta, mttr = compute_mtta_mttr(db)

    # Assert: only the resolved incident contributes to MTTR.
    assert mttr == 240.0
    assert mtta == 10.0


# --------------------------------------------------------------------------- #
# Single-incident exactness                                                   #
# --------------------------------------------------------------------------- #


def test_single_incident_returns_exact_deltas(db: Session) -> None:
    # Arrange: ack after 5 min, resolve after 1 hour.
    service = _make_service(db)
    _make_incident(
        db,
        service,
        opened_at=_BASE,
        acknowledged_at=_BASE + timedelta(minutes=5),
        resolved_at=_BASE + timedelta(hours=1),
        status=IncidentStatus.resolved,
    )

    # Act
    mtta, mttr = compute_mtta_mttr(db)

    # Assert
    assert mtta == 300.0
    assert mttr == 3600.0


# --------------------------------------------------------------------------- #
# Window filtering                                                            #
# --------------------------------------------------------------------------- #


def test_window_excludes_incidents_opened_before_the_window(db: Session) -> None:
    # Arrange: one incident opened ~10 days ago (acked + resolved) and one opened
    # ~1 hour ago. A 24h window must only see the recent one.
    service = _make_service(db)
    now = datetime.now(UTC)
    old_open = now - timedelta(days=10)
    recent_open = now - timedelta(hours=1)

    _make_incident(
        db,
        service,
        opened_at=old_open,
        acknowledged_at=old_open + timedelta(seconds=1000),
        resolved_at=old_open + timedelta(seconds=5000),
        status=IncidentStatus.resolved,
    )
    _make_incident(
        db,
        service,
        opened_at=recent_open,
        acknowledged_at=recent_open + timedelta(seconds=50),
        resolved_at=recent_open + timedelta(seconds=200),
        status=IncidentStatus.resolved,
    )

    # Act
    mtta, mttr = compute_mtta_mttr(db, window=timedelta(hours=24))

    # Assert: only the recent incident's deltas survive the window filter.
    assert mtta == 50.0
    assert mttr == 200.0


def test_none_window_includes_all_incidents_all_time(db: Session) -> None:
    # Arrange: same two incidents as the windowed test.
    service = _make_service(db)
    now = datetime.now(UTC)
    old_open = now - timedelta(days=10)
    recent_open = now - timedelta(hours=1)

    _make_incident(
        db,
        service,
        opened_at=old_open,
        acknowledged_at=old_open + timedelta(seconds=1000),
        resolved_at=old_open + timedelta(seconds=5000),
        status=IncidentStatus.resolved,
    )
    _make_incident(
        db,
        service,
        opened_at=recent_open,
        acknowledged_at=recent_open + timedelta(seconds=50),
        resolved_at=recent_open + timedelta(seconds=200),
        status=IncidentStatus.resolved,
    )

    # Act: all-time.
    mtta, mttr = compute_mtta_mttr(db, window=None)

    # Assert: both incidents averaged. MTTA = (1000 + 50) / 2, MTTR = (5000 + 200) / 2.
    assert mtta == (1000.0 + 50.0) / 2
    assert mttr == (5000.0 + 200.0) / 2


def test_window_yields_none_when_qualifying_incident_falls_outside(db: Session) -> None:
    # Arrange: a fully resolved incident opened well outside a tight window.
    service = _make_service(db)
    now = datetime.now(UTC)
    old_open = now - timedelta(days=30)
    _make_incident(
        db,
        service,
        opened_at=old_open,
        acknowledged_at=old_open + timedelta(seconds=100),
        resolved_at=old_open + timedelta(seconds=400),
        status=IncidentStatus.resolved,
    )

    # Act: a 1-hour window sees nothing.
    mtta, mttr = compute_mtta_mttr(db, window=timedelta(hours=1))

    # Assert
    assert mtta is None
    assert mttr is None
