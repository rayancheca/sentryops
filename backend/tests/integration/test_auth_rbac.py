"""Integration tests for authentication, token lifecycle, and the RBAC matrix.

These exercise the real HTTP boundary (``TestClient`` + the ``{success, data,
error, meta}`` envelope). The RBAC matrix is the headline: authorization is
enforced in :mod:`app.api.deps`, so we prove that viewers cannot reach
operator-only routes, operators cannot reach admin-only routes, and admins can
reach everything.

Login/refresh are rate-limited (``10/minute`` per client IP, and ``TestClient``
presents a single fixed IP). We reset the slowapi limiter before each test so a
test that authenticates several times cannot trip a spurious 429.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import limiter
from app.models.enums import Role
from app.models.user import RefreshToken, User

LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> Iterator[None]:
    """Clear the shared (Redis-backed) auth rate-limit window between tests."""
    limiter.reset()
    yield
    limiter.reset()


def _login(client: TestClient, email: str, password: str):
    return client.post(LOGIN, json={"email": email, "password": password})


# --------------------------------------------------------------------------- #
# Login + /me
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_login_success_returns_token_pair_in_envelope(
    client: TestClient, operator_user: User
) -> None:
    # Arrange / Act
    resp = _login(client, "operator@test.local", "operator-pass-123")

    # Assert
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["error"] is None
    data = body["data"]
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["token_type"] == "bearer"


@pytest.mark.integration
def test_login_with_wrong_password_is_401(client: TestClient, operator_user: User) -> None:
    # Act
    resp = _login(client, "operator@test.local", "definitely-wrong")

    # Assert: opaque 401 with the standard error envelope
    assert resp.status_code == 401
    body = resp.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "unauthorized"


@pytest.mark.integration
def test_login_unknown_email_is_401(client: TestClient) -> None:
    # Act
    resp = _login(client, "nobody@test.local", "whatever-123")

    # Assert
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


@pytest.mark.integration
def test_login_inactive_user_is_401(client: TestClient, db, operator_user: User) -> None:
    # Arrange: disable the account directly in the DB
    user = db.get(User, operator_user.id)
    user.is_active = False
    db.commit()

    # Act
    resp = _login(client, "operator@test.local", "operator-pass-123")

    # Assert: same opaque 401 as bad credentials (no enumeration)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


@pytest.mark.integration
def test_me_with_valid_token_returns_current_user(
    client: TestClient, operator_headers: dict[str, str]
) -> None:
    # Act
    resp = client.get(ME, headers=operator_headers)

    # Assert
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["email"] == "operator@test.local"
    assert data["role"] == Role.operator.value
    assert "hashed_password" not in data


@pytest.mark.integration
def test_me_without_token_is_401(client: TestClient) -> None:
    # Act
    resp = client.get(ME)

    # Assert
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


@pytest.mark.integration
def test_me_with_garbage_token_is_401(client: TestClient) -> None:
    # Act
    resp = client.get(ME, headers={"Authorization": "Bearer not-a-real-jwt"})

    # Assert
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


# --------------------------------------------------------------------------- #
# Refresh-token rotation (single-use)
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_refresh_rotates_to_a_new_pair(client: TestClient, operator_user: User) -> None:
    # Arrange
    login = _login(client, "operator@test.local", "operator-pass-123")
    old_refresh = login.json()["data"]["refresh_token"]

    # Act
    rotated = client.post(REFRESH, json={"refresh_token": old_refresh})

    # Assert: a brand-new, different pair is issued
    assert rotated.status_code == 200, rotated.text
    new_pair = rotated.json()["data"]
    assert new_pair["access_token"]
    assert new_pair["refresh_token"]
    assert new_pair["refresh_token"] != old_refresh


@pytest.mark.integration
def test_old_refresh_token_is_rejected_after_rotation(
    client: TestClient, operator_user: User
) -> None:
    # Arrange: log in, then rotate once
    old_refresh = _login(client, "operator@test.local", "operator-pass-123").json()["data"][
        "refresh_token"
    ]
    rotated = client.post(REFRESH, json={"refresh_token": old_refresh})
    new_refresh = rotated.json()["data"]["refresh_token"]

    # Act: present the OLD (now-revoked) refresh token a second time
    replay = client.post(REFRESH, json={"refresh_token": old_refresh})

    # Assert: single-use enforcement rejects the replay...
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "unauthorized"

    # ...but the freshly minted token still works.
    again = client.post(REFRESH, json={"refresh_token": new_refresh})
    assert again.status_code == 200, again.text


@pytest.mark.integration
def test_refresh_with_access_token_is_rejected(client: TestClient, operator_user: User) -> None:
    # Arrange: an access token is the wrong token type for /refresh
    access = _login(client, "operator@test.local", "operator-pass-123").json()["data"][
        "access_token"
    ]

    # Act
    resp = client.post(REFRESH, json={"refresh_token": access})

    # Assert
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


@pytest.mark.integration
def test_refresh_with_garbage_token_is_401(client: TestClient) -> None:
    # Act
    resp = client.post(REFRESH, json={"refresh_token": "not-a-jwt"})

    # Assert
    assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# Logout (revocation)
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_logout_revokes_refresh_token(client: TestClient, db, operator_user: User) -> None:
    # Arrange
    refresh = _login(client, "operator@test.local", "operator-pass-123").json()["data"][
        "refresh_token"
    ]

    # Act
    logout = client.post(LOGOUT, json={"refresh_token": refresh})

    # Assert: logout acknowledges revocation...
    assert logout.status_code == 200, logout.text
    assert logout.json()["data"]["revoked"] is True

    # ...the underlying RefreshToken row is marked revoked...
    rows = db.query(RefreshToken).all()
    assert len(rows) == 1
    assert rows[0].revoked is True

    # ...and the token can no longer be rotated.
    rotate = client.post(REFRESH, json={"refresh_token": refresh})
    assert rotate.status_code == 401


@pytest.mark.integration
def test_logout_is_idempotent_and_ignores_garbage(client: TestClient) -> None:
    # Act: logging out an unknown/garbage token must not error (200, never raises)
    resp = client.post(LOGOUT, json={"refresh_token": "not-a-jwt"})

    # Assert
    assert resp.status_code == 200
    assert resp.json()["data"]["revoked"] is True


# --------------------------------------------------------------------------- #
# THE RBAC MATRIX
# --------------------------------------------------------------------------- #
#
# Role hierarchy: admin > operator > viewer.
#   - viewer  : read-only (can GET /assets, denied POST /assets)
#   - operator: viewer + asset mutations (denied POST /users, DELETE /assets)
#   - admin   : everything
#


def _minimal_asset_payload() -> dict[str, object]:
    return {"name": "rbac-probe-host", "asset_type": "host"}


@pytest.mark.integration
def test_viewer_can_read_assets(client: TestClient, viewer_headers: dict[str, str]) -> None:
    # Act
    resp = client.get("/api/v1/assets", headers=viewer_headers)

    # Assert: any authenticated user (viewer floor) may read
    assert resp.status_code == 200, resp.text


@pytest.mark.integration
def test_viewer_is_denied_operator_only_create_asset(
    client: TestClient, viewer_headers: dict[str, str]
) -> None:
    # Act
    resp = client.post("/api/v1/assets", json=_minimal_asset_payload(), headers=viewer_headers)

    # Assert
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


@pytest.mark.integration
def test_operator_can_create_asset(client: TestClient, operator_headers: dict[str, str]) -> None:
    # Act
    resp = client.post("/api/v1/assets", json=_minimal_asset_payload(), headers=operator_headers)

    # Assert
    assert resp.status_code == 201, resp.text


@pytest.mark.integration
def test_operator_is_denied_admin_only_create_user(
    client: TestClient, operator_headers: dict[str, str]
) -> None:
    # Arrange
    payload = {
        "email": "new-recruit@test.local",
        "full_name": "New Recruit",
        "password": "a-strong-pass-123",
        "role": "viewer",
    }

    # Act
    resp = client.post("/api/v1/users", json=payload, headers=operator_headers)

    # Assert
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


@pytest.mark.integration
def test_operator_is_denied_admin_only_delete_asset(
    client: TestClient, operator_headers: dict[str, str], admin_headers: dict[str, str]
) -> None:
    # Arrange: operator creates an asset they are allowed to create...
    created = client.post("/api/v1/assets", json=_minimal_asset_payload(), headers=operator_headers)
    asset_id = created.json()["data"]["id"]

    # Act: ...but deleting it is admin-only
    resp = client.delete(f"/api/v1/assets/{asset_id}", headers=operator_headers)

    # Assert
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


@pytest.mark.integration
def test_admin_can_create_user(client: TestClient, admin_headers: dict[str, str]) -> None:
    # Arrange
    payload = {
        "email": "admin-made@test.local",
        "full_name": "Admin Made",
        "password": "a-strong-pass-123",
        "role": "operator",
    }

    # Act
    resp = client.post("/api/v1/users", json=payload, headers=admin_headers)

    # Assert
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["email"] == "admin-made@test.local"


@pytest.mark.integration
def test_admin_can_create_and_delete_asset(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    # Arrange: admin sits above operator, so it can create...
    created = client.post("/api/v1/assets", json=_minimal_asset_payload(), headers=admin_headers)
    assert created.status_code == 201, created.text
    asset_id = created.json()["data"]["id"]

    # Act: ...and is the only role allowed to delete
    deleted = client.delete(f"/api/v1/assets/{asset_id}", headers=admin_headers)

    # Assert
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["data"]["status"] == "deleted"


@pytest.mark.integration
def test_admin_can_list_users(client: TestClient, admin_headers: dict[str, str]) -> None:
    # Act
    resp = client.get("/api/v1/users", headers=admin_headers)

    # Assert: admin-only list route is reachable and returns the page shape
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert "items" in data
    assert "total" in data


@pytest.mark.integration
def test_unauthenticated_mutation_is_401_not_403(client: TestClient) -> None:
    # Act: no token at all -> authentication failure precedes authorization
    resp = client.post("/api/v1/assets", json=_minimal_asset_payload())

    # Assert
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"
