"""Dependency-graph endpoints: add/remove edges and traverse up/down/full.

Tree and graph reads return plain ``{asset, nodes, edges}`` dicts; edge mutations
require operator.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.api.deps import CurrentUser, DbSession, RequireOperator
from app.schemas.common import Envelope
from app.schemas.dependency import DependencyCreate, DependencyRead
from app.services import dependency_service

router = APIRouter(prefix="/dependencies", tags=["dependencies"])

_MIN_DEPTH = 1
_MAX_DEPTH = 10


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post(
    "",
    response_model=Envelope[DependencyRead],
    status_code=201,
    summary="Create a dependency edge",
)
def add_dependency(
    payload: DependencyCreate,
    db: DbSession,
    user: RequireOperator,
    request: Request,
) -> Envelope[DependencyRead]:
    edge = dependency_service.add_edge(
        db,
        payload.source_asset_id,
        payload.target_asset_id,
        kind=payload.kind,
        actor_id=user.id,
        source_ip=_client_ip(request),
    )
    db.commit()
    db.refresh(edge)
    return Envelope.ok(DependencyRead.model_validate(edge))


@router.delete(
    "/{dependency_id}",
    response_model=Envelope[dict[str, str]],
    summary="Delete a dependency edge",
)
def remove_dependency(
    dependency_id: uuid.UUID,
    db: DbSession,
    user: RequireOperator,
    request: Request,
) -> Envelope[dict[str, str]]:
    dependency_service.remove_edge(
        db, dependency_id, actor_id=user.id, source_ip=_client_ip(request)
    )
    db.commit()
    return Envelope.ok({"status": "deleted", "dependency_id": str(dependency_id)})


@router.get(
    "/upstream/{asset_id}",
    response_model=Envelope[dict[str, object]],
    summary="Assets this asset depends on (transitive)",
)
def upstream(
    asset_id: uuid.UUID,
    db: DbSession,
    _user: CurrentUser,
    max_depth: Annotated[int, Query(ge=_MIN_DEPTH, le=_MAX_DEPTH)] = 5,
) -> Envelope[dict[str, object]]:
    return Envelope.ok(dependency_service.get_upstream_tree(db, asset_id, max_depth=max_depth))


@router.get(
    "/downstream/{asset_id}",
    response_model=Envelope[dict[str, object]],
    summary="Assets that depend on this asset (transitive)",
)
def downstream(
    asset_id: uuid.UUID,
    db: DbSession,
    _user: CurrentUser,
    max_depth: Annotated[int, Query(ge=_MIN_DEPTH, le=_MAX_DEPTH)] = 5,
) -> Envelope[dict[str, object]]:
    return Envelope.ok(dependency_service.get_downstream_tree(db, asset_id, max_depth=max_depth))


@router.get(
    "/graph/{asset_id}",
    response_model=Envelope[dict[str, object]],
    summary="Combined neighbourhood graph around an asset",
)
def graph(
    asset_id: uuid.UUID,
    db: DbSession,
    _user: CurrentUser,
    max_depth: Annotated[int, Query(ge=_MIN_DEPTH, le=_MAX_DEPTH)] = 3,
) -> Envelope[dict[str, object]]:
    return Envelope.ok(dependency_service.full_graph(db, asset_id, max_depth=max_depth))
