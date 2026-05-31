"""Asset (CMDB) service: short-code generation, filtered listing, and audited CRUD.

Services own the unit of work up to ``flush`` and emit audit entries; the route
layer owns the surrounding transaction (``db.commit()``).
"""

from __future__ import annotations

import secrets
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import NotFoundError
from app.models.asset import Asset, Tag, asset_tags
from app.models.enums import AssetType, AuditAction, Environment, LifecycleState
from app.schemas.asset import AssetCreate, AssetUpdate
from app.services.audit_service import record_audit, snapshot

# Crockford-style base32 alphabet (no I/L/O/U) for human-legible QR-printed codes.
_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_CODE_BODY_LEN = 5
_MAX_CODE_ATTEMPTS = 8

# Short, stable prefixes per asset type; keeps printed labels self-describing.
_TYPE_PREFIX: dict[AssetType, str] = {
    AssetType.host: "HST",
    AssetType.network_device: "NET",
    AssetType.service: "SVC",
    AssetType.software_license: "LIC",
    AssetType.cloud_resource: "CLD",
}

_AUDIT_ENTITY = "asset"


def _random_body() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_BODY_LEN))


def generate_short_code(db: Session, asset_type: AssetType) -> str:
    """Return a unique, human-friendly short code like ``HST-7Q2KX``.

    Retries on the (vanishingly unlikely) collision; falls back to a longer body
    so we never loop forever on a saturated namespace.
    """
    prefix = _TYPE_PREFIX.get(asset_type, "AST")
    for attempt in range(_MAX_CODE_ATTEMPTS):
        body = _random_body() + ("" if attempt < _MAX_CODE_ATTEMPTS - 1 else _random_body())
        candidate = f"{prefix}-{body}"
        exists = db.execute(select(Asset.id).where(Asset.short_code == candidate).limit(1)).first()
        if exists is None:
            return candidate
    # Extremely unlikely: defer to a UUID fragment that still fits String(16).
    return f"{prefix}-{uuid.uuid4().hex[:9].upper()}"


def _load_tags(db: Session, tag_ids: list[uuid.UUID]) -> list[Tag]:
    if not tag_ids:
        return []
    unique_ids = list(dict.fromkeys(tag_ids))
    tags = list(db.execute(select(Tag).where(Tag.id.in_(unique_ids))).scalars())
    found = {tag.id for tag in tags}
    missing = [tid for tid in unique_ids if tid not in found]
    if missing:
        raise NotFoundError(
            "One or more tags were not found.",
            details={"tag_ids": [str(tid) for tid in missing]},
        )
    return tags


def get_asset(db: Session, asset_id: uuid.UUID) -> Asset:
    """Load an asset with its tags eagerly, or raise :class:`NotFoundError`."""
    asset = db.execute(
        select(Asset).where(Asset.id == asset_id).options(selectinload(Asset.tags))
    ).scalar_one_or_none()
    if asset is None:
        raise NotFoundError("Asset not found.", details={"asset_id": str(asset_id)})
    return asset


def list_assets(
    db: Session,
    *,
    limit: int,
    offset: int,
    asset_type: AssetType | None = None,
    environment: Environment | None = None,
    lifecycle_state: LifecycleState | None = None,
    owner_id: uuid.UUID | None = None,
    tag_id: uuid.UUID | None = None,
    q: str | None = None,
) -> tuple[list[Asset], int]:
    """Return a filtered, paginated page of assets plus the total match count."""
    stmt = select(Asset)
    if asset_type is not None:
        stmt = stmt.where(Asset.asset_type == asset_type)
    if environment is not None:
        stmt = stmt.where(Asset.environment == environment)
    if lifecycle_state is not None:
        stmt = stmt.where(Asset.lifecycle_state == lifecycle_state)
    if owner_id is not None:
        stmt = stmt.where(Asset.owner_id == owner_id)
    if tag_id is not None:
        stmt = stmt.where(
            Asset.id.in_(select(asset_tags.c.asset_id).where(asset_tags.c.tag_id == tag_id))
        )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Asset.name.ilike(like) | Asset.short_code.ilike(like))

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = int(db.execute(count_stmt).scalar_one())

    page_stmt = stmt.order_by(Asset.created_at.desc()).limit(limit).offset(offset)
    items = list(db.execute(page_stmt).scalars())
    return items, total


