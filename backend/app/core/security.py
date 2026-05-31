"""Password hashing (argon2) and JWT access/refresh token handling."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings

_ph = PasswordHasher()
_settings = get_settings()

TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Constant-time-ish verify; returns False on mismatch or malformed hash."""
    try:
        return _ph.verify(hashed, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    return _ph.check_needs_rehash(hashed)


def _create_token(
    subject: str | uuid.UUID,
    role: str,
    token_type: TokenType,
    expires_delta: timedelta,
    jti: str | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": jti or uuid.uuid4().hex,
    }
    return jwt.encode(payload, _settings.secret_key, algorithm=_settings.jwt_algorithm)


def create_access_token(subject: str | uuid.UUID, role: str) -> str:
    return _create_token(
        subject, role, "access", timedelta(minutes=_settings.access_token_expire_minutes)
    )


def create_refresh_token(subject: str | uuid.UUID, role: str, jti: str) -> str:
    """Refresh token; ``jti`` is persisted (hashed) so the token can be revoked."""
    return _create_token(
        subject, role, "refresh", timedelta(days=_settings.refresh_token_expire_days), jti=jti
    )


def decode_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT. Raises ``jwt.PyJWTError`` on any problem."""
    return jwt.decode(token, _settings.secret_key, algorithms=[_settings.jwt_algorithm])
