"""Audit-log read projection. The audit log is append-only — no write schema."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import AuditAction


class AuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action: AuditAction
    entity_type: str
    entity_id: uuid.UUID | None
    actor_id: uuid.UUID | None
    before: dict[str, object] | None
    after: dict[str, object] | None
    source_ip: str | None
    created_at: datetime
