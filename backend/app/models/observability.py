"""Services, health checks, check-result time series, and incidents."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import (
    CheckStatus,
    CheckType,
    IncidentEventType,
    IncidentStatus,
    Severity,
)

if TYPE_CHECKING:
    from app.models.ai import AITriageResult
    from app.models.asset import Asset
    from app.models.user import User


class Service(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "services"

    name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL"), index=True
    )
    # SLO target as a fraction, e.g. 0.999 for "three nines".
    slo_target: Mapped[float] = mapped_column(Float, default=0.999, nullable=False)

    asset: Mapped[Asset | None] = relationship()
    health_checks: Mapped[list[HealthCheck]] = relationship(
        back_populates="service", cascade="all, delete-orphan"
    )
    incidents: Mapped[list[Incident]] = relationship(back_populates="service")


class HealthCheck(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "health_checks"

    service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    check_type: Mapped[CheckType] = mapped_column(
        SAEnum(CheckType, native_enum=False, length=8), nullable=False
    )
    # URL for HTTP checks; host for TCP checks.
    target: Mapped[str] = mapped_column(String(512), nullable=False)
    method: Mapped[str] = mapped_column(String(8), default="GET", nullable=False)
    expected_status: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    latency_budget_ms: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    port: Mapped[int | None] = mapped_column(Integer)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    service: Mapped[Service] = relationship(back_populates="health_checks")
    results: Mapped[list[CheckResult]] = relationship(
        back_populates="health_check", cascade="all, delete-orphan"
    )


class CheckResult(UUIDMixin, Base):
    __tablename__ = "check_results"
    __table_args__ = (
        # Composite (health_check_id, created_at): every uptime/SLO query asks
        # "results for this check within the last 24h/7d/30d", so we filter by
        # check then range-scan by time. This is the workhorse read path.
        Index("ix_check_results_check_recent", "health_check_id", "created_at"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    health_check_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("health_checks.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[CheckStatus] = mapped_column(
        SAEnum(CheckStatus, native_enum=False, length=8), nullable=False
    )
    latency_ms: Mapped[float | None] = mapped_column(Float)
    status_code: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)

    health_check: Mapped[HealthCheck] = relationship(back_populates="results")


class Incident(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "incidents"
    __table_args__ = (Index("ix_incidents_status_opened", "status", "opened_at"),)

    service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), index=True, nullable=False
    )
    health_check_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("health_checks.id", ondelete="SET NULL")
    )
    # Denormalized link to the failing asset for blast-radius and AI triage.
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[IncidentStatus] = mapped_column(
        SAEnum(IncidentStatus, native_enum=False, length=16),
        default=IncidentStatus.open,
        index=True,
        nullable=False,
    )
    severity: Mapped[Severity] = mapped_column(
        SAEnum(Severity, native_enum=False, length=16),
        default=Severity.high,
        nullable=False,
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    service: Mapped[Service] = relationship(back_populates="incidents")
    asset: Mapped[Asset | None] = relationship()
    acknowledged_by: Mapped[User | None] = relationship(foreign_keys=[acknowledged_by_id])
    resolved_by: Mapped[User | None] = relationship(foreign_keys=[resolved_by_id])
    events: Mapped[list[IncidentEvent]] = relationship(
        back_populates="incident",
        cascade="all, delete-orphan",
        order_by="IncidentEvent.created_at",
    )
    triage_results: Mapped[list[AITriageResult]] = relationship(
        back_populates="incident",
        cascade="all, delete-orphan",
        order_by="AITriageResult.created_at",
    )


class IncidentEvent(UUIDMixin, Base):
    __tablename__ = "incident_events"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_type: Mapped[IncidentEventType] = mapped_column(
        SAEnum(IncidentEventType, native_enum=False, length=16), nullable=False
    )
    message: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    incident: Mapped[Incident] = relationship(back_populates="events")
    actor: Mapped[User | None] = relationship()
