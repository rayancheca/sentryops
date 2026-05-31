"""User management service (admin-only at the API layer).

Every create/update/role-change/deactivate is recorded through ``record_audit``
with ``entity_type='user'`` so the audit log captures before/after snapshots.
Services own ``flush``; routes own ``commit``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_password
from app.models.enums import AuditAction, Role
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.services.audit_service import record_audit, snapshot

_ENTITY = "user"
# The password hash must never leak into audit snapshots.
_SNAPSHOT_EXCLUDE = {"hashed_password"}


def list_users(db: Session, *, limit: int, offset: int) -> tuple[list[User], int]:
    """Return a page of users plus the total count (ordered by creation time)."""
    total = db.scalar(select(func.count()).select_from(User)) or 0
    rows = list(
        db.scalars(select(User).order_by(User.created_at.asc()).limit(limit).offset(offset))
    )
    return rows, total


def get_user(db: Session, user_id: uuid.UUID) -> User:
    """Fetch one user or raise ``NotFoundError``."""
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    return user


def create_user(
    db: Session,
    payload: UserCreate,
    *,
    actor_id: uuid.UUID | None = None,
    source_ip: str | None = None,
) -> User:
    """Create a user with a hashed password; unique email enforced at the boundary."""
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise ConflictError("A user with that email already exists.")

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        is_active=True,
        mfa_enabled=payload.mfa_enabled,
    )
    db.add(user)
    db.flush()

    record_audit(
        db,
        action=AuditAction.create,
        entity_type=_ENTITY,
        entity_id=user.id,
        actor_id=actor_id,
        before=None,
        after=snapshot(user, exclude=_SNAPSHOT_EXCLUDE),
        source_ip=source_ip,
    )
    return user


def update_user(
    db: Session,
    user: User,
    payload: UserUpdate,
    *,
    actor_id: uuid.UUID | None = None,
    source_ip: str | None = None,
) -> User:
    """Apply a partial update (only provided fields) and audit the change."""
    before = snapshot(user, exclude=_SNAPSHOT_EXCLUDE)

    changes = payload.model_dump(exclude_unset=True)
    if "full_name" in changes and changes["full_name"] is not None:
        user.full_name = changes["full_name"]
    if "is_active" in changes and changes["is_active"] is not None:
        user.is_active = changes["is_active"]
    if "mfa_enabled" in changes and changes["mfa_enabled"] is not None:
        user.mfa_enabled = changes["mfa_enabled"]
    db.flush()

    record_audit(
        db,
        action=AuditAction.update,
        entity_type=_ENTITY,
        entity_id=user.id,
        actor_id=actor_id,
        before=before,
        after=snapshot(user, exclude=_SNAPSHOT_EXCLUDE),
        source_ip=source_ip,
    )
    return user


def set_role(
    db: Session,
    user: User,
    role: Role,
    *,
    actor_id: uuid.UUID | None = None,
    source_ip: str | None = None,
) -> User:
    """Change a user's RBAC role; recorded as a state change in the audit log."""
    before = snapshot(user, exclude=_SNAPSHOT_EXCLUDE)
    user.role = role
    db.flush()

    record_audit(
        db,
        action=AuditAction.state_change,
        entity_type=_ENTITY,
        entity_id=user.id,
        actor_id=actor_id,
        before=before,
        after=snapshot(user, exclude=_SNAPSHOT_EXCLUDE),
        source_ip=source_ip,
    )
    return user


def deactivate_user(
    db: Session,
    user: User,
    *,
    actor_id: uuid.UUID | None = None,
    source_ip: str | None = None,
) -> User:
    """Soft-disable an account (no hard delete); recorded as a state change."""
    before = snapshot(user, exclude=_SNAPSHOT_EXCLUDE)
    user.is_active = False
    db.flush()

    record_audit(
        db,
        action=AuditAction.state_change,
        entity_type=_ENTITY,
        entity_id=user.id,
        actor_id=actor_id,
        before=before,
        after=snapshot(user, exclude=_SNAPSHOT_EXCLUDE),
        source_ip=source_ip,
    )
    return user
