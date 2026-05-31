"""Behavioral tests for the user management service (app/services/user_service.py).

Covers create (incl. duplicate-email conflict), partial update, role change, and
deactivate — asserting the persisted state, the password is hashed (never stored
plaintext, never leaked into audit snapshots), and an audit row is written for
every mutation.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_password, verify_password
from app.models.audit import AuditLog
from app.models.enums import AuditAction, Role
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.services.user_service import (
    create_user,
    deactivate_user,
    get_user,
    set_role,
    update_user,
)

pytestmark = pytest.mark.integration


def _user_audit_rows(db: Session, user_id: uuid.UUID, action: AuditAction) -> list[AuditLog]:
    return list(
        db.execute(
            select(AuditLog)
            .where(AuditLog.entity_type == "user")
            .where(AuditLog.entity_id == user_id)
            .where(AuditLog.action == action)
        ).scalars()
    )


def test_create_user_hashes_password_and_audits(db: Session) -> None:
    # Arrange
    payload = UserCreate(
        email="new.user@test.local",
        full_name="New User",
        password="super-secret-pass",
        role=Role.operator,
        mfa_enabled=True,
    )

    # Act
    user = create_user(db, payload)
    db.flush()

    # Assert — persisted with a verifiable hash (not the plaintext).
    assert user.id is not None
    assert user.email == "new.user@test.local"
    assert user.role is Role.operator
    assert user.is_active is True
    assert user.mfa_enabled is True
    assert user.hashed_password != "super-secret-pass"
    assert verify_password("super-secret-pass", user.hashed_password)

    # ...and a create audit row that never leaks the password hash.
    rows = _user_audit_rows(db, user.id, AuditAction.create)
    assert len(rows) == 1
    assert rows[0].before is None
    assert rows[0].after is not None
    assert "hashed_password" not in rows[0].after


def test_create_user_duplicate_email_raises_conflict(db: Session) -> None:
    # Arrange — an existing account.
    db.add(
        User(
            email="dupe@test.local",
            full_name="First",
            hashed_password=hash_password("first-pass-123"),
            role=Role.viewer,
            is_active=True,
        )
    )
    db.flush()

    # Act / Assert — a second create with the same email conflicts.
    with pytest.raises(ConflictError) as excinfo:
        create_user(
            db,
            UserCreate(
                email="dupe@test.local",
                full_name="Second",
                password="second-pass-123",
            ),
        )
    assert "already exists" in str(excinfo.value)


def test_update_user_applies_only_provided_fields_and_audits(db: Session) -> None:
    # Arrange
    user = create_user(
        db,
        UserCreate(email="upd@test.local", full_name="Old Name", password="pass-12345"),
    )
    db.flush()

    # Act — change name + mfa, leave is_active untouched.
    update_user(db, user, UserUpdate(full_name="New Name", mfa_enabled=True))
    db.flush()

    # Assert
    db.refresh(user)
    assert user.full_name == "New Name"
    assert user.mfa_enabled is True
    assert user.is_active is True  # unchanged

    rows = _user_audit_rows(db, user.id, AuditAction.update)
    assert len(rows) == 1
    assert rows[0].before["full_name"] == "Old Name"
    assert rows[0].after["full_name"] == "New Name"


def test_update_user_ignores_unset_fields(db: Session) -> None:
    # Arrange
    user = create_user(
        db,
        UserCreate(email="noop@test.local", full_name="Keep", password="pass-12345"),
    )
    db.flush()

    # Act — an empty update should not change anything.
    update_user(db, user, UserUpdate())
    db.flush()

    # Assert — fields preserved; an audit row is still written for the attempt.
    db.refresh(user)
    assert user.full_name == "Keep"
    assert len(_user_audit_rows(db, user.id, AuditAction.update)) == 1


def test_set_role_changes_role_and_records_state_change(db: Session) -> None:
    # Arrange — a viewer is promoted to admin.
    user = create_user(
        db,
        UserCreate(email="promote@test.local", full_name="Promote", password="pass-12345"),
    )
    db.flush()
    assert user.role is Role.viewer

    # Act
    set_role(db, user, Role.admin)
    db.flush()

    # Assert
    db.refresh(user)
    assert user.role is Role.admin
    rows = _user_audit_rows(db, user.id, AuditAction.state_change)
    assert len(rows) == 1
    assert rows[0].before["role"] == "viewer"
    assert rows[0].after["role"] == "admin"


def test_deactivate_user_soft_disables_and_records_state_change(db: Session) -> None:
    # Arrange — an active account.
    user = create_user(
        db,
        UserCreate(
            email="deact@test.local",
            full_name="Deactivate",
            password="pass-12345",
            role=Role.operator,
        ),
    )
    db.flush()
    assert user.is_active is True

    # Act
    deactivate_user(db, user)
    db.flush()

    # Assert — soft disable (row still exists, just inactive).
    db.refresh(user)
    assert user.is_active is False
    assert db.get(User, user.id) is not None
    rows = _user_audit_rows(db, user.id, AuditAction.state_change)
    assert len(rows) == 1
    assert rows[0].before["is_active"] is True
    assert rows[0].after["is_active"] is False


def test_get_user_returns_existing_and_raises_for_missing(db: Session) -> None:
    # Arrange
    user = create_user(
        db,
        UserCreate(email="fetch@test.local", full_name="Fetch", password="pass-12345"),
    )
    db.flush()

    # Act / Assert — found by id...
    fetched = get_user(db, user.id)
    assert fetched.id == user.id

    # ...and a missing id raises NotFoundError.
    with pytest.raises(NotFoundError):
        get_user(db, uuid.uuid4())
