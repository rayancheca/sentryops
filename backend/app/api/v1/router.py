"""Aggregate every v1 domain router under a single APIRouter mounted at /api/v1."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    ai,
    assets,
    audit,
    auth,
    checkouts,
    compliance,
    dependencies,
    incidents,
    observability,
    tags,
    users,
)

api_router = APIRouter()

for _module in (
    auth,
    users,
    assets,
    tags,
    dependencies,
    checkouts,
    audit,
    compliance,
    observability,
    incidents,
    ai,
):
    api_router.include_router(_module.router)
