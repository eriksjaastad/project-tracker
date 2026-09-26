"""Tests for /api/agentic/markers and the shared markers loader.

The markers file is a gitignored JSON list. A missing file is a valid empty
state, but a present-and-unreadable file must never be treated as empty:
the next POST would otherwise overwrite every marker in it (#7586).
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import dashboard.app as dashboard_app
from fastapi.testclient import TestClient


@pytest.fixture
def markers_file(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "agentic_markers.json"
    monkeypatch.setattr(dashboard_app, "MARKERS_PATH", path)
    return path


def test_get_markers_missing_file_returns_empty_list(markers_file: Path):
    response = TestClient(dashboard_app.app).get("/api/agentic/markers")

    assert response.status_code == 200, response.text
    assert response.json() == {"markers": []}


def test_get_markers_corrupt_json_returns_503_with_detail(markers_file: Path):
    markers_file.write_text("{not-json")

    response = TestClient(dashboard_app.app).get("/api/agentic/markers")

    assert response.status_code == 503, response.text
    detail = response.json()["detail"]
    assert str(markers_file) in detail
    assert "invalid JSON" in detail


def test_get_markers_non_list_json_returns_503(markers_file: Path):
    markers_file.write_text(json.dumps({"date": "2026-03-10", "label": "not a list"}))

    response = TestClient(dashboard_app.app).get("/api/agentic/markers")

    assert response.status_code == 503, response.text
    detail = response.json()["detail"]
    assert str(markers_file) in detail
    assert "not a list" in detail


def test_get_markers_invalid_utf8_returns_503_with_detail(markers_file: Path):
    invalid = b"\xff\xfe["
    markers_file.write_bytes(invalid)

    response = TestClient(dashboard_app.app).get("/api/agentic/markers")

    assert response.status_code == 503, response.text
    detail = response.json()["detail"]
    assert str(markers_file) in detail
    assert "not valid UTF-8" in detail


def test_post_with_invalid_utf8_file_returns_503_and_leaves_file_unchanged(markers_file: Path):
    invalid = b"\xff\xfe["
    markers_file.write_bytes(invalid)

    response = TestClient(dashboard_app.app).post(
        "/api/agentic/markers",
        json={"date": "2026-03-10", "label": "Would erase everything"},
    )

    assert response.status_code == 503, response.text
    assert markers_file.read_bytes() == invalid


def test_post_with_corrupt_file_returns_503_and_leaves_file_unchanged(markers_file: Path):
    corrupt = b'{"markers": ['
    markers_file.write_bytes(corrupt)

    response = TestClient(dashboard_app.app).post(
        "/api/agentic/markers",
        json={"date": "2026-03-10", "label": "Would erase everything"},
    )

    assert response.status_code == 503, response.text
    assert markers_file.read_bytes() == corrupt


def test_patch_with_corrupt_file_returns_503_and_leaves_file_unchanged(markers_file: Path):
    corrupt = b'{"markers": ['
    markers_file.write_bytes(corrupt)

    response = TestClient(dashboard_app.app).patch(
        "/api/agentic/markers/some-id",
        json={"label": "Would erase everything"},
    )

    assert response.status_code == 503, response.text
    assert markers_file.read_bytes() == corrupt


def test_delete_with_corrupt_file_returns_503_and_leaves_file_unchanged(markers_file: Path):
    corrupt = b'{"markers": ['
    markers_file.write_bytes(corrupt)

    response = TestClient(dashboard_app.app).delete("/api/agentic/markers/some-id")

    assert response.status_code == 503, response.text
    assert markers_file.read_bytes() == corrupt


def test_marker_crud_round_trip(markers_file: Path):
    client = TestClient(dashboard_app.app)

    # Missing file -> empty list, no error.
    assert client.get("/api/agentic/markers").json() == {"markers": []}

    # Create.
    response = client.post(
        "/api/agentic/markers",
        json={"date": "2026-03-10", "label": "Workflow change"},
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["date"] == "2026-03-10"
    assert created["label"] == "Workflow change"
    assert created["source"] == "manual"
    marker_id = created["id"]

    # Listed and persisted.
    listed = client.get("/api/agentic/markers").json()["markers"]
    assert [m["id"] for m in listed] == [marker_id]

    # Update.
    response = client.patch(
        f"/api/agentic/markers/{marker_id}",
        json={"label": "Workflow change (updated)"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["label"] == "Workflow change (updated)"

    # Delete.
    response = client.delete(f"/api/agentic/markers/{marker_id}")
    assert response.status_code == 204, response.text
    assert client.get("/api/agentic/markers").json() == {"markers": []}
