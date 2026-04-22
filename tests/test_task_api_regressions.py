"""Regression tests for task API behavior."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import dashboard.app as dashboard_app
from db.manager import DatabaseManager
from db.schema import create_database


def _setup_db(tmp_path: Path) -> tuple[Path, DatabaseManager]:
    db_path = tmp_path / "test.db"
    create_database(db_path)
    db = DatabaseManager(db_path=db_path)
    db.add_project(
        project_id="project-tracker",
        name="Project Tracker",
        path=str(tmp_path / "project-tracker"),
        status="active",
    )
    return db_path, db


def test_list_tasks_honors_status_query_param(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path, db = _setup_db(tmp_path)
    monkeypatch.setenv("PT_DB_PATH", str(db_path))

    done_task = db.add_task("Done task", "project-tracker", status="Done")
    db.add_task("Open task", "project-tracker", status="Backlog")

    response = TestClient(dashboard_app.app).get("/api/tasks?status=Done")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 1
    assert [task["id"] for task in payload["tasks"]] == [done_task["id"]]
