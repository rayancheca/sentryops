"""Assets (CMDB core), tags, the directed dependency graph, and check-in/out."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import AssetType, Environment, LifecycleState

if TYPE_CHECKING:
    from app.models.user import User

# Many-to-many association between assets and tags.
asset_tags = Table(
    "asset_tags",
    Base.metadata,
    Column("asset_id", ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tags"

    name: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    color: Mapped[str] = mapped_column(String(20), default="#64748b", nullable=False)

    assets: Mapped[list[Asset]] = relationship(secondary=asset_tags, back_populates="tags")


class Asset(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "assets"

    # Short, human-friendly code printed on the QR label (e.g. "SVR-7Q2KX").
    short_code: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    asset_type: Mapped[AssetType] = mapped_column(
        SAEnum(AssetType, native_enum=False, length=32), nullable=False
    )
    lifecycle_state: Mapped[LifecycleState] = mapped_column(
        SAEnum(LifecycleState, native_enum=False, length=20),
        default=LifecycleState.active,
        nullable=False,
    )
    environment: Mapped[Environment] = mapped_column(
        SAEnum(Environment, native_enum=False, length=16),
        default=Environment.prod,
        nullable=False,
    )
    location: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    # Security-posture facts evaluated by the compliance engine (typed keys
    # documented in app/schemas/asset.py::AssetAttributes).
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    # Arbitrary user-defined fields; not interpreted by the engine.
    custom_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )

    owner: Mapped[User | None] = relationship(
        back_populates="owned_assets", foreign_keys=[owner_id]
    )
    tags: Mapped[list[Tag]] = relationship(secondary=asset_tags, back_populates="assets")
    dependencies_out: Mapped[list[AssetDependency]] = relationship(
        foreign_keys="AssetDependency.source_asset_id",
        back_populates="source",
        cascade="all, delete-orphan",
    )
    dependencies_in: Mapped[list[AssetDependency]] = relationship(
        foreign_keys="AssetDependency.target_asset_id",
        back_populates="target",
        cascade="all, delete-orphan",
    )


class AssetDependency(UUIDMixin, TimestampMixin, Base):
    """Directed edge: ``source`` depends on ``target``."""

    __tablename__ = "asset_dependencies"
    __table_args__ = (
        UniqueConstraint("source_asset_id", "target_asset_id", name="dependency_edge"),
        CheckConstraint("source_asset_id <> target_asset_id", name="no_self_dependency"),
    )

    source_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    target_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str | None] = mapped_column(String(50))

    source: Mapped[Asset] = relationship(
        foreign_keys=[source_asset_id], back_populates="dependencies_out"
    )
    target: Mapped[Asset] = relationship(
        foreign_keys=[target_asset_id], back_populates="dependencies_in"
    )


class AssetCheckout(UUIDMixin, TimestampMixin, Base):
    """A check-out record; the current holder is the row with ``checked_in_at IS NULL``."""

    __tablename__ = "asset_checkouts"
    __table_args__ = (
        # Fast "who currently holds asset X" lookup.
        Index("ix_checkout_asset_active", "asset_id", "checked_in_at"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    holder_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    checked_out_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    checked_out_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    asset: Mapped[Asset] = relationship()
    holder: Mapped[User | None] = relationship(foreign_keys=[holder_id])
    checked_out_by: Mapped[User | None] = relationship(foreign_keys=[checked_out_by_id])
