"""Calendar manager and dashboard calendar endpoints (#7899).

The dashboard's create and remind endpoints once passed a `machine` argument
the manager no longer accepted, so they 500ed before reaching the database.
These tests cover that path plus plain create / done / link writes.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import dashboard.app as dashboard_app  # noqa: E402
from db.backend_calendar_manager import CalendarManager  # noqa: E402
from db.manager import DatabaseManager  # noqa: E402
from db.schema import create_database  # noqa: E402


def test_calendar_writes_create_done_and_link(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.db"
    create_database(db_path)
    cm = CalendarManager(db_path)
    cm.ensure_tables()

    event_id = cm.add_event(title="Review", event_date="2030-01-01")
    assert cm.mark_done(event_id) is True
    assert cm.get_event(event_id)["status"] == "done"

    db = DatabaseManager(db_path)
    db.add_project(project_id="p", name="P", path=str(tmp_path / "p"), status="active")
    task = db.add_task("Linked card", "p", notes="- [ ] linked")
    cm.link_task(event_id, task["id"])
    assert [t["id"] for t in cm.get_event(event_id)["linked_tasks"]] == [task["id"]]


def test_upcoming_reminders_filter_by_machine(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.db"
    create_database(db_path)
    cm = CalendarManager(db_path)
    cm.ensure_tables()
    # get_upcoming_reminders() compares against the UTC date; a local date is
    # "yesterday" to it between UTC midnight and local midnight west of UTC.
    today = datetime.now(timezone.utc).date().isoformat()
    mine = cm.add_event(title="Mine", event_date=today, machine="MacBook")
    other = cm.add_event(title="Other", event_date=today, machine="Mac Mini")

    assert {e["id"] for e in cm.get_upcoming_reminders(machine="MacBook")} == {mine}
    assert {e["id"] for e in cm.get_upcoming_reminders()} == {mine, other}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "tracker.db"
    create_database(db_path)
    monkeypatch.setenv("PT_DB_PATH", str(db_path))
    return TestClient(dashboard_app.app)


@pytest.mark.parametrize("machine", [None, "MacBook"])
def test_create_event_endpoint_succeeds(client: TestClient, machine) -> None:
    payload = {"title": "Ship it", "event_date": "2030-01-01"}
    if machine:
        payload["machine"] = machine
    resp = client.post("/api/calendar/events", json=payload)
    assert resp.status_code == 200, resp.text
    event_id = resp.json()["id"]
    detail = client.get(f"/api/calendar/events/{event_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["machine"] == machine

    done = client.patch(f"/api/calendar/events/{event_id}/done")
    assert done.status_code == 200, done.text


@pytest.mark.parametrize("query", ["", "?machine=MacBook"])
def test_remind_endpoint_succeeds(client: TestClient, query: str) -> None:
    resp = client.get(f"/api/calendar/remind{query}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == len(resp.json()["events"])
