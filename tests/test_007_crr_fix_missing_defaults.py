"""Tests for migration 007 — add DEFAULT '' to tasks/calendar_events timestamps."""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO / "scripts"))

_MIGRATION_PATH = REPO / "scripts" / "db" / "migrations" / "007_crr_fix_missing_defaults.py"
_spec = importlib.util.spec_from_file_location("_m007", _MIGRATION_PATH)
assert _spec and _spec.loader
_m007 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m007)  # type: ignore[union-attr]
up = _m007.up


def _db_with_broken_defaults(tmp_path: Path) -> sqlite3.Connection:
    """tasks and calendar_events with NOT NULL but no DEFAULT — the Mini-failure schema."""
    conn = sqlite3.connect(str(tmp_path / "tracker.db"))
    conn.executescript("""
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY NOT NULL,
            text TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Backlog',
            project_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            parent_id INTEGER,
            blocked_by TEXT
        );
        CREATE TABLE calendar_events (
            id INTEGER PRIMARY KEY NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            event_date TEXT NOT NULL DEFAULT '',
            project_id TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            machine TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        INSERT INTO tasks (id, text, status, project_id, created_at, updated_at)
            VALUES (1, 'task one', 'Backlog', 'p1', '2026-01-01', '2026-01-01');
        INSERT INTO calendar_events (id, title, event_date, created_at, updated_at)
            VALUES (1, 'event one', '2026-06-01', '2026-01-01', '2026-01-01');
    """)
    conn.commit()
    return conn


def _db_already_compliant(tmp_path: Path) -> sqlite3.Connection:
    """tasks and calendar_events already have DEFAULT '' — migration should no-op."""
    conn = sqlite3.connect(str(tmp_path / "tracker.db"))
    conn.executescript("""
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY NOT NULL,
            text TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            completed_at TEXT,
            parent_id INTEGER,
            blocked_by TEXT
        );
        CREATE TABLE calendar_events (
            id INTEGER PRIMARY KEY NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            event_date TEXT NOT NULL DEFAULT '',
            project_id TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            machine TEXT,
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT ''
        );
        INSERT INTO tasks (id, text, created_at, updated_at)
            VALUES (1, 'task one', '2026-01-01', '2026-01-01');
        INSERT INTO calendar_events (id, title, event_date, created_at, updated_at)
            VALUES (1, 'event', '2026-06-01', '2026-01-01', '2026-01-01');
    """)
    conn.commit()
    return conn


def _get_col_defaults(conn: sqlite3.Connection, tbl: str) -> dict[str, str | None]:
    return {r[1]: r[4] for r in conn.execute(f"PRAGMA table_info({tbl})").fetchall()}


def test_defaults_added_to_broken_schema(tmp_path: Path) -> None:
    conn = _db_with_broken_defaults(tmp_path)
    conn.execute("BEGIN")
    up(conn)
    conn.execute("COMMIT")

    defaults = _get_col_defaults(conn, "tasks")
    assert defaults["created_at"] == "''", f"tasks.created_at DEFAULT: {defaults['created_at']!r}"
    assert defaults["updated_at"] == "''", f"tasks.updated_at DEFAULT: {defaults['updated_at']!r}"

    defaults = _get_col_defaults(conn, "calendar_events")
    assert defaults["created_at"] == "''", f"calendar_events.created_at DEFAULT: {defaults['created_at']!r}"
    assert defaults["updated_at"] == "''", f"calendar_events.updated_at DEFAULT: {defaults['updated_at']!r}"


def test_row_counts_preserved(tmp_path: Path) -> None:
    conn = _db_with_broken_defaults(tmp_path)
    conn.execute("BEGIN")
    up(conn)
    conn.execute("COMMIT")

    assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM calendar_events").fetchone()[0] == 1


def test_row_values_preserved(tmp_path: Path) -> None:
    conn = _db_with_broken_defaults(tmp_path)
    conn.execute("BEGIN")
    up(conn)
    conn.execute("COMMIT")

    row = conn.execute("SELECT text, created_at FROM tasks WHERE id=1").fetchone()
    assert row[0] == "task one"
    assert row[1] == "2026-01-01"


def test_integrity_check_passes(tmp_path: Path) -> None:
    conn = _db_with_broken_defaults(tmp_path)
    conn.execute("BEGIN")
    up(conn)
    conn.execute("COMMIT")
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_no_op_when_already_compliant(tmp_path: Path) -> None:
    """Migration must skip entirely when columns already have DEFAULT values."""
    conn = _db_already_compliant(tmp_path)

    before_tasks = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    before_cal = conn.execute("SELECT COUNT(*) FROM calendar_events").fetchone()[0]

    conn.execute("BEGIN")
    up(conn)
    conn.execute("COMMIT")

    # Row counts unchanged
    assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == before_tasks
    assert conn.execute("SELECT COUNT(*) FROM calendar_events").fetchone()[0] == before_cal

    # Columns still have correct defaults
    defaults = _get_col_defaults(conn, "tasks")
    assert defaults["created_at"] == "''"
    assert defaults["updated_at"] == "''"


def test_idempotent(tmp_path: Path) -> None:
    """Running up() twice on a broken schema must be safe — second run is a no-op."""
    conn = _db_with_broken_defaults(tmp_path)

    conn.execute("BEGIN")
    up(conn)
    conn.execute("COMMIT")

    before = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]

    conn.execute("BEGIN")
    up(conn)
    conn.execute("COMMIT")

    assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == before
    defaults = _get_col_defaults(conn, "tasks")
    assert defaults["created_at"] == "''"
