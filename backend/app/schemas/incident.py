"""Pydantic schemas for incidents, incident events, and MTTA/MTTR metrics."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import IncidentEventType, IncidentStatus, Severity


class IncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    status: IncidentStatus
    severity: Severity
    service_id: uuid.UUID
    asset_id: uuid.UUID | None
    health_check_id: uuid.UUID | None
    opened_at: datetime
    acknowledged_at: datetime | None
    acknowledged_by_id: uuid.UUID | None
    resolved_at: datetime | None
    resolved_by_id: uuid.UUID | None
    closed_at: datetime | None


class IncidentEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: IncidentEventType
    message: str | None
    actor_id: uuid.UUID | None
    payload: dict[str, Any] | None
    created_at: datetime


class IncidentDetailRead(IncidentRead):
    """An incident plus its ordered event timeline."""

    events: list[IncidentEventRead]


class CommentCreate(BaseModel):
    message: str = Field(min_length=1, max_length=4096)


class MttaMttrRead(BaseModel):
    mtta_seconds: float | None
    mttr_seconds: float | None
    window_hours: int | None
