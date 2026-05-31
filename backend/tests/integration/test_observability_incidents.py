"""Integration tests for the observability + incident lifecycle.

Covers the bridge from synthetic check results to operator incidents:
auto-open on consecutive DOWN, auto-recover on consecutive UP, the manual
acknowledge/resolve transitions, and the ``uptime_ratio`` aggregation. Check
results are inserted with explicit, monotonically increasing ``created_at``
timestamps so the "most recent N" ordering in the service is deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.enums import (
    CheckStatus,
    CheckType,
    IncidentEventType,
    IncidentStatus,
    Role,
)
from app.models.observability import (
    CheckResult,
    HealthCheck,
    Incident,
    IncidentEvent,
    Service,
)
from app.models.user import User
from app.services import incident_service
from app.services.observability_service import uptime_ratio

pytestmark = pytest.mark.integration

_BASE_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def _make_user(db: Session, email: str) -> User:
    user = User(
        email=email,
        full_name="Operator",
        hashed_password="x",
        role=Role.operator,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _make_service_with_check(db: Session) -> tuple[Service, HealthCheck]:
    service = Service(name="checkout-api", slo_target=0.999)
    db.add(service)
    db.flush()
    check = HealthCheck(
        service_id=service.id,
        name="https probe",
        check_type=CheckType.http,
        target="https://checkout.test.local/health",
        expected_status=200,
        latency_budget_ms=1000,
        enabled=True,
    )
    db.add(check)
    db.flush()
    # Refresh the relationship so check.service is populated for the service.
    db.refresh(check)
    return service, check


def _insert_result(
    db: Session,
    check: HealthCheck,
    status: CheckStatus,
    *,
    at: datetime,
) -> CheckResult:
    result = CheckResult(
        health_check_id=check.id,
        status=status,
        latency_ms=42.0,
        status_code=200 if status is CheckStatus.up else 503,
        error=None if status is CheckStatus.up else "down",
        created_at=at,
    )
    db.add(result)
    db.flush()
    return result


def _insert_sequence(
    db: Session,
    check: HealthCheck,
    statuses: list[CheckStatus],
    *,
    start: datetime = _BASE_TIME,
) -> None:
    """Insert results with strictly increasing created_at (oldest first)."""
    for index, status in enumerate(statuses):
        _insert_result(db, check, status, at=start + timedelta(minutes=index))


def test_incident_opens_after_threshold_consecutive_down(db: Session) -> None:
    # Arrange — N consecutive DOWN results, where N == the open threshold.
    settings = get_settings()
    threshold = settings.incident_open_threshold
    service, check = _make_service_with_check(db)
    _insert_sequence(db, check, [CheckStatus.down] * threshold)

    # Act
    incident = incident_service.evaluate_after_result(db, check)
    db.flush()

    # Assert — an incident is opened and linked to the service/check.
    assert incident is not None
    assert incident.status is IncidentStatus.open
    assert incident.service_id == service.id
    assert incident.health_check_id == check.id
    assert incident.opened_at is not None

    # An "opened" timeline event was recorded.
    events = db.query(IncidentEvent).filter(IncidentEvent.incident_id == incident.id).all()
    assert any(e.event_type is IncidentEventType.opened for e in events)


def test_no_incident_below_threshold(db: Session) -> None:
    # Arrange — one fewer DOWN than the open threshold.
    threshold = get_settings().incident_open_threshold
    _service, check = _make_service_with_check(db)
    _insert_sequence(db, check, [CheckStatus.down] * (threshold - 1))

    # Act
    incident = incident_service.evaluate_after_result(db, check)
    db.flush()

    # Assert — nothing opens, and no incident exists for the service.
    assert incident is None
    assert db.query(Incident).count() == 0


def test_recent_up_result_prevents_open(db: Session) -> None:
    # Arrange — the most recent result is UP, so the DOWN streak is broken.
    threshold = get_settings().incident_open_threshold
    _service, check = _make_service_with_check(db)
    statuses = [CheckStatus.down] * threshold + [CheckStatus.up]
    _insert_sequence(db, check, statuses)

    # Act
    incident = incident_service.evaluate_after_result(db, check)
    db.flush()

    # Assert
    assert incident is None
    assert db.query(Incident).count() == 0


def test_no_duplicate_incident_while_one_is_live(db: Session) -> None:
    # Arrange — open an incident, then evaluate again on more DOWN results.
    threshold = get_settings().incident_open_threshold
    _service, check = _make_service_with_check(db)
    _insert_sequence(db, check, [CheckStatus.down] * threshold)
    first = incident_service.evaluate_after_result(db, check)
    db.flush()
    assert first is not None

    # Act — additional DOWN results arrive while the incident is still open.
    _insert_sequence(
        db,
        check,
        [CheckStatus.down] * threshold,
        start=_BASE_TIME + timedelta(hours=1),
    )
    second = incident_service.evaluate_after_result(db, check)
    db.flush()

    # Assert — no second incident opens; exactly one incident exists.
    assert second is None
    assert db.query(Incident).count() == 1


def test_acknowledge_incident_sets_status_and_timestamp(db: Session) -> None:
    # Arrange
    threshold = get_settings().incident_open_threshold
    _service, check = _make_service_with_check(db)
    _insert_sequence(db, check, [CheckStatus.down] * threshold)
    incident = incident_service.evaluate_after_result(db, check)
    db.flush()
    assert incident is not None
    actor = _make_user(db, "ack@test.local")

    # Act
    acked = incident_service.acknowledge_incident(db, incident, actor)
    db.flush()

    # Assert
    assert acked.status is IncidentStatus.acknowledged
    assert acked.acknowledged_at is not None
    assert acked.acknowledged_by_id == actor.id
    events = db.query(IncidentEvent).filter(IncidentEvent.incident_id == incident.id).all()
    assert any(e.event_type is IncidentEventType.acknowledged for e in events)


def test_resolve_incident_sets_resolved_closed_and_status(db: Session) -> None:
    # Arrange
    threshold = get_settings().incident_open_threshold
    _service, check = _make_service_with_check(db)
    _insert_sequence(db, check, [CheckStatus.down] * threshold)
    incident = incident_service.evaluate_after_result(db, check)
    db.flush()
    assert incident is not None
    actor = _make_user(db, "resolver@test.local")

    # Act
    resolved = incident_service.resolve_incident(db, incident, actor)
    db.flush()

    # Assert
    assert resolved.status is IncidentStatus.closed
    assert resolved.resolved_at is not None
    assert resolved.closed_at is not None
    assert resolved.resolved_by_id == actor.id
    events = {
        e.event_type
        for e in db.query(IncidentEvent).filter(IncidentEvent.incident_id == incident.id).all()
    }
    assert IncidentEventType.resolved in events
    assert IncidentEventType.closed in events


def test_recovery_closes_incident_after_consecutive_up(db: Session) -> None:
    # Arrange — open an incident from a DOWN streak.
    settings = get_settings()
    open_threshold = settings.incident_open_threshold
    close_threshold = settings.incident_close_threshold
    _service, check = _make_service_with_check(db)
    _insert_sequence(db, check, [CheckStatus.down] * open_threshold)
    incident = incident_service.evaluate_after_result(db, check)
    db.flush()
    assert incident is not None and incident.status is IncidentStatus.open

    # Act — the service recovers: the most recent M results are all UP.
    _insert_sequence(
        db,
        check,
        [CheckStatus.up] * close_threshold,
        start=_BASE_TIME + timedelta(hours=1),
    )
    recovery = incident_service.evaluate_after_result(db, check)
    db.flush()

    # Assert — recovery returns None and closes/resolves the live incident.
    assert recovery is None
    db.refresh(incident)
    assert incident.status is IncidentStatus.closed
    assert incident.resolved_at is not None
    assert incident.closed_at is not None
    events = {
        e.event_type
        for e in db.query(IncidentEvent).filter(IncidentEvent.incident_id == incident.id).all()
    }
    assert IncidentEventType.recovered in events
    assert IncidentEventType.resolved in events
    assert IncidentEventType.closed in events


def test_recovery_requires_full_up_streak(db: Session) -> None:
    # Arrange — open an incident, then a partial recovery (UP then DOWN).
    settings = get_settings()
    open_threshold = settings.incident_open_threshold
    close_threshold = settings.incident_close_threshold
    _service, check = _make_service_with_check(db)
    _insert_sequence(db, check, [CheckStatus.down] * open_threshold)
    incident = incident_service.evaluate_after_result(db, check)
    db.flush()
    assert incident is not None

    # Act — the most recent result is DOWN again, breaking the UP streak.
    partial = [CheckStatus.up] * close_threshold + [CheckStatus.down]
    _insert_sequence(db, check, partial, start=_BASE_TIME + timedelta(hours=1))
    result = incident_service.evaluate_after_result(db, check)
    db.flush()

    # Assert — the incident stays live (still open).
    assert result is None
    db.refresh(incident)
    assert incident.status is IncidentStatus.open
    assert incident.closed_at is None


def test_add_comment_appends_timeline_event(db: Session) -> None:
    # Arrange
    threshold = get_settings().incident_open_threshold
    _service, check = _make_service_with_check(db)
    _insert_sequence(db, check, [CheckStatus.down] * threshold)
    incident = incident_service.evaluate_after_result(db, check)
    db.flush()
    assert incident is not None
    actor = _make_user(db, "commenter@test.local")

    # Act
    event = incident_service.add_comment(db, incident, actor, "Investigating root cause.")
    db.flush()

    # Assert
    assert event.event_type is IncidentEventType.comment
    assert event.message == "Investigating root cause."
    assert event.actor_id == actor.id


def test_uptime_ratio_on_known_mix(db: Session) -> None:
    # Arrange — 3 UP and 1 DOWN within the window => 0.75 uptime.
    _service, check = _make_service_with_check(db)
    now = datetime.now(UTC)
    _insert_result(db, check, CheckStatus.up, at=now - timedelta(minutes=4))
    _insert_result(db, check, CheckStatus.up, at=now - timedelta(minutes=3))
    _insert_result(db, check, CheckStatus.down, at=now - timedelta(minutes=2))
    _insert_result(db, check, CheckStatus.up, at=now - timedelta(minutes=1))

    # Act
    ratio = uptime_ratio(db, check.id, timedelta(hours=1))

    # Assert
    assert ratio == pytest.approx(0.75)


def test_uptime_ratio_defaults_to_one_with_no_data(db: Session) -> None:
    # Arrange — a check with no recorded results.
    _service, check = _make_service_with_check(db)

    # Act
    ratio = uptime_ratio(db, check.id, timedelta(hours=1))

    # Assert — no data observed means nothing is known to be down.
    assert ratio == pytest.approx(1.0)


def test_uptime_ratio_excludes_results_outside_window(db: Session) -> None:
    # Arrange — one DOWN inside the window, several UP far outside it.
    _service, check = _make_service_with_check(db)
    now = datetime.now(UTC)
    _insert_result(db, check, CheckStatus.down, at=now - timedelta(minutes=1))
    _insert_result(db, check, CheckStatus.up, at=now - timedelta(days=10))
    _insert_result(db, check, CheckStatus.up, at=now - timedelta(days=11))

    # Act — only the recent DOWN counts.
    ratio = uptime_ratio(db, check.id, timedelta(hours=1))

    # Assert
    assert ratio == pytest.approx(0.0)
