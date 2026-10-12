"""/api/memory-graph reads ai-memory's float32 embedding blobs (ai-memory #8035)."""

from __future__ import annotations

import sqlite3

import numpy as np
from fastapi.testclient import TestClient

import dashboard.app as dashboard_app


def test_memory_graph_decodes_blobs_and_drops_malformed_ones(tmp_path, monkeypatch):
    brain = tmp_path / "ai-memory" / "brain.db"
    brain.parent.mkdir()
    conn = sqlite3.connect(brain)
    conn.execute(
        "CREATE TABLE thoughts (id INTEGER PRIMARY KEY, content TEXT, embedding TEXT,"
        " embedding_blob BLOB, metadata TEXT, created_at TEXT, source_machine TEXT)"
    )
    vector = np.array([1.0, 0.0, 0.0, 0.0], dtype="<f4").tobytes()
    rows = [
        (1, "a", vector, "2026-10-12T00:00:01"),
        (2, "b", vector, "2026-10-12T00:00:02"),
        (3, "torn", vector[:5], "2026-10-12T00:00:03"),  # not whole float32s
        (4, "text", "abcd", "2026-10-12T00:00:04"),  # TEXT, not a BLOB
    ]
    conn.executemany(
        "INSERT INTO thoughts (id, content, embedding_blob, metadata, created_at, source_machine)"
        " VALUES (?, ?, ?, '{}', ?, 'test')",
        rows,
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("PROJECTS_ROOT", str(tmp_path))
    monkeypatch.setitem(dashboard_app._graph_cache, "data", None)

    # The invalid rows are the newest; with room for two nodes the two valid
    # rows must still be the ones selected.
    response = TestClient(dashboard_app.app).get(
        "/api/memory-graph", params={"min_similarity": 0.5, "max_nodes": 2}
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert sorted(node["id"] for node in data["nodes"]) == ["1", "2"]
    assert len(data["edges"]) == 1  # identical vectors connect
