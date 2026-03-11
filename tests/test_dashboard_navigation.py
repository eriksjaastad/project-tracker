from fastapi.testclient import TestClient

from dashboard.app import app, build_navigation


client = TestClient(app)


def test_root_redirects_to_dashboard():
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/dashboard"


def test_navigation_api_returns_shared_contract():
    response = client.get("/api/navigation")

    assert response.status_code == 200

    payload = response.json()
    assert payload["title"] == "Project Tracker"
    assert [item["id"] for item in payload["items"]] == [
        "dashboard",
        "kanban",
        "agentic",
        "graph",
    ]
    assert payload["items"][0]["href"] == "/dashboard"
    assert payload["items"][1]["navigation_type"] == "spa"


def test_build_navigation_marks_expected_active_items():
    project_navigation = build_navigation("/project/project-tracker")
    kanban_navigation = build_navigation("/kanban/project-tracker")

    assert next(item for item in project_navigation if item["id"] == "dashboard")["active"] is True
    assert next(item for item in project_navigation if item["id"] == "kanban")["active"] is False
    assert next(item for item in kanban_navigation if item["id"] == "kanban")["active"] is True


def test_graph_view_renders_shared_shell_navigation():
    response = client.get("/graph")

    assert response.status_code == 200
    body = response.text
    assert "Project Tracker" in body
    assert "Dashboard" in body
    assert "Kanban" in body
    assert "Agentic" in body
    assert "Graph" in body
    assert "Knowledge Graph" in body