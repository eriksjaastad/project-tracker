"""Tests for /api/projects portfolio metadata surfacing."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import dashboard.app as dashboard_app
from db.manager import DatabaseManager
from db.schema import create_database


def test_api_projects_include_portfolio_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "test.db"
    create_database(db_path)
    monkeypatch.setenv("PT_DB_PATH", str(db_path))
    project_path = tmp_path / "smart-invoice-workflow"
    project_path.mkdir()

    db = DatabaseManager(db_path=db_path)
    db.add_project(
        project_id="smart-invoice-workflow",
        name="smart-invoice-workflow",
        path=str(project_path),
        status="active",
    )
    db.set_info("portfolio_group", "AP", project_id="smart-invoice-workflow")
    db.set_info("portfolio_label", "[AP]", project_id="smart-invoice-workflow")
    db.set_info("portfolio_parent", "auxesis-projects", project_id="smart-invoice-workflow")

    response = TestClient(dashboard_app.app).get("/api/projects")

    assert response.status_code == 200, response.text
    projects_by_id = {p["id"]: p for p in response.json()["projects"]}
    project = projects_by_id["smart-invoice-workflow"]
    assert project["portfolio_group"] == "AP"
    assert project["portfolio_label"] == "[AP]"
    assert project["portfolio_parent"] == "auxesis-projects"
