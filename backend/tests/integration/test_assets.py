"""Integration tests for the asset (CMDB) endpoints.

Covers the full CRUD + lifecycle surface through the HTTP boundary, and asserts
that every mutating operation writes the expected immutable :class:`AuditLog`
row (queried back through the ``db`` fixture). Also checks filtered listing and
CSV export.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.rate_limit import limiter
from app.models.audit import AuditLog
from app.models.enums import AuditAction

ASSETS = "/api/v1/assets"


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> Iterator[None]:
    """Clear the shared (Redis-backed) auth rate-limit window between tests.

    Each test authenticates via several ``*_headers`` fixtures (one login each),
    and slowapi keys by client IP — ``TestClient`` presents a single fixed IP, so
    without a reset the ``10/minute`` auth limit is exhausted across the module.
    """
    limiter.reset()
    yield
    limiter.reset()


def _create_asset(
    client: TestClient,
    headers: dict[str, str],
    *,
    name: str = "web-01",
    asset_type: str = "host",
    environment: str = "prod",
) -> dict:
    resp = client.post(
        ASSETS,
        json={"name": name, "asset_type": asset_type, "environment": environment},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _audit_rows(db, entity_id: uuid.UUID, action: AuditAction) -> list[AuditLog]:
    return list(
        db.execute(
            select(AuditLog)
            .where(AuditLog.entity_type == "asset")
            .where(AuditLog.entity_id == entity_id)
            .where(AuditLog.action == action)
        ).scalars()
    )


# --------------------------------------------------------------------------- #
# Create
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_create_asset_returns_201_with_server_assigned_short_code(
    client: TestClient, operator_headers: dict[str, str]
) -> None:
    # Act
    data = _create_asset(client, operator_headers, name="db-primary", asset_type="host")

    # Assert: server assigns id + a typed short code (host -> HST-...)
    assert uuid.UUID(data["id"])
    assert data["name"] == "db-primary"
    assert data["short_code"].startswith("HST-")
    assert data["asset_type"] == "host"
    assert data["lifecycle_state"] == "active"  # schema default


@pytest.mark.integration
def test_create_asset_writes_create_audit_row(
    client: TestClient, operator_headers: dict[str, str], operator_user, db
) -> None:
    # Act
    data = _create_asset(client, operator_headers)

    # Assert: exactly one create audit row, attributed to the operator, with an
    # "after" snapshot and no "before".
    rows = _audit_rows(db, uuid.UUID(data["id"]), AuditAction.create)
    assert len(rows) == 1
    entry = rows[0]
    assert entry.actor_id == operator_user.id
    assert entry.before is None
    assert entry.after is not None
    assert entry.after["name"] == "web-01"


@pytest.mark.integration
def test_admin_can_also_create_asset(client: TestClient, admin_headers: dict[str, str]) -> None:
    # Act: admin outranks operator, so creation is allowed
    data = _create_asset(client, admin_headers, name="admin-host")

    # Assert
    assert data["name"] == "admin-host"


@pytest.mark.integration
def test_create_asset_rejects_invalid_type_with_422(
    client: TestClient, operator_headers: dict[str, str]
) -> None:
    # Act
    resp = client.post(
        ASSETS,
        json={"name": "bad", "asset_type": "not-a-real-type"},
        headers=operator_headers,
    )

    # Assert
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


# --------------------------------------------------------------------------- #
# Get / list / filter
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_get_asset_returns_full_read_projection(
    client: TestClient, operator_headers: dict[str, str], viewer_headers: dict[str, str]
) -> None:
    # Arrange
    created = _create_asset(client, operator_headers)

    # Act: any authenticated user (viewer) may read
    resp = client.get(f"{ASSETS}/{created['id']}", headers=viewer_headers)

    # Assert
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["id"] == created["id"]
    assert data["short_code"] == created["short_code"]
    assert "attributes" in data
    assert "tags" in data


@pytest.mark.integration
def test_get_missing_asset_is_404(client: TestClient, viewer_headers: dict[str, str]) -> None:
    # Act
    resp = client.get(f"{ASSETS}/{uuid.uuid4()}", headers=viewer_headers)

    # Assert
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


@pytest.mark.integration
def test_list_assets_returns_page_envelope(
    client: TestClient, operator_headers: dict[str, str], viewer_headers: dict[str, str]
) -> None:
    # Arrange
    _create_asset(client, operator_headers, name="host-a", asset_type="host")
    _create_asset(client, operator_headers, name="svc-a", asset_type="service")

    # Act
    resp = client.get(ASSETS, headers=viewer_headers)

    # Assert
    assert resp.status_code == 200, resp.text
    page = resp.json()["data"]
    assert page["total"] == 2
    assert len(page["items"]) == 2
    assert page["limit"] == 50
    assert page["offset"] == 0


@pytest.mark.integration
def test_list_assets_empty_state(client: TestClient, viewer_headers: dict[str, str]) -> None:
    # Act: no assets created
    resp = client.get(ASSETS, headers=viewer_headers)

    # Assert
    assert resp.status_code == 200
    page = resp.json()["data"]
    assert page["total"] == 0
    assert page["items"] == []


@pytest.mark.integration
def test_list_assets_filters_by_asset_type(
    client: TestClient, operator_headers: dict[str, str], viewer_headers: dict[str, str]
) -> None:
    # Arrange
    _create_asset(client, operator_headers, name="host-a", asset_type="host")
    _create_asset(client, operator_headers, name="svc-a", asset_type="service")

    # Act
    resp = client.get(ASSETS, params={"asset_type": "service"}, headers=viewer_headers)

    # Assert: only the service is returned
    assert resp.status_code == 200, resp.text
    page = resp.json()["data"]
    assert page["total"] == 1
    assert page["items"][0]["asset_type"] == "service"
    assert page["items"][0]["name"] == "svc-a"


@pytest.mark.integration
def test_list_assets_search_query_matches_name(
    client: TestClient, operator_headers: dict[str, str], viewer_headers: dict[str, str]
) -> None:
    # Arrange
    _create_asset(client, operator_headers, name="payments-api", asset_type="service")
    _create_asset(client, operator_headers, name="batch-worker", asset_type="service")

    # Act
    resp = client.get(ASSETS, params={"q": "payments"}, headers=viewer_headers)

    # Assert
    assert resp.status_code == 200, resp.text
    page = resp.json()["data"]
    assert page["total"] == 1
    assert page["items"][0]["name"] == "payments-api"


# --------------------------------------------------------------------------- #
# Update
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_update_asset_applies_partial_change_and_audits(
    client: TestClient, operator_headers: dict[str, str], operator_user, db
) -> None:
    # Arrange
    created = _create_asset(client, operator_headers, name="old-name")

    # Act
    resp = client.patch(
        f"{ASSETS}/{created['id']}",
        json={"name": "new-name", "location": "rack-7"},
        headers=operator_headers,
    )

    # Assert: the change is applied...
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["name"] == "new-name"
    assert data["location"] == "rack-7"

    # ...and a single update audit row captures before/after.
    rows = _audit_rows(db, uuid.UUID(created["id"]), AuditAction.update)
    assert len(rows) == 1
    assert rows[0].before["name"] == "old-name"
    assert rows[0].after["name"] == "new-name"
    assert rows[0].actor_id == operator_user.id


@pytest.mark.integration
def test_viewer_cannot_update_asset(
    client: TestClient, operator_headers: dict[str, str], viewer_headers: dict[str, str]
) -> None:
    # Arrange
    created = _create_asset(client, operator_headers)

    # Act
    resp = client.patch(f"{ASSETS}/{created['id']}", json={"name": "nope"}, headers=viewer_headers)

    # Assert
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


# --------------------------------------------------------------------------- #
# Lifecycle state change
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_change_state_transitions_and_writes_state_change_audit(
    client: TestClient, operator_headers: dict[str, str], operator_user, db
) -> None:
    # Arrange: created assets default to "active"
    created = _create_asset(client, operator_headers)
    assert created["lifecycle_state"] == "active"

    # Act
    resp = client.post(
        f"{ASSETS}/{created['id']}/state",
        json={"lifecycle_state": "maintenance"},
        headers=operator_headers,
    )

    # Assert: state moved...
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["lifecycle_state"] == "maintenance"

    # ...and a state_change audit row records the transition.
    rows = _audit_rows(db, uuid.UUID(created["id"]), AuditAction.state_change)
    assert len(rows) == 1
    assert rows[0].before["lifecycle_state"] == "active"
    assert rows[0].after["lifecycle_state"] == "maintenance"
    assert rows[0].actor_id == operator_user.id


# --------------------------------------------------------------------------- #
# Delete (admin-only)
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_admin_delete_asset_removes_row_and_writes_delete_audit(
    client: TestClient, admin_headers: dict[str, str], admin_user, db
) -> None:
    # Arrange
    created = _create_asset(client, admin_headers)
    asset_id = created["id"]

    # Act
    resp = client.delete(f"{ASSETS}/{asset_id}", headers=admin_headers)

    # Assert: the delete response acknowledges removal...
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["status"] == "deleted"
    assert body["asset_id"] == asset_id

    # ...the asset is actually gone...
    follow_up = client.get(f"{ASSETS}/{asset_id}", headers=admin_headers)
    assert follow_up.status_code == 404

    # ...and a delete audit row preserves the prior state (before, no after).
    rows = _audit_rows(db, uuid.UUID(asset_id), AuditAction.delete)
    assert len(rows) == 1
    assert rows[0].before is not None
    assert rows[0].after is None
    assert rows[0].actor_id == admin_user.id


@pytest.mark.integration
def test_full_lifecycle_audit_trail_is_recorded_in_order(
    client: TestClient, admin_headers: dict[str, str], db
) -> None:
    # Arrange / Act: create -> update -> state-change -> delete
    created = _create_asset(client, admin_headers)
    asset_id = uuid.UUID(created["id"])
    client.patch(f"{ASSETS}/{created['id']}", json={"name": "renamed"}, headers=admin_headers)
    client.post(
        f"{ASSETS}/{created['id']}/state",
        json={"lifecycle_state": "retired"},
        headers=admin_headers,
    )
    client.delete(f"{ASSETS}/{created['id']}", headers=admin_headers)

    # Assert: all four audit actions exist for this entity, in creation order
    rows = list(
        db.execute(
            select(AuditLog)
            .where(AuditLog.entity_type == "asset")
            .where(AuditLog.entity_id == asset_id)
            .order_by(AuditLog.created_at.asc())
        ).scalars()
    )
    actions = [r.action for r in rows]
    assert actions == [
        AuditAction.create,
        AuditAction.update,
        AuditAction.state_change,
        AuditAction.delete,
    ]


# --------------------------------------------------------------------------- #
# CSV export
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_csv_export_returns_header_and_rows(
    client: TestClient, operator_headers: dict[str, str], viewer_headers: dict[str, str]
) -> None:
    # Arrange
    _create_asset(client, operator_headers, name="export-me", asset_type="host")

    # Act
    resp = client.get(f"{ASSETS}/export", headers=viewer_headers)

    # Assert: a CSV document with the expected header and the created asset
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    body = resp.text
    lines = body.strip().splitlines()
    assert lines[0].startswith("short_code,name,asset_type")
    assert any("export-me" in line for line in lines[1:])


@pytest.mark.integration
def test_csv_export_empty_state_has_header_only(
    client: TestClient, viewer_headers: dict[str, str]
) -> None:
    # Act
    resp = client.get(f"{ASSETS}/export", headers=viewer_headers)

    # Assert: header row present, no data rows
    assert resp.status_code == 200
    lines = resp.text.strip().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("short_code,name,asset_type")
