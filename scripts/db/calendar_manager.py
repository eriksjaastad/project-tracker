"""
Calendar Manager — AI-first calendar for project-tracker.

Design philosophy:
- Every field is optional except title + date (minimal barrier to entry)
- Agents can do everything humans can, plus poll for reminders via JSON
- Flexible: add new event types / fields without breaking existing rows
- Cron jobs are surfaced alongside events (they're scheduled too)
- Extensible metadata field for future fields (dict stored as JSON)
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    # Deserialize metadata JSON if present — warn on corruption, don't silently swallow
    if d.get("metadata") and isinstance(d["metadata"], str):
        try:
            d["metadata"] = json.loads(d["metadata"])
        except (json.JSONDecodeError, TypeError) as exc:
            import warnings
            warnings.warn(
                f"calendar_events row {d.get('id')}: corrupted metadata JSON ({exc}). "
                "Resetting to empty dict.",
                stacklevel=2,
            )
            d["metadata"] = {}
    return d


VALID_EVENT_TYPES = {"reminder", "deadline", "milestone", "meeting", "recurring"}
VALID_RECURRENCE = {None, "daily", "weekly", "monthly"}


def validate_event_type(event_type: str) -> tuple[bool, str]:
    if event_type not in VALID_EVENT_TYPES:
        return False, f"Invalid event_type '{event_type}'. Must be one of: {', '.join(sorted(VALID_EVENT_TYPES))}"
    return True, ""



# ---------------------------------------------------------------------------
# CalendarManager
# ---------------------------------------------------------------------------

class CalendarManager:
    """Manages calendar_events, calendar_event_tasks, and surfaces cron_jobs.

    Designed to be used standalone OR via an existing db_path.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        if db_path is None:
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent.parent))
            try:
                from scripts.config import DATABASE_PATH
                db_path = DATABASE_PATH
            except ImportError:
                db_path = Path("data/tracker.db")
        self.db_path = Path(db_path)

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    def ensure_tables(self) -> None:
        """Create calendar tables if they don't exist. Safe to call repeatedly."""
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS calendar_events (
                    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                    title                 TEXT    NOT NULL,
                    description           TEXT,
                    event_date            TEXT    NOT NULL,
                    event_time            TEXT,
                    event_type            TEXT    NOT NULL DEFAULT 'reminder',
                    recurrence            TEXT,
                    project_id            TEXT    REFERENCES projects(id) ON DELETE SET NULL,
                    machine               TEXT,
                    prompt                TEXT,
                    notify_before_minutes INTEGER NOT NULL DEFAULT 60,
                    notified_at           TEXT,
                    status                TEXT    NOT NULL DEFAULT 'active',
                    created_by            TEXT,
                    metadata              TEXT    DEFAULT '{}',
                    created_at            TEXT    NOT NULL,
                    updated_at            TEXT    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS calendar_event_tasks (
                    event_id  INTEGER NOT NULL REFERENCES calendar_events(id) ON DELETE CASCADE,
                    task_id   INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    link_type TEXT    NOT NULL DEFAULT 'related',
                    PRIMARY KEY (event_id, task_id)
                );

                CREATE INDEX IF NOT EXISTS idx_cal_date       ON calendar_events(event_date);
                CREATE INDEX IF NOT EXISTS idx_cal_project    ON calendar_events(project_id);
                CREATE INDEX IF NOT EXISTS idx_cal_status     ON calendar_events(status);
                CREATE INDEX IF NOT EXISTS idx_cal_machine    ON calendar_events(machine);
            """)
            conn.commit()

    # ------------------------------------------------------------------
    # Write — events
    # ------------------------------------------------------------------

    def add_event(
        self,
        title: str,
        event_date: str,
        *,
        description: Optional[str] = None,
        event_time: Optional[str] = None,
        event_type: str = "reminder",
        recurrence: Optional[str] = None,
        project_id: Optional[str] = None,
        prompt: Optional[str] = None,
        notify_before_minutes: int = 60,
        created_by: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Add a calendar event. Returns the new event ID."""
        ok, err = validate_event_type(event_type)
        if not ok:
            raise ValueError(err)
        if recurrence not in VALID_RECURRENCE:
            raise ValueError(f"Invalid recurrence '{recurrence}'. Must be one of: daily, weekly, monthly, or null")

        now = _now()
        with self._conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO calendar_events
                    (title, description, event_date, event_time, event_type, recurrence,
                     project_id, prompt, notify_before_minutes,
                     created_by, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title, description, event_date, event_time, event_type, recurrence,
                    project_id, prompt, notify_before_minutes,
                    created_by, json.dumps(metadata or {}), now, now,
                ),
            )
            conn.commit()
            return cursor.lastrowid  # type: ignore[return-value]

    def update_event(self, event_id: int, **updates: Any) -> bool:
        """Update any fields on an event. Returns True if event was found."""
        allowed = {
            "title", "description", "event_date", "event_time", "event_type",
            "recurrence", "project_id", "machine", "prompt", "notify_before_minutes",
            "notified_at", "status", "created_by", "metadata",
        }
        bad = set(updates) - allowed
        if bad:
            raise ValueError(f"Unknown field(s): {bad}")
        if not updates:
            return True

        if "event_type" in updates:
            ok, err = validate_event_type(updates["event_type"])
            if not ok:
                raise ValueError(err)
        if "metadata" in updates and isinstance(updates["metadata"], dict):
            updates["metadata"] = json.dumps(updates["metadata"])

        updates["updated_at"] = _now()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [event_id]

        with self._conn() as conn:
            cursor = conn.execute(
                f"UPDATE calendar_events SET {set_clause} WHERE id = ?", values
            )
            conn.commit()
            return cursor.rowcount > 0

    def mark_done(self, event_id: int) -> bool:
        return self.update_event(event_id, status="done")

    def cancel_event(self, event_id: int) -> bool:
        return self.update_event(event_id, status="cancelled")

    def link_task(self, event_id: int, task_id: int, link_type: str = "related") -> None:
        """Link a task to an event (bidirectional via join table)."""
        valid_link_types = {"related", "deadline-for", "blocks"}
        if link_type not in valid_link_types:
            raise ValueError(f"link_type must be one of: {valid_link_types}")
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO calendar_event_tasks (event_id, task_id, link_type) VALUES (?, ?, ?)",
                (event_id, task_id, link_type),
            )
            conn.commit()

    def unlink_task(self, event_id: int, task_id: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM calendar_event_tasks WHERE event_id = ? AND task_id = ?",
                (event_id, task_id),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Read — events
    # ------------------------------------------------------------------

    def get_event(self, event_id: int) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM calendar_events WHERE id = ?", (event_id,)
            ).fetchone()
        if row is None:
            return None
        event = _row_to_dict(row)
        event["linked_tasks"] = self._get_linked_tasks(event_id)
        return event

    def get_events(
        self,
        *,
        days: int = 7,
        from_date: Optional[str] = None,
        project_id: Optional[str] = None,
        machine: Optional[str] = None,
        event_type: Optional[str] = None,
        status: str = "active",
        include_all: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get events. Defaults to next N days. Pass include_all=True to ignore date window."""
        query = "SELECT * FROM calendar_events WHERE 1=1"
        params: list = []

        if not include_all:
            from datetime import timedelta
            start = from_date or datetime.now(timezone.utc).date().isoformat()
            end_date = (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()
            query += " AND event_date >= ? AND event_date <= ?"
            params += [start, end_date]

        if status and not include_all:
            query += " AND status = ?"
            params.append(status)

        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        if machine:
            query += " AND machine = ?"
            params.append(machine)

        query += " ORDER BY event_date ASC, event_time ASC NULLS LAST"

        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_upcoming_reminders(
        self, within_minutes: int = 60,
    ) -> List[Dict[str, Any]]:
        """Return events whose notification window is now open and haven't been notified yet.

        Timezone note: event_date and event_time are stored as user-entered local wall-clock
        values (no TZ info). We do a date-only comparison for all-day events and strip
        timezone info for time comparisons to avoid UTC-vs-local drift.
        """
        from datetime import timedelta

        now_dt = datetime.now(timezone.utc)
        window_end = now_dt + timedelta(minutes=within_minutes)
        # Use naive ISO strings for SQLite datetime() comparison — SQLite has no TZ support
        now_naive = now_dt.strftime("%Y-%m-%dT%H:%M:%S")
        end_naive = window_end.strftime("%Y-%m-%dT%H:%M:%S")
        today = now_dt.date().isoformat()
        end_date = window_end.date().isoformat()

        query = """
            SELECT * FROM calendar_events
            WHERE status = 'active'
              AND notified_at IS NULL
              AND (
                -- Events with a specific time: compare datetime values (naive, wall-clock)
                (event_time IS NOT NULL
                 AND datetime(event_date || 'T' || event_time)
                     BETWEEN datetime(?) AND datetime(?))
                OR
                -- All-day events: fire if the event date falls in the window's date range
                (event_time IS NULL
                 AND event_date BETWEEN ? AND ?)
              )
        """
        params: list = [now_naive, end_naive, today, end_date]

        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_dict(r) for r in rows]

    def _get_linked_tasks(self, event_id: int) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT t.id, t.text, t.status, t.priority, t.project_id, cet.link_type
                FROM tasks t
                JOIN calendar_event_tasks cet ON cet.task_id = t.id
                WHERE cet.event_id = ?
                ORDER BY t.id
                """,
                (event_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_events_for_task(self, task_id: int) -> List[Dict[str, Any]]:
        """Get all calendar events linked to a specific task."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT ce.*, cet.link_type
                FROM calendar_events ce
                JOIN calendar_event_tasks cet ON cet.event_id = ce.id
                WHERE cet.task_id = ?
                ORDER BY ce.event_date ASC
                """,
                (task_id,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def mark_notified(self, event_id: int) -> None:
        self.update_event(event_id, notified_at=_now())

    def reset_notify(self, event_id: int) -> None:
        self.update_event(event_id, notified_at=None)

    # ------------------------------------------------------------------
    # Cron jobs — surface existing jobs alongside calendar events
    # ------------------------------------------------------------------

    def get_cron_jobs(
        self,
        *,
        project_id: Optional[str] = None,
        active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """Return cron jobs, filtered by project. Shown alongside calendar events."""
        query = "SELECT * FROM cron_jobs WHERE 1=1"
        params: list = []

        if active_only:
            query += " AND is_active = 1"
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)

        query += " ORDER BY project_id, schedule"

        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # iCal export
    # ------------------------------------------------------------------

    def export_ical(
        self,
        *,
        project_id: Optional[str] = None,
        include_all: bool = True,
    ) -> str:
        """Export events as iCal (.ics) format for Apple/Google Calendar import."""
        events = self.get_events(
            project_id=project_id, include_all=include_all
        )

        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//project-tracker//AI Calendar//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
        ]

        for ev in events:
            dt_start = ev["event_date"].replace("-", "")
            if ev.get("event_time"):
                dt_start += "T" + ev["event_time"].replace(":", "") + "00"
            uid = f"pt-cal-{ev['id']}@project-tracker"
            summary = ev["title"].replace("\n", " ")
            desc_parts = []
            if ev.get("description"):
                desc_parts.append(ev["description"])
            if ev.get("prompt"):
                desc_parts.append(f"[Agent prompt] {ev['prompt']}")
            description = "\\n".join(desc_parts) if desc_parts else ""

            lines += [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"SUMMARY:{summary}",
                f"DTSTART:{dt_start}" if "T" in dt_start else f"DTSTART;VALUE=DATE:{dt_start}",
                f"CATEGORIES:{ev.get('event_type', 'reminder').upper()}",
            ]
            if description:
                lines.append(f"DESCRIPTION:{description}")
            if ev.get("project_id"):
                lines.append(f"COMMENT:Project: {ev['project_id']}")
            lines.append("END:VEVENT")

        lines.append("END:VCALENDAR")
        return "\r\n".join(lines) + "\r\n"