def create_asset(
    db: Session,
    payload: AssetCreate,
    *,
    actor_id: uuid.UUID | None = None,
    source_ip: str | None = None,
) -> Asset:
    """Create an asset, attach tags, and record a ``create`` audit entry."""
    tags = _load_tags(db, payload.tag_ids)
    asset = Asset(
        short_code=generate_short_code(db, payload.asset_type),
        name=payload.name,
        asset_type=payload.asset_type,
        environment=payload.environment,
        lifecycle_state=payload.lifecycle_state,
        location=payload.location,
        description=payload.description,
        owner_id=payload.owner_id,
        attributes=payload.attributes.model_dump(mode="json", exclude_none=False),
        custom_fields=dict(payload.custom_fields),
    )
    asset.tags = tags
    db.add(asset)
    db.flush()
    record_audit(
        db,
        action=AuditAction.create,
        entity_type=_AUDIT_ENTITY,
        entity_id=asset.id,
        actor_id=actor_id,
        after=snapshot(asset),
        source_ip=source_ip,
    )
    return asset


def update_asset(
    db: Session,
    asset: Asset,
    payload: AssetUpdate,
    *,
    actor_id: uuid.UUID | None = None,
    source_ip: str | None = None,
) -> Asset:
    """Apply a partial update and record an ``update`` audit entry (before/after)."""
    before = snapshot(asset)
    data = payload.model_dump(exclude_unset=True)

    if "tag_ids" in data:
        asset.tags = _load_tags(db, payload.tag_ids or [])
    if "attributes" in data and payload.attributes is not None:
        asset.attributes = payload.attributes.model_dump(mode="json", exclude_none=False)
    if "custom_fields" in data and payload.custom_fields is not None:
        asset.custom_fields = dict(payload.custom_fields)

    for field in (
        "name",
        "asset_type",
        "environment",
        "lifecycle_state",
        "location",
        "description",
        "owner_id",
    ):
        if field in data:
            setattr(asset, field, getattr(payload, field))

    db.flush()
    record_audit(
        db,
        action=AuditAction.update,
        entity_type=_AUDIT_ENTITY,
        entity_id=asset.id,
        actor_id=actor_id,
        before=before,
        after=snapshot(asset),
        source_ip=source_ip,
    )
    return asset


def change_state(
    db: Session,
    asset: Asset,
    new_state: LifecycleState,
    *,
    actor_id: uuid.UUID | None = None,
    source_ip: str | None = None,
) -> Asset:
    """Transition lifecycle state and record a ``state_change`` audit entry."""
    before = snapshot(asset)
    asset.lifecycle_state = new_state
    db.flush()
    record_audit(
        db,
        action=AuditAction.state_change,
        entity_type=_AUDIT_ENTITY,
        entity_id=asset.id,
        actor_id=actor_id,
        before=before,
        after=snapshot(asset),
        source_ip=source_ip,
    )
    return asset


def delete_asset(
    db: Session,
    asset: Asset,
    *,
    actor_id: uuid.UUID | None = None,
    source_ip: str | None = None,
) -> None:
    """Delete an asset and record a ``delete`` audit entry with the prior state."""
    before = snapshot(asset)
    asset_id = asset.id
    db.delete(asset)
    db.flush()
    record_audit(
        db,
        action=AuditAction.delete,
        entity_type=_AUDIT_ENTITY,
        entity_id=asset_id,
        actor_id=actor_id,
        before=before,
        source_ip=source_ip,
    )
