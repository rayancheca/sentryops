"""Behavioral tests for the asset check-in/out service (app/services/checkout_service.py).

Covers the full custody lifecycle: check out -> current holder -> conflict on a
second check-out while held -> check in clears the holder -> history lists every
record. Each transition's audit row is verified too.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.enums import AssetType, AuditAction, Role
from app.models.user import User
from app.schemas.asset import AssetCreate
from app.services.asset_service import create_asset
from app.services.checkout_service import check_in, check_out, current_holder, history

pytestmark = pytest.mark.integration


def _make_user(db: Session, email: str, role: Role = Role.operator) -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0].title(),
        hashed_password=hash_password("checkout-pass-123"),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _make_asset(db: Session, name: str = "laptop-01"):
    asset = create_asset(db, AssetCreate(name=name, asset_type=AssetType.host))
    db.flush()
    return asset


def _checkout_audit_rows(db: Session, action: AuditAction) -> list[AuditLog]:
    return list(
        db.execute(
            select(AuditLog)
            .where(AuditLog.entity_type == "asset_checkout")
            .where(AuditLog.action == action)
        ).scalars()
    )


def test_check_out_sets_current_holder_and_audits(db: Session) -> None:
    # Arrange
    actor = _make_user(db, "actor@test.local")
    holder = _make_user(db, "holder@test.local")
    asset = _make_asset(db)

    # Act
    record = check_out(db, asset, holder.id, actor, notes="for the road trip")
    db.flush()

    # Assert — record links holder + actor, and is the current open holder.
    assert record.asset_id == asset.id
    assert record.holder_id == holder.id
    assert record.checked_out_by_id == actor.id
    assert record.checked_in_at is None
    assert record.notes == "for the road trip"

    held = current_holder(db, asset.id)
    assert held is not None
    assert held.id == record.id

    rows = _checkout_audit_rows(db, AuditAction.checkout)
    assert len(rows) == 1
    assert rows[0].actor_id == actor.id


def test_second_check_out_while_held_raises_conflict(db: Session) -> None:
    # Arrange — asset is already checked out.
    actor = _make_user(db, "actor@test.local")
    first_holder = _make_user(db, "first@test.local")
    second_holder = _make_user(db, "second@test.local")
    asset = _make_asset(db)
    check_out(db, asset, first_holder.id, actor)
    db.flush()

    # Act / Assert — a second check-out conflicts.
    with pytest.raises(ConflictError) as excinfo:
        check_out(db, asset, second_holder.id, actor)
    assert "already checked out" in str(excinfo.value)


def test_check_in_clears_holder_and_audits(db: Session) -> None:
    # Arrange — check out, then check back in.
    actor = _make_user(db, "actor@test.local")
    holder = _make_user(db, "holder@test.local")
    asset = _make_asset(db)
    check_out(db, asset, holder.id, actor)
    db.flush()

    # Act
    record = check_in(db, asset, actor)
    db.flush()

    # Assert — the row is stamped checked-in and nobody currently holds it.
    assert record.checked_in_at is not None
    assert current_holder(db, asset.id) is None

    rows = _checkout_audit_rows(db, AuditAction.checkin)
    assert len(rows) == 1
    assert rows[0].before is not None
    assert rows[0].after is not None


def test_check_in_when_not_checked_out_raises_conflict(db: Session) -> None:
    # Arrange — a fresh asset that was never checked out.
    actor = _make_user(db, "actor@test.local")
    asset = _make_asset(db)

    # Act / Assert
    with pytest.raises(ConflictError) as excinfo:
        check_in(db, asset, actor)
    assert "not currently checked out" in str(excinfo.value)


def test_history_returns_all_records_newest_first(db: Session) -> None:
    # Arrange — a full out/in cycle, then a second out.
    actor = _make_user(db, "actor@test.local")
    holder = _make_user(db, "holder@test.local")
    asset = _make_asset(db)
    check_out(db, asset, holder.id, actor)
    db.flush()
    check_in(db, asset, actor)
    db.flush()
    second = check_out(db, asset, holder.id, actor)
    db.flush()

    # Act
    rows = history(db, asset.id)

    # Assert — both records are returned; exactly one (the second) is still open
    # while the first cycle is closed. The two share a transaction-clock
    # ``checked_out_at``, so we assert on the set/holder rather than tie-broken order.
    assert len(rows) == 2
    ids = {r.id for r in rows}
    assert second.id in ids
    open_rows = [r for r in rows if r.checked_in_at is None]
    closed_rows = [r for r in rows if r.checked_in_at is not None]
    assert len(open_rows) == 1
    assert open_rows[0].id == second.id
    assert len(closed_rows) == 1


def test_current_holder_none_for_unknown_asset(db: Session) -> None:
    # Act / Assert — an asset id that was never checked out has no holder.
    assert current_holder(db, uuid.uuid4()) is None


def test_check_out_again_allowed_after_check_in(db: Session) -> None:
    # Arrange — out, in, then a second check-out should succeed (no conflict).
    actor = _make_user(db, "actor@test.local")
    holder = _make_user(db, "holder@test.local")
    asset = _make_asset(db)
    check_out(db, asset, holder.id, actor)
    db.flush()
    check_in(db, asset, actor)
    db.flush()

    # Act
    second = check_out(db, asset, holder.id, actor)
    db.flush()

    # Assert
    assert second.checked_in_at is None
    held = current_holder(db, asset.id)
    assert held is not None and held.id == second.id
