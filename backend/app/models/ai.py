"""Persisted AI incident-triage results, including a per-call token/cost log."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
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

from app.db.base import Base, UUIDMixin
from app.models.enums import Severity, TriageStatus

if TYPE_CHECKING:
    from app.models.observability import Incident


class AITriageResult(UUIDMixin, Base):
    __tablename__ = "ai_triage_results"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[TriageStatus] = mapped_column(
        SAEnum(TriageStatus, native_enum=False, length=12), nullable=False
    )
    model: Mapped[str | None] = mapped_column(String(64))

    # Structured, schema-validated output from the model.
    root_cause_hypothesis: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)  # 0.0 .. 1.0
    severity_assessment: Mapped[Severity | None] = mapped_column(
        SAEnum(Severity, native_enum=False, length=16)
    )
    remediation_steps: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    stakeholder_comms_draft: Mapped[str | None] = mapped_column(Text)

    # Token / cost log.
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # True for seeded/illustrative demo output (no live API call was made).
    is_seeded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    raw_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    incident: Mapped[Incident] = relationship(back_populates="triage_results")
