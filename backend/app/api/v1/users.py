"""User administration endpoints. Every route is admin-only via ``RequireAdmin``.

Authorization is enforced here at the API boundary, not in the UI. Mutations
commit after a successful service call; the service layer records the audit
entry (with the actor and source IP) before the route commits.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.deps import DbSession, RequireAdmin
from app.schemas.common import Envelope, Page, PaginationParams
from app.schemas.user import RoleUpdate, UserCreate, UserRead, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client is not None else None


@router.get("", response_model=Envelope[Page[UserRead]], summary="List users")
def list_users(
    _admin: RequireAdmin,
    db: DbSession,
    page: Annotated[PaginationParams, Depends()],
) -> Envelope[Page[UserRead]]:
    rows, total = user_service.list_users(db, limit=page.limit, offset=page.offset)
    items = [UserRead.model_validate(u) for u in rows]
    return Envelope.ok(Page(items=items, total=total, limit=page.limit, offset=page.offset))


@router.post("", response_model=Envelope[UserRead], status_code=201, summary="Create a user")
def create_user(
    request: Request,
    admin: RequireAdmin,
    db: DbSession,
    payload: UserCreate,
) -> Envelope[UserRead]:
    user = user_service.create_user(db, payload, actor_id=admin.id, source_ip=_client_ip(request))
    db.commit()
    return Envelope.ok(UserRead.model_validate(user))


@router.get("/{user_id}", response_model=Envelope[UserRead], summary="Get a user")
def get_user(
    _admin: RequireAdmin,
    db: DbSession,
    user_id: uuid.UUID,
) -> Envelope[UserRead]:
    user = user_service.get_user(db, user_id)
    return Envelope.ok(UserRead.model_validate(user))


@router.patch("/{user_id}", response_model=Envelope[UserRead], summary="Update a user")
def update_user(
    request: Request,
    admin: RequireAdmin,
    db: DbSession,
    user_id: uuid.UUID,
    payload: UserUpdate,
) -> Envelope[UserRead]:
    user = user_service.get_user(db, user_id)
    user = user_service.update_user(
        db, user, payload, actor_id=admin.id, source_ip=_client_ip(request)
    )
    db.commit()
    return Envelope.ok(UserRead.model_validate(user))


@router.patch("/{user_id}/role", response_model=Envelope[UserRead], summary="Change a user's role")
def set_role(
    request: Request,
    admin: RequireAdmin,
    db: DbSession,
    user_id: uuid.UUID,
    payload: RoleUpdate,
) -> Envelope[UserRead]:
    user = user_service.get_user(db, user_id)
    user = user_service.set_role(
        db, user, payload.role, actor_id=admin.id, source_ip=_client_ip(request)
    )
    db.commit()
    return Envelope.ok(UserRead.model_validate(user))


@router.post(
    "/{user_id}/deactivate", response_model=Envelope[UserRead], summary="Deactivate a user"
)
def deactivate_user(
    request: Request,
    admin: RequireAdmin,
    db: DbSession,
    user_id: uuid.UUID,
) -> Envelope[UserRead]:
    user = user_service.get_user(db, user_id)
    user = user_service.deactivate_user(db, user, actor_id=admin.id, source_ip=_client_ip(request))
    db.commit()
    return Envelope.ok(UserRead.model_validate(user))
