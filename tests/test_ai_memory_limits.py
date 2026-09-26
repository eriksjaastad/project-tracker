"""Tests for #7147: /api/ai-memory server-side caps and build-status.

Covers:
- max_nodes / max_edges caps, with strongest edges kept and truthful stats
- 400s for invalid query params
- clamping of out-of-range values
- GET /api/ai-memory/build-status (ok / failed / unknown)
- removal of the dead POST /api/ai-memory/rebuild endpoint and its JS

All brain.db access goes through a tmp_path fixture; the real
~/projects/ai-memory/brain.db is never touched.
"""

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import dashboard.app as dashboard_app
from dashboard.app import app

client = TestClient(app)

REPO_ROOT = Path(dashboard_app.__file__).resolve().parent.parent

N_NODES = 120


@pytest.fixture
def brain_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a tiny graph_nodes/graph_edges fixture under tmp_path/ai-memory.

    Node i has mention_count N_NODES - i + 1, so node 1 is the largest.
    Edges are the complete graph on the N_NODES nodes, weight = source*1000 +
    target, which makes the strongest edges uniquely ordered and lets tests
    assert exactly which edges survive the weight-DESC cap. The endpoint
    resolves brain.db through config_projects_root(), so pointing that at
    tmp_path redirects it to the fixture without touching the real ai-memory
    checkout.
    """
    db_path = tmp_path / "ai-memory" / "brain.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE graph_nodes (id INTEGER PRIMARY KEY, type TEXT, name TEXT, "
        "description TEXT, mention_count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE graph_edges (source_node_id INTEGER, target_node_id INTEGER, "
        "type TEXT, weight REAL)"
    )
    conn.executemany(
        "INSERT INTO graph_nodes VALUES (?, 'concept', ?, 'desc', ?)",
        [
            (node_id, f"n{node_id}", N_NODES - node_id + 1)
            for node_id in range(1, N_NODES + 1)
        ],
    )
    conn.executemany(
        "INSERT INTO graph_edges VALUES (?, ?, 'relates_to', ?)",
        [
            (i, j, i * 1000.0 + j)
            for i in range(1, N_NODES + 1)
            for j in range(i + 1, N_NODES + 1)
        ],
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(dashboard_app, "config_projects_root", lambda: tmp_path)
    return db_path


def _ids(nodes) -> set:
    return {n["id"] for n in nodes}


def test_max_nodes_cap_keeps_top_nodes_by_size(brain_db):
    r = client.get("/api/ai-memory", params={"max_nodes": 60, "max_edges": 1000})
    assert r.status_code == 200
    data = r.json()

    assert _ids(data["nodes"]) == set(range(1, 61))  # top 60 by mention_count
    stats = data["stats"]
    assert stats["nodes_shown"] == 60
    assert stats["total_nodes_available"] == N_NODES
    # 1770 edges exist between the top-60 nodes; the edge cap bites too.
    assert stats["edges_shown"] == 1000
    assert stats["total_edges_available"] == N_NODES * (N_NODES - 1) // 2
    assert stats["truncated"] is True


def test_max_edges_cap_keeps_strongest_edges_between_kept_nodes(brain_db):
    r = client.get("/api/ai-memory", params={"max_nodes": 60, "max_edges": 100})
    assert r.status_code == 200
    data = r.json()

    assert _ids(data["nodes"]) == set(range(1, 61))
    assert len(data["edges"]) == 100
    # Strongest edges between the kept (top-60) nodes, weight = source*1000 +
    # target, descending: (59,60), (58,60), (58,59), (57,60), (57,59), ...
    assert [(e["source"], e["target"]) for e in data["edges"][:5]] == [
        (59, 60), (58, 60), (58, 59), (57, 60), (57, 59),
    ]
    # The strongest edge in the DB ((119,120), weight 119120) involves trimmed
    # nodes and must not appear.
    assert all(e["source"] <= 60 and e["target"] <= 60 for e in data["edges"])
    stats = data["stats"]
    assert stats["edges_shown"] == 100
    assert stats["total_edges_available"] == N_NODES * (N_NODES - 1) // 2
    assert stats["truncated"] is True


def test_no_truncation_when_under_caps(brain_db):
    r = client.get("/api/ai-memory", params={"max_nodes": 200, "max_edges": 10000})
    assert r.status_code == 200
    data = r.json()

    assert _ids(data["nodes"]) == set(range(1, N_NODES + 1))
    assert len(data["edges"]) == N_NODES * (N_NODES - 1) // 2
    stats = data["stats"]
    assert stats["total_nodes_available"] == stats["nodes_shown"] == N_NODES
    assert stats["total_edges_available"] == stats["edges_shown"] == len(data["edges"])
    assert stats["truncated"] is False
    # Legacy keys still work and mean the shown counts.
    assert stats["total_nodes"] == stats["nodes_shown"]
    assert stats["total_edges"] == stats["edges_shown"]


def test_defaults_apply_caps(brain_db):
    r = client.get("/api/ai-memory")
    assert r.status_code == 200
    data = r.json()
    stats = data["stats"]
    # Defaults: 1500 nodes (> 120, all shown) and 5000 edges (< 7140, capped).
    assert stats["nodes_shown"] == N_NODES
    assert stats["total_nodes_available"] == N_NODES
    assert stats["edges_shown"] == 5000
    assert stats["total_edges_available"] == N_NODES * (N_NODES - 1) // 2
    assert stats["truncated"] is True


def test_invalid_max_params_return_400(brain_db):
    for params in (
        {"max_nodes": "abc"},
        {"max_edges": "abc"},
        {"max_nodes": ""},
        {"max_edges": ""},
    ):
        r = client.get("/api/ai-memory", params=params)
        assert r.status_code == 400, params
        body = r.json()
        assert "max_nodes" in body["error"] or "max_edges" in body["error"]


def test_out_of_range_params_are_clamped(brain_db):
    # Below the floors (50 nodes / 100 edges): clamped up, so the top 50 nodes
    # and the 100 strongest edges between them come back.
    r = client.get("/api/ai-memory", params={"max_nodes": 1, "max_edges": 1})
    assert r.status_code == 200
    data = r.json()
    assert len(data["nodes"]) == 50
    assert len(data["edges"]) == 100

    # Above the ceilings: clamped down, still serves the whole fixture.
    r = client.get("/api/ai-memory", params={"max_nodes": 999999, "max_edges": 999999})
    assert r.status_code == 200
    data = r.json()
    assert len(data["nodes"]) == N_NODES
    assert len(data["edges"]) == N_NODES * (N_NODES - 1) // 2


def test_min_mentions_filter_still_works_with_caps(brain_db):
    r = client.get(
        "/api/ai-memory",
        params={"min_mentions": 100, "max_nodes": 50, "max_edges": 1000},
    )
    assert r.status_code == 200
    data = r.json()

    # mention_count >= 100 means nodes 1..21.
    assert _ids(data["nodes"]) == set(range(1, 22))
    stats = data["stats"]
    assert stats["total_nodes_available"] == 21
    assert stats["total_edges_available"] == 21 * 20 // 2
    assert stats["truncated"] is False


def _write_receipt(tmp_path: Path, content: str | None) -> Path:
    receipt_dir = tmp_path / "ai-memory" / "logs" / "cron"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt = receipt_dir / "com.ai-memory.weekly-graph-build.json"
    if content is not None:
        receipt.write_text(content)
    return receipt


def _get_build_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: str | None):
    _write_receipt(tmp_path, content)
    monkeypatch.setattr(dashboard_app, "config_projects_root", lambda: tmp_path)
    return client.get("/api/ai-memory/build-status")


def test_build_status_ok(tmp_path, monkeypatch):
    r = _get_build_status(
        tmp_path,
        monkeypatch,
        json.dumps(
            {
                "label": "com.ai-memory.weekly-graph-build",
                "started_at": "2026-09-21T14:48:22Z",
                "finished_at": "2026-09-21T17:17:35Z",
                "exit_status": 0,
                "invocation": "scheduled",
            }
        ),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["state"] == "ok"
    assert data["exit_status"] == 0
    assert data["started_at"] == "2026-09-21T14:48:22Z"
    assert data["finished_at"] == "2026-09-21T17:17:35Z"
    assert data["invocation"] == "scheduled"
    assert data["schedule"] == "Mondays 10:00"


def test_build_status_failed(tmp_path, monkeypatch):
    r = _get_build_status(
        tmp_path,
        monkeypatch,
        json.dumps(
            {
                "started_at": "2026-09-21T14:48:22Z",
                "finished_at": "2026-09-21T14:48:23Z",
                "exit_status": 1,
                "invocation": "scheduled",
            }
        ),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["state"] == "failed"
    assert data["exit_status"] == 1


def test_build_status_missing_receipt_is_unknown(tmp_path, monkeypatch):
    r = _get_build_status(tmp_path, monkeypatch, None)
    assert r.status_code == 200
    data = r.json()
    assert data["state"] == "unknown"
    assert data["started_at"] is None
    assert data["finished_at"] is None
    assert data["exit_status"] is None
    assert data["schedule"] == "Mondays 10:00"


def test_build_status_invalid_json_is_unknown(tmp_path, monkeypatch):
    r = _get_build_status(tmp_path, monkeypatch, "not valid json {")
    assert r.status_code == 200
    data = r.json()
    assert data["state"] == "unknown"


def test_build_status_invalid_shape_is_unknown(tmp_path, monkeypatch):
    r = _get_build_status(
        tmp_path,
        monkeypatch,
        json.dumps({"started_at": "2026-09-21T14:48:22Z"}),  # no exit_status
    )
    assert r.status_code == 200
    data = r.json()
    assert data["state"] == "unknown"


def test_rebuild_endpoint_is_gone(brain_db):
    assert client.post("/api/ai-memory/rebuild").status_code == 404
    assert client.get("/api/ai-memory/rebuild").status_code == 404


def test_no_rebuild_references_remain():
    scanned = [REPO_ROOT / "dashboard" / "app.py"]
    scanned.extend(sorted((REPO_ROOT / "dashboard" / "static").glob("*.js")))
    scanned.extend(sorted((REPO_ROOT / "dashboard" / "templates").glob("*.html")))
    for pattern in ("/api/ai-memory/rebuild", "rebuildAiMemoryGraph"):
        offenders = [p for p in scanned if pattern in p.read_text()]
        assert not offenders, f"{pattern!r} still referenced in {offenders}"
