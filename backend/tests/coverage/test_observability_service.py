"""Behavioral tests for observability analytics (app/services/observability_service.py).

Seeds services, checks, and check-result time series via the ``db`` fixture and
asserts the uptime / error-budget / status-grid math against known mixes. Results
are inserted with explicit ``created_at`` so window filtering is deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.enums import CheckStatus, CheckType, IncidentStatus
from app.models.observability import CheckResult, HealthCheck, Incident, Service
from app.services.observability_service import (
    error_budget,
    service_uptime,
    status_grid,
    uptime_ratio,
)

pytestmark = pytest.mark.integration


def _make_service(db: Session, name: str, *, slo_target: float = 0.999) -> Service:
    service = Service(name=name, slo_target=slo_target)
    db.add(service)
    db.flush()
    return service


def _make_check(
    db: Session, service: Service, *, name: str = "probe", enabled: bool = True
) -> HealthCheck:
    check = HealthCheck(
        service_id=service.id,
        name=name,
        check_type=CheckType.http,
        target="https://svc.test.local/health",
        expected_status=200,
        latency_budget_ms=1000,
        enabled=enabled,
    )
    db.add(check)
    db.flush()
    return check


def _insert_result(db: Session, check: HealthCheck, status: CheckStatus, *, at: datetime) -> None:
    db.add(
        CheckResult(
            health_check_id=check.id,
            status=status,
            latency_ms=42.0,
            status_code=200 if status is CheckStatus.up else 503,
            error=None if status is CheckStatus.up else "down",
            created_at=at,
        )
    )
    db.flush()


# --------------------------------------------------------------------------- #
# uptime_ratio
# --------------------------------------------------------------------------- #


def test_uptime_ratio_mixed_window(db: Session) -> None:
    # Arrange — 3 UP + 1 DOWN inside the window.
    service = _make_service(db, "uptime-mixed")
    check = _make_check(db, service)
    now = datetime.now(UTC)
    _insert_result(db, check, CheckStatus.up, at=now - timedelta(minutes=4))
    _insert_result(db, check, CheckStatus.up, at=now - timedelta(minutes=3))
    _insert_result(db, check, CheckStatus.down, at=now - timedelta(minutes=2))
    _insert_result(db, check, CheckStatus.up, at=now - timedelta(minutes=1))

    # Act / Assert
    assert uptime_ratio(db, check.id, timedelta(hours=1)) == pytest.approx(0.75)


def test_uptime_ratio_no_data_defaults_to_one(db: Session) -> None:
    # Arrange — a check with no results.
    service = _make_service(db, "uptime-empty")
    check = _make_check(db, service)

    # Act / Assert — nothing observed means nothing known to be down.
    assert uptime_ratio(db, check.id, timedelta(hours=1)) == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# service_uptime (pooled across all of a service's checks)
# --------------------------------------------------------------------------- #


def test_service_uptime_pools_results_across_checks(db: Session) -> None:
    # Arrange — two checks on one service: check A all UP, check B half DOWN.
    service = _make_service(db, "pooled")
    check_a = _make_check(db, service, name="a")
    check_b = _make_check(db, service, name="b")
    now = datetime.now(UTC)
    _insert_result(db, check_a, CheckStatus.up, at=now - timedelta(minutes=3))
    _insert_result(db, check_a, CheckStatus.up, at=now - timedelta(minutes=2))
    _insert_result(db, check_b, CheckStatus.up, at=now - timedelta(minutes=2))
    _insert_result(db, check_b, CheckStatus.down, at=now - timedelta(minutes=1))

    # Act — 3 UP / 4 total across the pooled set.
    ratio = service_uptime(db, service.id, timedelta(hours=1))

    # Assert
    assert ratio == pytest.approx(0.75)


def test_service_uptime_no_data_defaults_to_one(db: Session) -> None:
    # Arrange — a service whose single check has no results.
    service = _make_service(db, "service-empty")
    _make_check(db, service)

    # Act / Assert
    assert service_uptime(db, service.id, timedelta(hours=1)) == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# error_budget (pure math)
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_error_budget_partial_burn() -> None:
    # Arrange — 99.9% SLO, observed 99.95% uptime.
    budget = error_budget(slo_target=0.999, observed_uptime=0.9995)

    # Assert — budget=0.001, consumed=0.0005, burn=0.5, remaining=0.0005.
    assert budget["budget"] == pytest.approx(0.001)
    assert budget["consumed"] == pytest.approx(0.0005)
    assert budget["burn_rate"] == pytest.approx(0.5)
    assert budget["remaining"] == pytest.approx(0.0005)


@pytest.mark.unit
def test_error_budget_breached_goes_negative() -> None:
    # Arrange — observed uptime worse than the SLO allows.
    budget = error_budget(slo_target=0.99, observed_uptime=0.95)

    # Assert — consumed (0.05) exceeds budget (0.01); remaining is negative.
    assert budget["budget"] == pytest.approx(0.01)
    assert budget["consumed"] == pytest.approx(0.05)
    assert budget["burn_rate"] == pytest.approx(5.0)
    assert budget["remaining"] == pytest.approx(-0.04)


@pytest.mark.unit
def test_error_budget_perfect_slo_has_zero_burn_rate() -> None:
    # Arrange — a 100% SLO has no budget to divide against.
    budget = error_budget(slo_target=1.0, observed_uptime=0.99)

    # Assert — burn_rate is reported as 0.0 rather than dividing by zero.
    assert budget["budget"] == pytest.approx(0.0)
    assert budget["burn_rate"] == pytest.approx(0.0)


@pytest.mark.unit
def test_error_budget_full_uptime_consumes_nothing() -> None:
    # Arrange — perfect observed uptime.
    budget = error_budget(slo_target=0.99, observed_uptime=1.0)

    # Assert — consumed is clamped at 0; the whole budget remains.
    assert budget["consumed"] == pytest.approx(0.0)
    assert budget["burn_rate"] == pytest.approx(0.0)
    assert budget["remaining"] == pytest.approx(0.01)


# --------------------------------------------------------------------------- #
# status_grid
# --------------------------------------------------------------------------- #


def test_status_grid_derives_down_from_latest_enabled_check(db: Session) -> None:
    # Arrange — one healthy service and one whose latest result is DOWN.
    healthy = _make_service(db, "alpha")
    h_check = _make_check(db, healthy)
    now = datetime.now(UTC)
    _insert_result(db, h_check, CheckStatus.up, at=now - timedelta(minutes=1))

    failing = _make_service(db, "beta")
    f_check = _make_check(db, failing)
    _insert_result(db, f_check, CheckStatus.up, at=now - timedelta(minutes=3))
    _insert_result(db, f_check, CheckStatus.down, at=now - timedelta(minutes=1))

    # Act — grid is ordered by service name (alpha, beta).
    grid = status_grid(db)

    # Assert
    by_name = {row["service_name"]: row for row in grid}
    assert by_name["alpha"]["status"] is CheckStatus.up
    assert by_name["beta"]["status"] is CheckStatus.down
    assert by_name["beta"]["check_count"] == 1
    assert by_name["beta"]["last_checked_at"] is not None
    # beta: latest DOWN among 1 UP + 1 DOWN -> 0.5 uptime over the 24h window.
    assert by_name["beta"]["uptime_24h"] == pytest.approx(0.5)


def test_status_grid_service_with_no_results_is_up(db: Session) -> None:
    # Arrange — a service whose check has never run.
    service = _make_service(db, "untested")
    _make_check(db, service)

    # Act
    grid = status_grid(db)

    # Assert — no data means treated as UP, full uptime, no last-checked stamp.
    row = next(r for r in grid if r["service_name"] == "untested")
    assert row["status"] is CheckStatus.up
    assert row["uptime_24h"] == pytest.approx(1.0)
    assert row["last_checked_at"] is None


def test_status_grid_disabled_down_check_does_not_force_down(db: Session) -> None:
    # Arrange — the only failing check is disabled, so the service stays UP.
    service = _make_service(db, "disabled-fail")
    disabled = _make_check(db, service, name="disabled", enabled=False)
    now = datetime.now(UTC)
    _insert_result(db, disabled, CheckStatus.down, at=now - timedelta(minutes=1))

    # Act
    grid = status_grid(db)

    # Assert — derived status ignores the disabled check's DOWN result.
    row = next(r for r in grid if r["service_name"] == "disabled-fail")
    assert row["status"] is CheckStatus.up


def test_status_grid_counts_open_incidents(db: Session) -> None:
    # Arrange — a service with one open and one resolved incident.
    service = _make_service(db, "incident-svc")
    _make_check(db, service)
    opened = datetime.now(UTC) - timedelta(hours=1)
    db.add(
        Incident(
            service_id=service.id, title="open one", status=IncidentStatus.open, opened_at=opened
        )
    )
    db.add(
        Incident(
            service_id=service.id,
            title="resolved one",
            status=IncidentStatus.resolved,
            opened_at=opened,
        )
    )
    db.flush()

    # Act
    grid = status_grid(db)

    # Assert — only open/acknowledged incidents are counted.
    row = next(r for r in grid if r["service_name"] == "incident-svc")
    assert row["open_incidents"] == 1
