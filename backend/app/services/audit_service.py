"""Shared audit-logging helpers.

Every create/update/delete/state-change across the app routes through
``record_audit`` so the audit log stays the single immutable source of truth for
"what changed", which the AI triage agent later reads.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.enums import AuditAction


def _jsonable(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def snapshot(obj: Any, *, exclude: set[str] | None = None) -> dict[str, Any]:
    """Serialize an ORM object's column values to a JSON-safe dict for before/after."""
    exclude = exclude or set()
    mapper = inspect(obj).mapper
    return {
        col.key: _jsonable(getattr(obj, col.key))
        for col in mapper.column_attrs
        if col.key not in exclude
    }


def record_audit(
    db: Session,
    *,
    action: AuditAction,
    entity_type: str,
    entity_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    source_ip: str | None = None,
) -> AuditLog:
    """Append an immutable audit entry. Caller owns the surrounding transaction."""
    entry = AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        before=before,
        after=after,
        source_ip=source_ip,
    )
    db.add(entry)
    db.flush()
    return entry
