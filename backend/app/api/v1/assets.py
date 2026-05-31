"""Asset (CMDB) endpoints: CRUD, lifecycle, CSV import/export, and QR labels.

Reads require any authenticated user; mutations require operator, and delete
requires admin. Authorization is enforced here via the ``Require*`` deps.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, UploadFile
from fastapi.responses import PlainTextResponse

from app.api.deps import CurrentUser, DbSession, RequireAdmin, RequireOperator
from app.core.exceptions import ValidationAppError
from app.models.enums import AssetType, Environment, LifecycleState
from app.schemas.asset import (
    AssetCreate,
    AssetListItem,
    AssetRead,
    AssetStateChange,
    AssetUpdate,
)
from app.schemas.common import Envelope, Page, PaginationParams
from app.services import asset_service, csv_service, qr_service

router = APIRouter(prefix="/assets", tags=["assets"])

# A defensive cap on uploaded CSV size (1 MiB) to avoid unbounded memory use.
_MAX_CSV_BYTES = 1_048_576


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("", response_model=Envelope[Page[AssetListItem]], summary="List assets")
def list_assets(
    db: DbSession,
    _user: CurrentUser,
    pagination: Annotated[PaginationParams, Depends()],
    asset_type: Annotated[AssetType | None, Query()] = None,
    environment: Annotated[Environment | None, Query()] = None,
    lifecycle_state: Annotated[LifecycleState | None, Query()] = None,
    owner_id: Annotated[uuid.UUID | None, Query()] = None,
    tag_id: Annotated[uuid.UUID | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=255)] = None,
) -> Envelope[Page[AssetListItem]]:
    items, total = asset_service.list_assets(
        db,
        limit=pagination.limit,
        offset=pagination.offset,
        asset_type=asset_type,
        environment=environment,
        lifecycle_state=lifecycle_state,
        owner_id=owner_id,
        tag_id=tag_id,
        q=q,
    )
    page: Page[AssetListItem] = Page(
        items=[AssetListItem.model_validate(a) for a in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Envelope.ok(page)


@router.post(
    "",
    response_model=Envelope[AssetRead],
    status_code=201,
    summary="Create an asset",
)
def create_asset(
    payload: AssetCreate,
    db: DbSession,
    user: RequireOperator,
    request: Request,
) -> Envelope[AssetRead]:
    asset = asset_service.create_asset(db, payload, actor_id=user.id, source_ip=_client_ip(request))
    db.commit()
    db.refresh(asset)
    return Envelope.ok(AssetRead.model_validate(asset))


@router.get("/export", summary="Export all assets as CSV")
def export_assets(db: DbSession, _user: CurrentUser) -> PlainTextResponse:
    body = csv_service.export_assets_csv(db)
    return PlainTextResponse(
        content=body,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="assets.csv"'},
    )


@router.post(
    "/import",
    response_model=Envelope[dict[str, object]],
    summary="Bulk-create assets from CSV",
)
async def import_assets(
    db: DbSession,
    user: RequireOperator,
    request: Request,
    file: UploadFile | None = None,
) -> Envelope[dict[str, object]]:
    if file is not None:
        raw = await file.read(_MAX_CSV_BYTES + 1)
    else:
        raw = await request.body()
    if len(raw) > _MAX_CSV_BYTES:
        raise ValidationAppError("CSV upload exceeds the 1 MiB limit.")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationAppError("CSV must be UTF-8 encoded.") from exc

    result = csv_service.import_assets_csv(
        db, text, actor_id=user.id, source_ip=_client_ip(request)
    )
    db.commit()
    return Envelope.ok(result)


@router.get("/{asset_id}", response_model=Envelope[AssetRead], summary="Get an asset")
def get_asset(asset_id: uuid.UUID, db: DbSession, _user: CurrentUser) -> Envelope[AssetRead]:
    asset = asset_service.get_asset(db, asset_id)
    return Envelope.ok(AssetRead.model_validate(asset))


@router.patch("/{asset_id}", response_model=Envelope[AssetRead], summary="Update an asset")
def update_asset(
    asset_id: uuid.UUID,
    payload: AssetUpdate,
    db: DbSession,
    user: RequireOperator,
    request: Request,
) -> Envelope[AssetRead]:
    asset = asset_service.get_asset(db, asset_id)
    asset = asset_service.update_asset(
        db, asset, payload, actor_id=user.id, source_ip=_client_ip(request)
    )
    db.commit()
    db.refresh(asset)
    return Envelope.ok(AssetRead.model_validate(asset))


@router.post(
    "/{asset_id}/state",
    response_model=Envelope[AssetRead],
    summary="Change lifecycle state",
)
def change_state(
    asset_id: uuid.UUID,
    payload: AssetStateChange,
    db: DbSession,
    user: RequireOperator,
    request: Request,
) -> Envelope[AssetRead]:
    asset = asset_service.get_asset(db, asset_id)
    asset = asset_service.change_state(
        db, asset, payload.lifecycle_state, actor_id=user.id, source_ip=_client_ip(request)
    )
    db.commit()
    db.refresh(asset)
    return Envelope.ok(AssetRead.model_validate(asset))


@router.delete("/{asset_id}", response_model=Envelope[dict[str, str]], summary="Delete an asset")
def delete_asset(
    asset_id: uuid.UUID,
    db: DbSession,
    user: RequireAdmin,
    request: Request,
) -> Envelope[dict[str, str]]:
    asset = asset_service.get_asset(db, asset_id)
    asset_service.delete_asset(db, asset, actor_id=user.id, source_ip=_client_ip(request))
    db.commit()
    return Envelope.ok({"status": "deleted", "asset_id": str(asset_id)})


@router.get("/{asset_id}/qr.png", summary="QR-code PNG label")
def asset_qr_png(asset_id: uuid.UUID, db: DbSession, _user: CurrentUser) -> Response:
    asset = asset_service.get_asset(db, asset_id)
    png = qr_service.qr_png(asset.short_code)
    return Response(content=png, media_type="image/png")


@router.get("/{asset_id}/qr.svg", summary="QR-code SVG label")
def asset_qr_svg(asset_id: uuid.UUID, db: DbSession, _user: CurrentUser) -> Response:
    asset = asset_service.get_asset(db, asset_id)
    svg = qr_service.qr_svg(asset.short_code)
    return Response(content=svg, media_type="image/svg+xml")
