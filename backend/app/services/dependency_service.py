"""Directed dependency-graph service.

Edges read "source depends on target". Traversals are breadth-first with a
``visited`` set and a ``max_depth`` bound, so cycles (A->B->A) and deep chains
both terminate. Each returned payload is a plain dict (``{asset, nodes, edges}``)
serialised straight into the response envelope.
"""

from __future__ import annotations

import uuid
from collections import deque

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.models.asset import Asset, AssetDependency
from app.models.enums import AuditAction
from app.services.audit_service import record_audit, snapshot

_AUDIT_ENTITY = "asset_dependency"
_DEFAULT_TREE_DEPTH = 5
_DEFAULT_GRAPH_DEPTH = 3


def _node_dict(asset: Asset) -> dict[str, object]:
    return {
        "id": str(asset.id),
        "short_code": asset.short_code,
        "name": asset.name,
        "asset_type": asset.asset_type.value,
        "lifecycle_state": asset.lifecycle_state.value,
        "environment": asset.environment.value,
    }


def _require_asset(db: Session, asset_id: uuid.UUID) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise NotFoundError("Asset not found.", details={"asset_id": str(asset_id)})
    return asset


def _traverse(
    db: Session,
    root: Asset,
    *,
    max_depth: int,
    downstream: bool,
) -> dict[str, object]:
    """BFS from ``root`` following edges in one direction.

    ``downstream`` True follows source->target (things ``root`` depends on go the
    other way); we expose two named wrappers below so callers never pass a flag.
    """
    nodes: dict[uuid.UUID, dict[str, object]] = {root.id: _node_dict(root)}
    edges: list[dict[str, object]] = []
    seen_edges: set[uuid.UUID] = set()
    visited: set[uuid.UUID] = {root.id}
    queue: deque[tuple[uuid.UUID, int]] = deque([(root.id, 0)])

    while queue:
        current_id, depth = queue.popleft()
        if depth >= max_depth:
            continue

        if downstream:
            stmt = select(AssetDependency).where(AssetDependency.source_asset_id == current_id)
        else:
            stmt = select(AssetDependency).where(AssetDependency.target_asset_id == current_id)

        for edge in db.execute(stmt).scalars():
            neighbour_id = edge.target_asset_id if downstream else edge.source_asset_id
            if edge.id not in seen_edges:
                seen_edges.add(edge.id)
                edges.append(
                    {
                        "id": str(edge.id),
                        "source_asset_id": str(edge.source_asset_id),
                        "target_asset_id": str(edge.target_asset_id),
                        "kind": edge.kind,
                    }
                )
            if neighbour_id not in nodes:
                neighbour = db.get(Asset, neighbour_id)
                if neighbour is not None:
                    nodes[neighbour_id] = _node_dict(neighbour)
            # Cycle-safe: only enqueue unvisited neighbours.
            if neighbour_id not in visited:
                visited.add(neighbour_id)
                queue.append((neighbour_id, depth + 1))

    return {
        "asset": _node_dict(root),
        "nodes": list(nodes.values()),
        "edges": edges,
    }


def get_downstream_tree(
    db: Session, asset_id: uuid.UUID, max_depth: int = _DEFAULT_TREE_DEPTH
) -> dict[str, object]:
    """Everything that depends, transitively, on ``asset_id`` (its dependants)."""
    root = _require_asset(db, asset_id)
    return _traverse(db, root, max_depth=max_depth, downstream=False)


def get_upstream_tree(
    db: Session, asset_id: uuid.UUID, max_depth: int = _DEFAULT_TREE_DEPTH
) -> dict[str, object]:
    """Everything ``asset_id`` depends on, transitively (its dependencies)."""
    root = _require_asset(db, asset_id)
    return _traverse(db, root, max_depth=max_depth, downstream=True)


def full_graph(
    db: Session, asset_id: uuid.UUID, max_depth: int = _DEFAULT_GRAPH_DEPTH
) -> dict[str, object]:
    """Union of the upstream and downstream neighbourhoods around ``asset_id``."""
    root = _require_asset(db, asset_id)
    up = _traverse(db, root, max_depth=max_depth, downstream=True)
    down = _traverse(db, root, max_depth=max_depth, downstream=False)

    nodes: dict[str, dict[str, object]] = {}
    for node in (*up["nodes"], *down["nodes"]):  # type: ignore[misc]
        nodes[str(node["id"])] = node
    edges: dict[str, dict[str, object]] = {}
    for edge in (*up["edges"], *down["edges"]):  # type: ignore[misc]
        edges[str(edge["id"])] = edge

    return {
        "asset": _node_dict(root),
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
    }


def add_edge(
    db: Session,
    source_asset_id: uuid.UUID,
    target_asset_id: uuid.UUID,
    *,
    kind: str | None = None,
    actor_id: uuid.UUID | None = None,
    source_ip: str | None = None,
) -> AssetDependency:
    """Create a directed edge. The DB also guards self/duplicate edges; we fail
    early with typed errors so callers get a clean 422/409 instead of a 500."""
    if source_asset_id == target_asset_id:
        raise ValidationAppError("An asset cannot depend on itself.")

    _require_asset(db, source_asset_id)
    _require_asset(db, target_asset_id)

    existing = db.execute(
        select(AssetDependency.id)
        .where(AssetDependency.source_asset_id == source_asset_id)
        .where(AssetDependency.target_asset_id == target_asset_id)
        .limit(1)
    ).first()
    if existing is not None:
        raise ConflictError("That dependency edge already exists.")

    edge = AssetDependency(
        source_asset_id=source_asset_id,
        target_asset_id=target_asset_id,
        kind=kind,
    )
    db.add(edge)
    db.flush()
    record_audit(
        db,
        action=AuditAction.create,
        entity_type=_AUDIT_ENTITY,
        entity_id=edge.id,
        actor_id=actor_id,
        after=snapshot(edge),
        source_ip=source_ip,
    )
    return edge


def remove_edge(
    db: Session,
    dependency_id: uuid.UUID,
    *,
    actor_id: uuid.UUID | None = None,
    source_ip: str | None = None,
) -> None:
    """Delete a dependency edge by id, recording a ``delete`` audit entry."""
    edge = db.get(AssetDependency, dependency_id)
    if edge is None:
        raise NotFoundError(
            "Dependency edge not found.", details={"dependency_id": str(dependency_id)}
        )
    before = snapshot(edge)
    db.delete(edge)
    db.flush()
    record_audit(
        db,
        action=AuditAction.delete,
        entity_type=_AUDIT_ENTITY,
        entity_id=dependency_id,
        actor_id=actor_id,
        before=before,
        source_ip=source_ip,
    )
