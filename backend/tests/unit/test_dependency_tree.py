"""Dependency-graph traversal tests (logic-with-data, uses the db fixture).

Edge semantics from app/services/dependency_service.py: an ``AssetDependency``
row reads "source depends on target".

    * get_upstream_tree(X)   -> things X depends on   (follow source==X to targets)
    * get_downstream_tree(X) -> things that depend on X (follow target==X to sources)

We build asset graphs directly via ORM rows and assert the reachable node/edge
sets, max_depth bounding, cycle termination, and the full_graph union shape.
"""

from __future__ import annotations

import itertools

import pytest
from sqlalchemy.orm import Session

from app.models.asset import Asset, AssetDependency
from app.models.enums import AssetType, Environment, LifecycleState
from app.services.dependency_service import (
    full_graph,
    get_downstream_tree,
    get_upstream_tree,
)

pytestmark = pytest.mark.unit

_codes = itertools.count(1)


def _make_asset(db: Session, name: str) -> Asset:
    """Persist a minimal active prod host asset with a unique short_code."""
    asset = Asset(
        short_code=f"AST-{next(_codes):05d}",
        name=name,
        asset_type=AssetType.host,
        lifecycle_state=LifecycleState.active,
        environment=Environment.prod,
    )
    db.add(asset)
    db.flush()
    return asset


def _add_edge(db: Session, source: Asset, target: Asset) -> AssetDependency:
    """Directed edge: ``source`` depends on ``target``."""
    edge = AssetDependency(source_asset_id=source.id, target_asset_id=target.id)
    db.add(edge)
    db.flush()
    return edge


def _node_ids(tree: dict[str, object]) -> set[str]:
    return {node["id"] for node in tree["nodes"]}  # type: ignore[index,union-attr]


def _edge_pairs(tree: dict[str, object]) -> set[tuple[str, str]]:
    return {
        (edge["source_asset_id"], edge["target_asset_id"])  # type: ignore[index]
        for edge in tree["edges"]  # type: ignore[union-attr]
    }


# --------------------------------------------------------------------------- #
# Linear chain A -> B -> C                                                     #
# --------------------------------------------------------------------------- #


def test_upstream_chain_collects_all_transitive_dependencies(db: Session) -> None:
    # Arrange: A depends on B, B depends on C.
    a = _make_asset(db, "A")
    b = _make_asset(db, "B")
    c = _make_asset(db, "C")
    _add_edge(db, a, b)
    _add_edge(db, b, c)

    # Act: things A depends on, transitively.
    tree = get_upstream_tree(db, a.id)

    # Assert: A reaches B and C; the root is included.
    assert _node_ids(tree) == {str(a.id), str(b.id), str(c.id)}
    assert _edge_pairs(tree) == {(str(a.id), str(b.id)), (str(b.id), str(c.id))}
    assert tree["asset"]["id"] == str(a.id)  # type: ignore[index]


def test_downstream_chain_collects_all_transitive_dependants(db: Session) -> None:
    # Arrange: A depends on B, B depends on C.
    a = _make_asset(db, "A")
    b = _make_asset(db, "B")
    c = _make_asset(db, "C")
    _add_edge(db, a, b)
    _add_edge(db, b, c)

    # Act: everything that (transitively) depends on C.
    tree = get_downstream_tree(db, c.id)

    # Assert: C is depended on by B, and B by A.
    assert _node_ids(tree) == {str(a.id), str(b.id), str(c.id)}
    assert tree["asset"]["id"] == str(c.id)  # type: ignore[index]


def test_upstream_leaf_has_no_dependencies(db: Session) -> None:
    # Arrange: A depends on B; C (the leaf target) depends on nothing.
    a = _make_asset(db, "A")
    b = _make_asset(db, "B")
    c = _make_asset(db, "C")
    _add_edge(db, a, b)
    _add_edge(db, b, c)

    # Act: things C depends on.
    tree = get_upstream_tree(db, c.id)

    # Assert: only C itself, no edges.
    assert _node_ids(tree) == {str(c.id)}
    assert tree["edges"] == []


