"""User schemas: creation, partial update, role change, and read projection."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Role

# Pragmatic email shape check at the boundary. We avoid pydantic's ``EmailStr``
# because it requires the ``email-validator`` package, which is not a listed
# dependency; this regex rejects the obviously malformed without that import.
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class UserCreate(BaseModel):
    """Payload to provision a new account (admin-only at the API layer)."""

    email: str = Field(min_length=3, max_length=255, pattern=_EMAIL_PATTERN)
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=256)
    role: Role = Role.viewer
    mfa_enabled: bool = False


class UserUpdate(BaseModel):
    """Partial update; only provided fields are applied."""

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None
    mfa_enabled: bool | None = None


class RoleUpdate(BaseModel):
    """Dedicated payload for changing a user's RBAC role."""

    role: Role


class UserRead(BaseModel):
    """Safe read projection of a user (never exposes the password hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    is_active: bool
    mfa_enabled: bool
    created_at: datetime
