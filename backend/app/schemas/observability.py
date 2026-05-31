"""Pydantic schemas for services, health checks, results, and uptime/status."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CheckStatus, CheckType

# Bounds shared by create/update validation.
_MIN_INTERVAL_SECONDS = 5
_MAX_INTERVAL_SECONDS = 86_400
_MIN_LATENCY_BUDGET_MS = 1
_MAX_LATENCY_BUDGET_MS = 120_000
_MIN_PORT = 1
_MAX_PORT = 65_535


# --------------------------------------------------------------------------- #
# Services
# --------------------------------------------------------------------------- #
class ServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4096)
    asset_id: uuid.UUID | None = None
    slo_target: float = Field(default=0.999, ge=0.0, le=1.0)


class ServiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    asset_id: uuid.UUID | None
    slo_target: float
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Health checks
# --------------------------------------------------------------------------- #
class HealthCheckCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    check_type: CheckType
    target: str = Field(min_length=1, max_length=512)
    method: str = Field(default="GET", min_length=1, max_length=8)
    expected_status: int = Field(default=200, ge=100, le=599)
    latency_budget_ms: int = Field(
        default=1000, ge=_MIN_LATENCY_BUDGET_MS, le=_MAX_LATENCY_BUDGET_MS
    )
    port: int | None = Field(default=None, ge=_MIN_PORT, le=_MAX_PORT)
    interval_seconds: int = Field(default=60, ge=_MIN_INTERVAL_SECONDS, le=_MAX_INTERVAL_SECONDS)
    enabled: bool = True


class HealthCheckUpdate(BaseModel):
    """All fields optional; only provided fields are applied (PATCH semantics)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    target: str | None = Field(default=None, min_length=1, max_length=512)
    method: str | None = Field(default=None, min_length=1, max_length=8)
    expected_status: int | None = Field(default=None, ge=100, le=599)
    latency_budget_ms: int | None = Field(
        default=None, ge=_MIN_LATENCY_BUDGET_MS, le=_MAX_LATENCY_BUDGET_MS
    )
    port: int | None = Field(default=None, ge=_MIN_PORT, le=_MAX_PORT)
    interval_seconds: int | None = Field(
        default=None, ge=_MIN_INTERVAL_SECONDS, le=_MAX_INTERVAL_SECONDS
    )
    enabled: bool | None = None


class HealthCheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_id: uuid.UUID
    name: str
    check_type: CheckType
    target: str
    method: str
    expected_status: int
    latency_budget_ms: int
    port: int | None
    interval_seconds: int
    enabled: bool
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Check results + uptime/status
# --------------------------------------------------------------------------- #
class CheckResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    health_check_id: uuid.UUID
    status: CheckStatus
    latency_ms: float | None
    status_code: int | None
    error: str | None
    created_at: datetime


class UptimeRead(BaseModel):
    window_hours: int
    uptime: float
    slo_target: float
    error_budget: dict[str, float]


class StatusGridItem(BaseModel):
    service_id: uuid.UUID
    service_name: str
    asset_id: uuid.UUID | None
    status: CheckStatus
    uptime_24h: float
    slo_target: float
    check_count: int
    open_incidents: int
    last_checked_at: datetime | None = None
    extra: dict[str, Any] | None = None
