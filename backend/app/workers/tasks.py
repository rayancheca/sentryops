"""Background task definitions and enqueue helpers."""

from __future__ import annotations

import uuid

import structlog

from app.db.session import session_scope
from app.workers.queue import triage_queue

log = structlog.get_logger(__name__)


def enqueue_triage(incident_id: uuid.UUID) -> None:
    """Enqueue an AI triage job for a freshly opened incident."""
    triage_queue.enqueue("app.workers.tasks.run_triage_job", str(incident_id))


def run_triage_job(incident_id: str) -> None:
    """RQ entrypoint: load the incident and run triage (no-op if it vanished)."""
    from app.ai.triage import run_triage
    from app.models.observability import Incident

    with session_scope() as db:
        incident = db.get(Incident, uuid.UUID(incident_id))
        if incident is None:
            log.warning("triage_job_missing_incident", incident_id=incident_id)
            return
        run_triage(db, incident)
