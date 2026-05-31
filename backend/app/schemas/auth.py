"""Auth request/response schemas: login, token pair, refresh, and logout."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Pragmatic email shape check at the boundary. We avoid pydantic's ``EmailStr``
# because it requires the ``email-validator`` package, which is not a listed
# dependency; this regex rejects the obviously malformed without that import.
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class LoginRequest(BaseModel):
    """Credentials presented at ``POST /auth/login``."""

    email: str = Field(min_length=3, max_length=255, pattern=_EMAIL_PATTERN)
    password: str = Field(min_length=1, max_length=256)


class TokenPair(BaseModel):
    """Access + refresh token bundle returned on login and refresh."""

    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"


class RefreshRequest(BaseModel):
    """Body of ``POST /auth/refresh``; carries the refresh token to rotate."""

    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    """Body of ``POST /auth/logout``; carries the refresh token to revoke."""

    refresh_token: str = Field(min_length=1)
