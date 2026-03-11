"""Tests for /api/agentic/summary."""

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import dashboard.app as dashboard_app
from db.manager import DatabaseManager
from db.schema import create_database


def _setup_db(tmp_path: Path) -> tuple[Path, DatabaseManager, dict[str, int]]:
    db_path = tmp_path / "test.db"
    create_database(db_path)
    db = DatabaseManager(db_path=db_path)
    task_ids: dict[str, int] = {}

    for project_id in ("project-tracker", "image-workflow"):
        db.add_project(
            project_id=project_id,
            name=project_id,
            path=f"./{project_id}",
            status="active",
        )
        task = db.add_task(text=f"{project_id} task", project_id=project_id, status="Review")
        task_ids[project_id] = task["id"]

    return db_path, db, task_ids


def _insert_history(
    db: DatabaseManager, task_id: int, project_id: str, rows: list[tuple[str, str, str]]
) -> None:
    with db._get_conn() as conn:
        cursor = conn.cursor()
        cursor.executemany(
            """
            INSERT INTO task_history (task_id, project_id, event_type, old_status, new_status, timestamp)
            VALUES (?, ?, 'status_changed', ?, ?, ?)
            """,
            [(task_id, project_id, old_status, new_status, timestamp) for timestamp, old_status, new_status in rows],
        )
        conn.commit()


def _freeze_now(monkeypatch: pytest.MonkeyPatch, frozen_now: datetime) -> None:
    class FrozenDateTime:
        @classmethod
        def now(cls) -> datetime:
            return frozen_now

    monkeypatch.setattr(dashboard_app, "datetime", FrozenDateTime)


def _patch_markers(monkeypatch: pytest.MonkeyPatch, content: str | None) -> None:
    real_exists = dashboard_app.Path.exists
    real_read_text = dashboard_app.Path.read_text

    def fake_exists(self: Path) -> bool:
        if self.name == "agentic_markers.json":
            return content is not None
        return real_exists(self)

    def fake_read_text(self: Path, *args, **kwargs) -> str:
        if self.name == "agentic_markers.json":
            return content or ""
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(dashboard_app.Path, "exists", fake_exists)
    monkeypatch.setattr(dashboard_app.Path, "read_text", fake_read_text)


def test_agentic_summary_aggregates_rates_series_and_markers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path, db, task_ids = _setup_db(tmp_path)
    monkeypatch.setenv("PT_DB_PATH", str(db_path))
    _freeze_now(monkeypatch, datetime(2026, 3, 10, 12, 0, 0))
    _patch_markers(
        monkeypatch,
        json.dumps([
            {"date": "2026-03-08", "label": "Workflow change"},
            {"date": "2026-02-20", "label": "Out of range"},
            {"date": "2026-03-09"},
        ]),
    )

    _insert_history(db, task_ids["project-tracker"], "project-tracker", [
        ("2026-03-08 09:00:00", "Review", "In Progress"),
        ("2026-03-08 10:00:00", "Review", "Done"),
        ("2026-03-08 11:00:00", "In Progress", "Review"),
        ("2026-03-10 14:00:00", "Review", "In Progress"),
        ("2026-03-01 08:00:00", "Review", "In Progress"),
    ])

    response = TestClient(dashboard_app.app).get("/api/agentic/summary?days=3")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["summary"] == {
        "review_bounces": 2,
        "review_promotions": 1,
        "review_entries": 1,
        "bounce_rate": pytest.approx(2 / 3),
        "promotion_rate": pytest.approx(1 / 3),
    }
    assert payload["series"] == [
        {"date": "2026-03-08", "review_bounces": 1, "review_promotions": 1, "review_entries": 1},
        {"date": "2026-03-09", "review_bounces": 0, "review_promotions": 0, "review_entries": 0},
        {"date": "2026-03-10", "review_bounces": 1, "review_promotions": 0, "review_entries": 0},
    ]
    assert payload["markers"] == [{"date": "2026-03-08", "label": "Workflow change"}]
    assert payload["date_range"] == {"start": "2026-03-08", "end": "2026-03-10"}


def test_agentic_summary_filters_by_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path, db, task_ids = _setup_db(tmp_path)
    monkeypatch.setenv("PT_DB_PATH", str(db_path))
    _freeze_now(monkeypatch, datetime(2026, 3, 10, 12, 0, 0))
    _patch_markers(monkeypatch, None)

    _insert_history(db, task_ids["project-tracker"], "project-tracker", [
        ("2026-03-10 09:00:00", "Review", "In Progress"),
        ("2026-03-10 10:00:00", "Review", "Done"),
    ])
    _insert_history(db, task_ids["image-workflow"], "image-workflow", [
        ("2026-03-10 11:00:00", "Review", "In Progress"),
        ("2026-03-10 12:00:00", "In Progress", "Review"),
    ])

    response = TestClient(dashboard_app.app).get("/api/agentic/summary?days=1&project_id=project-tracker")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == "project-tracker"
    assert payload["summary"]["review_bounces"] == 1
    assert payload["summary"]["review_promotions"] == 1
    assert payload["summary"]["review_entries"] == 0


def test_agentic_summary_handles_invalid_days_and_malformed_markers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path, _, _ = _setup_db(tmp_path)
    monkeypatch.setenv("PT_DB_PATH", str(db_path))
    _freeze_now(monkeypatch, datetime(2026, 3, 10, 12, 0, 0))
    _patch_markers(monkeypatch, "{not-json")

    response = TestClient(dashboard_app.app).get("/api/agentic/summary?days=0")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["summary"] == {
        "review_bounces": 0,
        "review_promotions": 0,
        "review_entries": 0,
        "bounce_rate": 0.0,
        "promotion_rate": 0.0,
    }
    assert payload["markers"] == []
    assert payload["date_range"] == {"start": "2026-02-09", "end": "2026-03-10"}
    assert len(payload["series"]) == 30