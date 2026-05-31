"""Auth endpoints: login, refresh-token rotation, logout, and the /me lookup.

Login and refresh are rate-limited (``AUTH_LIMIT``) to blunt credential-stuffing
and token-replay attempts. slowapi requires the decorated path function to accept
a ``request: Request`` positional parameter, so both expose it explicitly.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api.deps import CurrentUser, DbSession
from app.core.rate_limit import AUTH_LIMIT, limiter
from app.schemas.auth import LoginRequest, LogoutRequest, RefreshRequest, TokenPair
from app.schemas.common import Envelope
from app.schemas.user import UserRead
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login", response_model=Envelope[TokenPair], summary="Exchange credentials for tokens"
)
@limiter.limit(AUTH_LIMIT)
def login(request: Request, payload: LoginRequest, db: DbSession) -> Envelope[TokenPair]:
    user = auth_service.authenticate(db, payload.email, payload.password)
    pair = auth_service.issue_token_pair(db, user)
    db.commit()
    return Envelope.ok(pair)


@router.post("/refresh", response_model=Envelope[TokenPair], summary="Rotate a refresh token")
@limiter.limit(AUTH_LIMIT)
def refresh(request: Request, payload: RefreshRequest, db: DbSession) -> Envelope[TokenPair]:
    pair = auth_service.rotate_refresh(db, payload.refresh_token)
    db.commit()
    return Envelope.ok(pair)


@router.post("/logout", response_model=Envelope[dict[str, Any]], summary="Revoke a refresh token")
def logout(payload: LogoutRequest, db: DbSession) -> Envelope[dict[str, Any]]:
    auth_service.revoke_refresh(db, payload.refresh_token)
    db.commit()
    return Envelope.ok({"revoked": True})


@router.get("/me", response_model=Envelope[UserRead], summary="Current authenticated user")
def me(user: CurrentUser) -> Envelope[UserRead]:
    return Envelope.ok(UserRead.model_validate(user))
