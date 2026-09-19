"""Calendar callers must retain their API across the dbmed boundary."""

import pytest

from db.calendar_manager import CalendarManager
from dbmed.errors import DbmedError, DbUnavailable


def test_calendar_positional_calls_round_trip(db):
    db.add_project("calendar-test", "Calendar test", "/nonexistent/calendar", "active")
    task = db.add_task("linked task", "calendar-test")
    calendar = CalendarManager()
    event_id = calendar.add_event("Reminder", "2026-09-20", project_id="calendar-test")
    assert calendar.get_event(event_id)["title"] == "Reminder"
    calendar.link_task(event_id, task["id"])
    assert [event["id"] for event in calendar.get_events_for_task(task["id"])] == [event_id]
    calendar.mark_notified(event_id)
    assert calendar.get_event(event_id)["notified_at"]
    calendar.unlink_task(event_id, task["id"])
    assert calendar.get_events_for_task(task["id"]) == []
    calendar.mark_done(event_id)
    assert calendar.get_event(event_id)["status"] == "done"


def test_calendar_rejects_duplicate_argument(db):
    with pytest.raises(DbmedError, match="multiple values"):
        CalendarManager().get_event(1, event_id=2)


def test_calendar_does_not_fall_back_when_daemon_is_down(tmp_path, monkeypatch):
    monkeypatch.setenv("DBMED_SOCKET", str(tmp_path / "absent.sock"))
    with pytest.raises(DbUnavailable):
        CalendarManager().get_events()
