"""Authentication service: credential checks and refresh-token rotation.

Refresh tokens are single-use. Each issued refresh token carries a unique ``jti``
that is persisted in :class:`RefreshToken`. Rotation revokes the presented token's
``jti`` and mints a brand-new pair, so a leaked refresh token is usable at most
once before it is invalidated.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AuthError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.user import RefreshToken, User
from app.schemas.auth import TokenPair


def authenticate(db: Session, email: str, password: str) -> User:
    """Return the user for valid, active credentials; raise ``AuthError`` otherwise.

    The same opaque error is raised for unknown email, wrong password, and
    inactive accounts so callers cannot enumerate valid addresses.
    """
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(password, user.hashed_password):
        raise AuthError("Invalid email or password.")
    if not user.is_active:
        raise AuthError("Invalid email or password.")
    return user


def issue_token_pair(db: Session, user: User) -> TokenPair:
    """Mint an access token plus a fresh, persisted refresh token.

    The caller owns the surrounding transaction (commits after this returns).
    """
    settings = get_settings()
    role = str(user.role)

    access = create_access_token(user.id, role)

    jti = uuid.uuid4().hex
    refresh = create_refresh_token(user.id, role, jti)
    expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)

    db.add(RefreshToken(user_id=user.id, jti=jti, expires_at=expires_at, revoked=False))
    db.flush()

    return TokenPair(access_token=access, refresh_token=refresh)


def _decode_refresh(refresh_token: str) -> dict[str, Any]:
    """Decode a refresh JWT, enforcing signature, expiry, and token type."""
    try:
        payload = decode_token(refresh_token)
    except jwt.PyJWTError as exc:
        raise AuthError("Invalid or expired refresh token.") from exc
    if payload.get("type") != "refresh":
        raise AuthError("Wrong token type.")
    return payload


def _aware(value: datetime) -> datetime:
    """Treat naive timestamps (e.g. from some drivers) as UTC for comparison."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def rotate_refresh(db: Session, refresh_token: str) -> TokenPair:
    """Exchange a valid refresh token for a new pair, revoking the presented one.

    Rejects tokens whose ``jti`` is missing, already revoked, or past expiry. On
    success the old ``jti`` is revoked (single-use) and a new pair is issued.
    """
    payload = _decode_refresh(refresh_token)

    jti = payload.get("jti")
    if not isinstance(jti, str) or not jti:
        raise AuthError("Malformed refresh token.")

    record = db.scalar(select(RefreshToken).where(RefreshToken.jti == jti))
    if record is None or record.revoked:
        raise AuthError("Refresh token is not valid.")
    if _aware(record.expires_at) <= datetime.now(UTC):
        raise AuthError("Refresh token has expired.")

    user = db.get(User, record.user_id)
    if user is None or not user.is_active:
        raise AuthError("User not found or inactive.")

    # Single-use: revoke the presented token before minting its replacement.
    record.revoked = True
    db.flush()

    return issue_token_pair(db, user)


def revoke_refresh(db: Session, refresh_token: str) -> None:
    """Mark the token's ``jti`` revoked. Idempotent and never raises on bad input."""
    try:
        payload = decode_token(refresh_token)
    except jwt.PyJWTError:
        return
    if payload.get("type") != "refresh":
        return

    jti = payload.get("jti")
    if not isinstance(jti, str) or not jti:
        return

    record = db.scalar(select(RefreshToken).where(RefreshToken.jti == jti))
    if record is None or record.revoked:
        return

    record.revoked = True
    db.flush()
