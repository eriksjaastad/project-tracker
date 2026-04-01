"""Tests for agent config health surfacing."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import dashboard.app as dashboard_app
from db.manager import DatabaseManager
from db.schema import create_database
from discovery import alert_detector


def test_get_all_alerts_includes_agent_config_health_warning(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    project_path = tmp_path / "sample-project"
    project_path.mkdir()
    (project_path / "CLAUDE.md").write_text("\n".join([f"- rule {i}" for i in range(205)]) + "\n")

    for detector_name in (
        "detect_telemetry_errors",
        "detect_stale_cron_heartbeats",
        "detect_blocked_projects",
        "detect_code_reviews",
        "detect_cron_failures",
        "detect_stalled_projects",
        "detect_missing_index",
    ):
        monkeypatch.setattr(alert_detector, detector_name, lambda *args, **kwargs: [])

    alerts = alert_detector.get_all_alerts([
        {"id": "sample-project", "name": "sample-project", "path": str(project_path)}
    ])

    assert alerts == [
        {
            "project_id": "sample-project",
            "project_name": "sample-project",
            "type": "agent_config_health",
            "severity": "warning",
            "message": "CLAUDE.md: 205 lines (limit: 200)",
            "details": "CLAUDE.md: 205 lines (limit: 200)",
        }
    ]


def test_api_projects_include_agent_config_health(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "test.db"
    create_database(db_path)
    monkeypatch.setenv("PT_DB_PATH", str(db_path))
    project_path = tmp_path / "sample-project"
    project_path.mkdir()
    (project_path / "CLAUDE.md").write_text("\n".join([f"- rule {i}" for i in range(205)]) + "\n")

    db = DatabaseManager(db_path=db_path)
    db.add_project(
        project_id="sample-project",
        name="sample-project",
        path=str(project_path),
        status="active",
    )

    response = TestClient(dashboard_app.app).get("/api/projects")

    assert response.status_code == 200, response.text
    project = response.json()["projects"][0]
    assert project["agent_config_health"]["has_claude_md"] is True
    assert project["agent_config_health"]["warning_count"] == 1
    assert next(
        file_health for file_health in project["agent_config_health"]["files"] if file_health["path"] == "CLAUDE.md"
    )["warnings"] == ["205 lines (limit: 200)"]


def test_api_alerts_include_agent_config_health(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "test.db"
    create_database(db_path)
    monkeypatch.setenv("PT_DB_PATH", str(db_path))
    project_path = tmp_path / "sample-project"
    project_path.mkdir()
    (project_path / "CLAUDE.md").write_text("\n".join([f"- rule {i}" for i in range(205)]) + "\n")
    (project_path / "00_Index_sample-project.md").write_text("# Index\n")

    db = DatabaseManager(db_path=db_path)
    db.add_project(
        project_id="sample-project",
        name="sample-project",
        path=str(project_path),
        status="active",
        has_index=True,
    )

    for detector_name in (
        "detect_telemetry_errors",
        "detect_stale_cron_heartbeats",
        "detect_blocked_projects",
        "detect_code_reviews",
        "detect_cron_failures",
        "detect_stalled_projects",
        "detect_missing_index",
    ):
        monkeypatch.setattr(alert_detector, detector_name, lambda *args, **kwargs: [])

    response = TestClient(dashboard_app.app).get("/api/alerts")

    assert response.status_code == 200, response.text
    assert response.json()["alerts"] == [
        {
            "project_id": "sample-project",
            "project_name": "sample-project",
            "type": "agent_config_health",
            "severity": "warning",
            "message": "CLAUDE.md: 205 lines (limit: 200)",
            "details": "CLAUDE.md: 205 lines (limit: 200)",
        }
    ]


def test_api_task_policy_and_project_card_flags(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "test.db"
    create_database(db_path)
    monkeypatch.setenv("PT_DB_PATH", str(db_path))
    blocked_path = tmp_path / "project-tracker"
    blocked_path.mkdir()
    allowed_path = tmp_path / "smart-invoice-workflow"
    allowed_path.mkdir()

    db = DatabaseManager(db_path=db_path)
    db.add_project(
        project_id="project-tracker",
        name="Project Tracker",
        path=str(blocked_path),
        status="active",
    )
    db.add_project(
        project_id="smart-invoice-workflow",
        name="Smart Invoice Workflow",
        path=str(allowed_path),
        status="active",
    )

    client = TestClient(dashboard_app.app)

    # With Mac Mini disconnected, no projects are blocked
    policy_response = client.get("/api/task-policy")
    assert policy_response.status_code == 200, policy_response.text
    policy = policy_response.json()
    assert policy["blocked_project_ids"] == []

    projects_response = client.get("/api/projects")
    assert projects_response.status_code == 200, projects_response.text
    projects = {project["id"]: project for project in projects_response.json()["projects"]}
    assert projects["project-tracker"]["can_create_cards"] is True
    assert projects["project-tracker"]["blocked_card_reason"] is None
    assert projects["smart-invoice-workflow"]["can_create_cards"] is True
    assert projects["smart-invoice-workflow"]["blocked_card_reason"] is None
