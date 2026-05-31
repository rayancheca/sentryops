"""Asset check-in/out endpoints.

Mutations (check-out / check-in) require operator; the holder and history reads
are open to any authenticated user.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from app.api.deps import CurrentUser, DbSession, RequireOperator
from app.core.exceptions import NotFoundError
from app.schemas.checkout import CheckoutCreate, CheckoutRead
from app.schemas.common import Envelope, Page
from app.services import checkout_service
from app.services.asset_service import get_asset

router = APIRouter(prefix="/checkouts", tags=["checkouts"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post(
    "/{asset_id}/check-out",
    response_model=Envelope[CheckoutRead],
    status_code=201,
    summary="Check an asset out to a holder",
)
def check_out(
    asset_id: uuid.UUID,
    payload: CheckoutCreate,
    db: DbSession,
    user: RequireOperator,
    request: Request,
) -> Envelope[CheckoutRead]:
    asset = get_asset(db, asset_id)
    record = checkout_service.check_out(
        db,
        asset,
        payload.holder_id,
        user,
        notes=payload.notes,
        source_ip=_client_ip(request),
    )
    db.commit()
    db.refresh(record)
    return Envelope.ok(CheckoutRead.model_validate(record))


@router.post(
    "/{asset_id}/check-in",
    response_model=Envelope[CheckoutRead],
    summary="Check an asset back in",
)
def check_in(
    asset_id: uuid.UUID,
    db: DbSession,
    user: RequireOperator,
    request: Request,
) -> Envelope[CheckoutRead]:
    asset = get_asset(db, asset_id)
    record = checkout_service.check_in(db, asset, user, source_ip=_client_ip(request))
    db.commit()
    db.refresh(record)
    return Envelope.ok(CheckoutRead.model_validate(record))


@router.get(
    "/{asset_id}/holder",
    response_model=Envelope[CheckoutRead],
    summary="Current holder of an asset",
)
def holder(asset_id: uuid.UUID, db: DbSession, _user: CurrentUser) -> Envelope[CheckoutRead]:
    record = checkout_service.current_holder(db, asset_id)
    if record is None:
        raise NotFoundError(
            "Asset is not currently checked out.", details={"asset_id": str(asset_id)}
        )
    return Envelope.ok(CheckoutRead.model_validate(record))


@router.get(
    "/{asset_id}/history",
    response_model=Envelope[Page[CheckoutRead]],
    summary="Check-out history for an asset",
)
def history(asset_id: uuid.UUID, db: DbSession, _user: CurrentUser) -> Envelope[Page[CheckoutRead]]:
    records = checkout_service.history(db, asset_id)
    page: Page[CheckoutRead] = Page(
        items=[CheckoutRead.model_validate(r) for r in records],
        total=len(records),
        limit=len(records),
        offset=0,
    )
    return Envelope.ok(page)