def test_downstream_root_with_no_dependants_returns_only_itself(db: Session) -> None:
    # Arrange: A is the top of the chain, nothing depends on it.
    a = _make_asset(db, "A")
    b = _make_asset(db, "B")
    _add_edge(db, a, b)

    # Act
    tree = get_downstream_tree(db, a.id)

    # Assert
    assert _node_ids(tree) == {str(a.id)}
    assert tree["edges"] == []


# --------------------------------------------------------------------------- #
# Diamond: A -> B, A -> D, B -> C, D -> C                                      #
# --------------------------------------------------------------------------- #


def _build_diamond(db: Session) -> dict[str, Asset]:
    a = _make_asset(db, "A")
    b = _make_asset(db, "B")
    c = _make_asset(db, "C")
    d = _make_asset(db, "D")
    _add_edge(db, a, b)
    _add_edge(db, a, d)
    _add_edge(db, b, c)
    _add_edge(db, d, c)
    return {"A": a, "B": b, "C": c, "D": d}


def test_diamond_upstream_reaches_convergence_node_once(db: Session) -> None:
    # Arrange
    g = _build_diamond(db)

    # Act: things A depends on (B, D, and the shared C).
    tree = get_upstream_tree(db, g["A"].id)

    # Assert: C appears exactly once despite two paths into it.
    node_ids = [node["id"] for node in tree["nodes"]]  # type: ignore[index,union-attr]
    assert set(node_ids) == {str(g[k].id) for k in ("A", "B", "C", "D")}
    assert node_ids.count(str(g["C"].id)) == 1
    # All four edges of the diamond appear, deduplicated by edge id.
    assert len(tree["edges"]) == 4  # type: ignore[arg-type]


def test_diamond_downstream_from_convergence_reaches_both_branches(db: Session) -> None:
    # Arrange
    g = _build_diamond(db)

    # Act: everything that depends on C -> B and D directly, A transitively.
    tree = get_downstream_tree(db, g["C"].id)

    # Assert
    assert _node_ids(tree) == {str(g[k].id) for k in ("A", "B", "C", "D")}


# --------------------------------------------------------------------------- #
# max_depth bounding                                                          #
# --------------------------------------------------------------------------- #


def test_upstream_respects_max_depth(db: Session) -> None:
    # Arrange: A -> B -> C -> D, a depth-3 chain.
    a = _make_asset(db, "A")
    b = _make_asset(db, "B")
    c = _make_asset(db, "C")
    d = _make_asset(db, "D")
    _add_edge(db, a, b)
    _add_edge(db, b, c)
    _add_edge(db, c, d)

    # Act: depth 1 from A only reaches its direct dependency B.
    depth1 = get_upstream_tree(db, a.id, max_depth=1)
    depth2 = get_upstream_tree(db, a.id, max_depth=2)

    # Assert
    assert _node_ids(depth1) == {str(a.id), str(b.id)}
    assert _node_ids(depth2) == {str(a.id), str(b.id), str(c.id)}


def test_max_depth_zero_returns_only_root(db: Session) -> None:
    # Arrange
    a = _make_asset(db, "A")
    b = _make_asset(db, "B")
    _add_edge(db, a, b)

    # Act: depth 0 expands nothing.
    tree = get_upstream_tree(db, a.id, max_depth=0)

    # Assert
    assert _node_ids(tree) == {str(a.id)}
    assert tree["edges"] == []


# --------------------------------------------------------------------------- #
# Cycle: A -> B -> A (must terminate, no infinite loop)                        #
# --------------------------------------------------------------------------- #


