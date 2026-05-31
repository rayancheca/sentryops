"""Request dependencies: DB session, authenticated user, and RBAC enforcement.

RBAC is enforced HERE, at the API boundary, not in the UI. Every mutating route
declares the minimum role it requires via ``require_role`` / the ``Require*``
aliases, so authorization holds regardless of which client calls the API.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError, PermissionDeniedError
from app.core.security import decode_token
from app.db.session import get_db
from app.models.enums import Role
from app.models.user import User

_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: DbSession,
) -> User:
    if credentials is None:
        raise AuthError("Missing bearer token.")
    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise AuthError("Invalid or expired token.") from exc
    if payload.get("type") != "access":
        raise AuthError("Wrong token type.")
    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except (KeyError, ValueError) as exc:
        raise AuthError("Malformed token subject.") from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthError("User not found or inactive.")
    request.state.user = user
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(required: Role) -> Callable[[User], User]:
    """Dependency factory enforcing a minimum role (admin > operator > viewer)."""

    def _dep(user: CurrentUser) -> User:
        if not Role(user.role).can_act_as(required):
            raise PermissionDeniedError(f"This action requires the '{required}' role.")
        return user

    return _dep


# Any authenticated user (viewer is the floor), operator+, and admin-only.
RequireViewer = Annotated[User, Depends(require_role(Role.viewer))]
RequireOperator = Annotated[User, Depends(require_role(Role.operator))]
RequireAdmin = Annotated[User, Depends(require_role(Role.admin))]
