"""Tag endpoints: list, create, delete, and attach/detach to assets.

Reads are open to any authenticated user; mutations require operator.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession, RequireOperator
from app.core.exceptions import ConflictError, NotFoundError
from app.models.asset import Tag
from app.models.enums import AuditAction
from app.schemas.common import Envelope, Page
from app.schemas.tag import TagCreate, TagRead
from app.services.asset_service import get_asset
from app.services.audit_service import record_audit, snapshot

router = APIRouter(prefix="/tags", tags=["tags"])

_AUDIT_ENTITY = "tag"


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _get_tag(db: DbSession, tag_id: uuid.UUID) -> Tag:
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise NotFoundError("Tag not found.", details={"tag_id": str(tag_id)})
    return tag


@router.get("", response_model=Envelope[Page[TagRead]], summary="List tags")
def list_tags(db: DbSession, _user: CurrentUser) -> Envelope[Page[TagRead]]:
    tags = list(db.execute(select(Tag).order_by(Tag.name)).scalars())
    page: Page[TagRead] = Page(
        items=[TagRead.model_validate(t) for t in tags],
        total=len(tags),
        limit=len(tags),
        offset=0,
    )
    return Envelope.ok(page)


@router.post("", response_model=Envelope[TagRead], status_code=201, summary="Create a tag")
def create_tag(
    payload: TagCreate, db: DbSession, user: RequireOperator, request: Request
) -> Envelope[TagRead]:
    existing = db.execute(select(Tag.id).where(Tag.name == payload.name)).first()
    if existing is not None:
        raise ConflictError("A tag with that name already exists.")

    tag = Tag(name=payload.name, color=payload.color)
    db.add(tag)
    db.flush()
    record_audit(
        db,
        action=AuditAction.create,
        entity_type=_AUDIT_ENTITY,
        entity_id=tag.id,
        actor_id=user.id,
        after=snapshot(tag),
        source_ip=_client_ip(request),
    )
    db.commit()
    db.refresh(tag)
    return Envelope.ok(TagRead.model_validate(tag))


@router.delete("/{tag_id}", response_model=Envelope[dict[str, str]], summary="Delete a tag")
def delete_tag(
    tag_id: uuid.UUID, db: DbSession, user: RequireOperator, request: Request
) -> Envelope[dict[str, str]]:
    tag = _get_tag(db, tag_id)
    before = snapshot(tag)
    db.delete(tag)
    db.flush()
    record_audit(
        db,
        action=AuditAction.delete,
        entity_type=_AUDIT_ENTITY,
        entity_id=tag_id,
        actor_id=user.id,
        before=before,
        source_ip=_client_ip(request),
    )
    db.commit()
    return Envelope.ok({"status": "deleted", "tag_id": str(tag_id)})


@router.post(
    "/{tag_id}/assets/{asset_id}",
    response_model=Envelope[dict[str, str]],
    summary="Attach a tag to an asset",
)
def attach_tag(
    tag_id: uuid.UUID,
    asset_id: uuid.UUID,
    db: DbSession,
    user: RequireOperator,
    request: Request,
) -> Envelope[dict[str, str]]:
    tag = _get_tag(db, tag_id)
    asset = get_asset(db, asset_id)
    if tag in asset.tags:
        raise ConflictError("Tag is already attached to this asset.")

    before = {"tag_ids": [str(t.id) for t in asset.tags]}
    asset.tags.append(tag)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("Tag is already attached to this asset.") from exc
    record_audit(
        db,
        action=AuditAction.update,
        entity_type="asset",
        entity_id=asset.id,
        actor_id=user.id,
        before=before,
        after={"tag_ids": [str(t.id) for t in asset.tags]},
        source_ip=_client_ip(request),
    )
    db.commit()
    return Envelope.ok({"status": "attached", "asset_id": str(asset_id), "tag_id": str(tag_id)})


@router.delete(
    "/{tag_id}/assets/{asset_id}",
    response_model=Envelope[dict[str, str]],
    summary="Detach a tag from an asset",
)
def detach_tag(
    tag_id: uuid.UUID,
    asset_id: uuid.UUID,
    db: DbSession,
    user: RequireOperator,
    request: Request,
) -> Envelope[dict[str, str]]:
    tag = _get_tag(db, tag_id)
    asset = get_asset(db, asset_id)
    if tag not in asset.tags:
        raise NotFoundError("Tag is not attached to this asset.")

    before = {"tag_ids": [str(t.id) for t in asset.tags]}
    asset.tags.remove(tag)
    db.flush()
    record_audit(
        db,
        action=AuditAction.update,
        entity_type="asset",
        entity_id=asset.id,
        actor_id=user.id,
        before=before,
        after={"tag_ids": [str(t.id) for t in asset.tags]},
        source_ip=_client_ip(request),
    )
    db.commit()
    return Envelope.ok({"status": "detached", "asset_id": str(asset_id), "tag_id": str(tag_id)})
