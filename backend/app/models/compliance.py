"""Compliance evaluation runs (historical snapshots) and per-asset results."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDMixin
from app.models.enums import ComplianceStatus, Severity

if TYPE_CHECKING:
    from app.models.asset import Asset
    from app.models.user import User


class ComplianceRun(UUIDMixin, Base):
    """One evaluation pass over all in-scope assets. Each run is a drift snapshot."""

    __tablename__ = "compliance_runs"

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    total_assets: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    org_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    passed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    not_applicable_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Failing-control counts by severity, e.g. {"critical": 2, "high": 5, ...}.
    severity_failing: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )

    triggered_by: Mapped[User | None] = relationship()
    results: Mapped[list[ComplianceResult]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class ComplianceResult(UUIDMixin, Base):
    __tablename__ = "compliance_results"
    __table_args__ = (
        Index("ix_compliance_results_run_asset", "run_id", "asset_id"),
        Index("ix_compliance_results_asset_recent", "asset_id", "created_at"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("compliance_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    rule_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[ComplianceStatus] = mapped_column(
        SAEnum(ComplianceStatus, native_enum=False, length=20), nullable=False
    )
    # Denormalized from the rule definition so historical results survive rule edits.
    severity: Mapped[Severity] = mapped_column(
        SAEnum(Severity, native_enum=False, length=16), nullable=False
    )
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    run: Mapped[ComplianceRun] = relationship(back_populates="results")
    asset: Mapped[Asset] = relationship()
