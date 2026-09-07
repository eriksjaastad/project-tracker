"""Integration tests for memory graph API type filters against live data.

Runs the app in-process via TestClient. It used to require a dashboard already
listening on localhost:8000, probed once at import time with a 3-second
timeout -- so a single blip during collection silently turned all six of these
into skips for the whole run, and a skip reads as benign. That happened: one
run reported 7 skipped, the next 1, with the server up the entire time. These
tests were contributing coverage only by luck, and never at all in CI, which
has no server.

The only genuine precondition is brain.db, which these tests read real data
from. That is a stable fact about the filesystem rather than a race, so it is
what gates them now -- and the skip reason names the actual path, so "did not
run" is legible instead of misleading.

Tests the /api/memory/types and /api/memory-graph endpoints to verify
that the type filter values returned by the types API correspond to
actual nodes in the graph data.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dashboard.app import app

client = TestClient(app)

BRAIN_DB = Path.home() / "projects" / "ai-memory" / "brain.db"
BRAIN_AVAILABLE = BRAIN_DB.is_file()

pytestmark = pytest.mark.skipif(
    not BRAIN_AVAILABLE,
    reason=f"brain.db not present at {BRAIN_DB}; these tests read real graph data",
)


@pytest.fixture(scope="module")
def memory_types() -> list[str]:
    """Fetch the list of thought types from /api/memory/types."""
    r = client.get("/api/memory/types")
    assert r.status_code == 200, f"Types endpoint returned {r.status_code}"
    data = r.json()
    assert "types" in data, "Response missing 'types' key"
    assert len(data["types"]) > 0, "Types list is empty"
    return data["types"]


@pytest.fixture(scope="module")
def graph_data() -> dict:
    """Fetch the full memory graph from /api/memory-graph."""
    # Use high min_similarity + low max_edges to minimize edge computation time.
    # We only need nodes and their types for filter testing, not the full edge set.
    r = client.get(
        "/api/memory-graph",
        params={"min_similarity": 0.95, "max_edges_per_node": 1},
    )
    assert r.status_code == 200, f"Graph endpoint returned {r.status_code}"
    data = r.json()
    assert "nodes" in data, "Response missing 'nodes' key"
    assert "edges" in data, "Response missing 'edges' key"
    assert "stats" in data, "Response missing 'stats' key"
    return data


def test_types_endpoint_returns_list(memory_types):
    """The /api/memory/types endpoint returns a non-empty list of strings."""
    assert isinstance(memory_types, list)
    assert all(isinstance(t, str) for t in memory_types)
    assert len(memory_types) > 0


def test_graph_endpoint_returns_nodes(graph_data):
    """The /api/memory-graph endpoint returns nodes and edges."""
    assert len(graph_data["nodes"]) > 0, "Graph has no nodes"
    assert graph_data["stats"]["total_thoughts"] == len(graph_data["nodes"])


def test_graph_nodes_have_type_field(graph_data):
    """Every node in the graph must have a 'type' field."""
    for node in graph_data["nodes"]:
        assert "type" in node, f"Node {node.get('id', '?')} missing 'type' field"


def test_canonical_types_present(memory_types):
    """The canonical types (observation, decision, idea, question) are always included."""
    for canonical in ("observation", "decision", "idea", "question"):
        assert canonical in memory_types, f"Canonical type '{canonical}' missing from types list"


def test_filter_nodes_by_each_type(memory_types, graph_data):
    """For each type from the types API, filter nodes client-side and report coverage.

    This mimics what the frontend does: receive the full graph, then filter
    nodes by type. Types with 0 matching nodes are collected and reported
    (not treated as failures).
    """
    nodes = graph_data["nodes"]
    populated_types = []
    empty_types = []

    for thought_type in memory_types:
        matching = [n for n in nodes if n["type"] == thought_type]
        if matching:
            populated_types.append((thought_type, len(matching)))
        else:
            empty_types.append(thought_type)

    # Diagnostic output (visible with pytest -v or -s)
    print("\n--- Memory Graph Type Filter Report ---")
    print(f"Total nodes: {len(nodes)}")
    print(f"Total types from API: {len(memory_types)}")
    print(f"\nPopulated types ({len(populated_types)}):")
    for t, count in sorted(populated_types, key=lambda x: -x[1]):
        print(f"  {t}: {count} nodes")
    if empty_types:
        print(f"\nEmpty types ({len(empty_types)}):")
        for t in sorted(empty_types):
            print(f"  {t}: 0 nodes")
    print("--- End Report ---\n")

    # At least some types should have nodes
    assert len(populated_types) > 0, "No types matched any nodes in the graph"


def test_all_node_types_are_in_types_list(memory_types, graph_data):
    """Every type found on graph nodes should be present in the types API response.

    If a node has a type that isn't in /api/memory/types, the frontend
    filter dropdown would be incomplete.
    """
    node_types = {n["type"] for n in graph_data["nodes"]}
    missing = node_types - set(memory_types)
    assert not missing, (
        f"Node types not in /api/memory/types response: {sorted(missing)}"
    )
