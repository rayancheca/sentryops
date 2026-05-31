"""Shared pytest fixtures: test database, client, and RBAC auth headers.

The test database (``sentryops_test``) is schema-built once per session via
``Base.metadata.create_all`` and every table is truncated before each test for
isolation. DATABASE_URL/SECRET_KEY are set BEFORE importing the app so the
cached settings and the module-level engine point at the test database.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://sentryops:sentryops@localhost:5432/sentryops_test",
)
os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-bytes-long-000000")
os.environ.setdefault("AI_TRIAGE_ENABLED", "false")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.models  # noqa: E402,F401  — register all tables
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.enums import Role  # noqa: E402
from app.models.user import User  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema() -> Iterator[None]:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def _make_user(db: Session, email: str, role: Role, password: str, *, mfa: bool = False) -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0].title(),
        hashed_password=hash_password(password),
        role=role,
        is_active=True,
        mfa_enabled=mfa,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_user(db: Session) -> User:
    return _make_user(db, "admin@test.local", Role.admin, "admin-pass-123", mfa=True)


@pytest.fixture
def operator_user(db: Session) -> User:
    return _make_user(db, "operator@test.local", Role.operator, "operator-pass-123")


@pytest.fixture
def viewer_user(db: Session) -> User:
    return _make_user(db, "viewer@test.local", Role.viewer, "viewer-pass-123")


def _auth_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(client: TestClient, admin_user: User) -> dict[str, str]:
    return _auth_headers(client, "admin@test.local", "admin-pass-123")


@pytest.fixture
def operator_headers(client: TestClient, operator_user: User) -> dict[str, str]:
    return _auth_headers(client, "operator@test.local", "operator-pass-123")


@pytest.fixture
def viewer_headers(client: TestClient, viewer_user: User) -> dict[str, str]:
    return _auth_headers(client, "viewer@test.local", "viewer-pass-123")
