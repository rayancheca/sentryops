"""Worker entrypoint: a health-check scheduler thread + an RQ triage worker.

Run as ``python -m app.workers.run`` (the compose ``worker`` service). The
scheduler loop probes due health checks, records results, drives incident
open/close transitions, and enqueues triage for newly opened incidents. The RQ
worker processes those triage jobs.
"""

from __future__ import annotations

import threading
import time
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from rq import Worker

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import session_scope
from app.workers.queue import redis_conn, triage_queue
from app.workers.tasks import enqueue_triage

log = structlog.get_logger(__name__)


def _run_due_checks() -> list[uuid.UUID]:
    """Probe every enabled check that is due; return any newly opened incident ids."""
    from app.models.observability import CheckResult, HealthCheck
    from app.observability.checks import run_check_sync
    from app.services.incident_service import evaluate_after_result
    from app.services.observability_service import record_check_result

    opened: list[uuid.UUID] = []
    now = datetime.now(UTC)
    with session_scope() as db:
        checks = db.query(HealthCheck).filter(HealthCheck.enabled.is_(True)).all()
        for check in checks:
            last = (
                db.query(CheckResult)
                .filter(CheckResult.health_check_id == check.id)
                .order_by(CheckResult.created_at.desc())
                .first()
            )
            due = last is None or (now - last.created_at) >= timedelta(
                seconds=check.interval_seconds
            )
            if not due:
                continue
            outcome = run_check_sync(check)
            record_check_result(db, check, outcome)
            db.flush()
            incident = evaluate_after_result(db, check)
            if incident is not None:
                opened.append(incident.id)
    # session_scope has committed here; safe to enqueue against persisted rows.
    return opened


def scheduler_loop() -> None:
    interval = get_settings().healthcheck_interval_seconds
    log.info("scheduler_started", interval_seconds=interval)
    while True:
        try:
            for incident_id in _run_due_checks():
                enqueue_triage(incident_id)
        except Exception as exc:  # keep the loop alive; log and continue
            log.error("scheduler_tick_failed", error=str(exc))
        time.sleep(interval)


def main() -> None:
    configure_logging()
    log.info("worker_starting")
    threading.Thread(target=scheduler_loop, daemon=True).start()
    Worker([triage_queue], connection=redis_conn).work(with_scheduler=False)


if __name__ == "__main__":
    main()
