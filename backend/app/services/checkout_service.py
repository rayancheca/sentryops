"""Asset check-in/out service.

An asset is "checked out" while a row exists with ``checked_in_at IS NULL``;
check-in stamps that row. Both transitions are audited (``checkout``/``checkin``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.models.asset import Asset, AssetCheckout
from app.models.enums import AuditAction
from app.models.user import User
from app.services.audit_service import record_audit, snapshot

_AUDIT_ENTITY = "asset_checkout"


def current_holder(db: Session, asset_id: uuid.UUID) -> AssetCheckout | None:
    """Return the open check-out row for ``asset_id`` (holder), or ``None``."""
    return db.execute(
        select(AssetCheckout)
        .where(AssetCheckout.asset_id == asset_id)
        .where(AssetCheckout.checked_in_at.is_(None))
        .order_by(AssetCheckout.checked_out_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def history(db: Session, asset_id: uuid.UUID) -> list[AssetCheckout]:
    """All check-out records for an asset, newest first."""
    return list(
        db.execute(
            select(AssetCheckout)
            .where(AssetCheckout.asset_id == asset_id)
            .order_by(AssetCheckout.checked_out_at.desc())
        ).scalars()
    )


def check_out(
    db: Session,
    asset: Asset,
    holder_id: uuid.UUID,
    actor: User,
    *,
    notes: str | None = None,
    source_ip: str | None = None,
) -> AssetCheckout:
    """Check ``asset`` out to ``holder_id``. Raises if it is already out."""
    if current_holder(db, asset.id) is not None:
        raise ConflictError("Asset is already checked out.", details={"asset_id": str(asset.id)})

    record = AssetCheckout(
        asset_id=asset.id,
        holder_id=holder_id,
        checked_out_by_id=actor.id,
        notes=notes,
    )
    db.add(record)
    db.flush()
    record_audit(
        db,
        action=AuditAction.checkout,
        entity_type=_AUDIT_ENTITY,
        entity_id=record.id,
        actor_id=actor.id,
        after=snapshot(record),
        source_ip=source_ip,
    )
    return record


def check_in(
    db: Session,
    asset: Asset,
    actor: User,
    *,
    source_ip: str | None = None,
) -> AssetCheckout:
    """Check ``asset`` back in. Raises if it is not currently out."""
    record = current_holder(db, asset.id)
    if record is None:
        raise ConflictError(
            "Asset is not currently checked out.", details={"asset_id": str(asset.id)}
        )

    before = snapshot(record)
    record.checked_in_at = datetime.now(UTC)
    db.flush()
    record_audit(
        db,
        action=AuditAction.checkin,
        entity_type=_AUDIT_ENTITY,
        entity_id=record.id,
        actor_id=actor.id,
        before=before,
        after=snapshot(record),
        source_ip=source_ip,
    )
    return record
