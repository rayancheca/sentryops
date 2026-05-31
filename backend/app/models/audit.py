"""Immutable audit log.

Append-only by design: there is no update or delete path in the service layer,
and the table carries only ``created_at`` (no ``updated_at``). It is both a
compliance signal and the AI triage agent's "what changed recently" source.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDMixin
from app.models.enums import AuditAction

if TYPE_CHECKING:
    from app.models.user import User


class AuditLog(UUIDMixin, Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        # Composite index ordered (entity_type, entity_id, created_at): the AI
        # context bundle and the per-entity history view both query "the most
        # recent N changes for this specific entity", so the leading columns
        # narrow to one entity and the trailing column serves the time ordering.
        Index("ix_audit_entity_recent", "entity_type", "entity_id", "created_at"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[AuditAction] = mapped_column(
        SAEnum(AuditAction, native_enum=False, length=20), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column()
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    source_ip: Mapped[str | None] = mapped_column(String(64))

    actor: Mapped[User | None] = relationship()