def test_upstream_cycle_terminates_and_collects_both_nodes(db: Session) -> None:
    # Arrange: a 2-cycle A -> B -> A.
    a = _make_asset(db, "A")
    b = _make_asset(db, "B")
    _add_edge(db, a, b)
    _add_edge(db, b, a)

    # Act: a generous max_depth would loop forever without the visited set.
    tree = get_upstream_tree(db, a.id, max_depth=100)

    # Assert: both nodes once, both edges once.
    assert _node_ids(tree) == {str(a.id), str(b.id)}
    assert _edge_pairs(tree) == {(str(a.id), str(b.id)), (str(b.id), str(a.id))}


def test_downstream_cycle_terminates(db: Session) -> None:
    # Arrange
    a = _make_asset(db, "A")
    b = _make_asset(db, "B")
    _add_edge(db, a, b)
    _add_edge(db, b, a)

    # Act
    tree = get_downstream_tree(db, a.id, max_depth=100)

    # Assert
    assert _node_ids(tree) == {str(a.id), str(b.id)}
    assert len(tree["edges"]) == 2  # type: ignore[arg-type]


def test_self_loop_via_cycle_does_not_duplicate_root(db: Session) -> None:
    # Arrange: three-node cycle A -> B -> C -> A.
    a = _make_asset(db, "A")
    b = _make_asset(db, "B")
    c = _make_asset(db, "C")
    _add_edge(db, a, b)
    _add_edge(db, b, c)
    _add_edge(db, c, a)

    # Act
    tree = get_upstream_tree(db, a.id, max_depth=100)

    # Assert: each node exactly once; root is not re-added when the cycle closes.
    node_ids = [node["id"] for node in tree["nodes"]]  # type: ignore[index,union-attr]
    assert node_ids.count(str(a.id)) == 1
    assert set(node_ids) == {str(a.id), str(b.id), str(c.id)}
    assert len(tree["edges"]) == 3  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# full_graph: union of upstream + downstream neighbourhoods                    #
# --------------------------------------------------------------------------- #


def test_full_graph_shape_and_keys(db: Session) -> None:
    # Arrange
    a = _make_asset(db, "A")
    b = _make_asset(db, "B")
    _add_edge(db, a, b)

    # Act
    graph = full_graph(db, a.id)

    # Assert: documented payload shape.
    assert set(graph.keys()) == {"asset", "nodes", "edges"}
    assert graph["asset"]["id"] == str(a.id)  # type: ignore[index]
    node = graph["nodes"][0]  # type: ignore[index]
    assert set(node.keys()) == {  # type: ignore[union-attr]
        "id",
        "short_code",
        "name",
        "asset_type",
        "lifecycle_state",
        "environment",
    }


def test_full_graph_unions_upstream_and_downstream(db: Session) -> None:
    # Arrange: chain X -> MID -> Y. From MID, upstream is Y, downstream is X.
    x = _make_asset(db, "X")
    mid = _make_asset(db, "MID")
    y = _make_asset(db, "Y")
    _add_edge(db, x, mid)
    _add_edge(db, mid, y)

    # Act
    graph = full_graph(db, mid.id)

    # Assert: both neighbours are present, each edge once.
    assert _node_ids(graph) == {str(x.id), str(mid.id), str(y.id)}
    assert _edge_pairs(graph) == {(str(x.id), str(mid.id)), (str(mid.id), str(y.id))}


def test_full_graph_dedups_shared_edges(db: Session) -> None:
    # Arrange: a 2-cycle means the same edges appear in both directions of the
    # union; full_graph must dedup them by id.
    a = _make_asset(db, "A")
    b = _make_asset(db, "B")
    _add_edge(db, a, b)
    _add_edge(db, b, a)

    # Act
    graph = full_graph(db, a.id)

    # Assert
    edge_ids = [edge["id"] for edge in graph["edges"]]  # type: ignore[index,union-attr]
    assert len(edge_ids) == len(set(edge_ids)) == 2
    assert _node_ids(graph) == {str(a.id), str(b.id)}
