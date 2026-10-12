"""create_database: one creation path (schema.sql), one ledger (schema_migrations)."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from scripts.db import schema
from scripts.db.migration_runner import (
    apply_all,
    discover_migrations,
    unapplied_migrations,
)
from scripts.db.schema_dump import main as schema_dump


def _objects(path: Path) -> list[tuple]:
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute("SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall()


def test_schema_sql_is_current_with_the_migrations():
    """Fails when a migration lands without `make schema`."""
    assert schema_dump(["--check"]) == 0


def test_fresh_database_is_marked_for_exactly_the_migrations_schema_sql_contains(tmp_path):
    db_path = tmp_path / "tracker.db"
    schema.create_database(db_path)
    version = schema._schema_sql_version(schema.SCHEMA_SQL.read_text())
    migrations = discover_migrations(schema.MIGRATIONS_DIR, verbose=False)
    with closing(sqlite3.connect(db_path)) as conn:
        ledger = [row[0] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
        assert ledger == [m.version for m in migrations if m.version <= version]
        assert unapplied_migrations(conn, migrations) == []
        # The ledgers nothing reads are not created any more.
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert not {"schema_version", "schema_migration_announcements"} & tables


def test_fresh_database_has_its_seed_row(tmp_path):
    """Without it every task delete is blocked (block_task_delete reads it)."""
    db_path = tmp_path / "tracker.db"
    schema.create_database(db_path)
    with closing(sqlite3.connect(db_path)) as conn:
        assert conn.execute("SELECT id, enabled FROM _delete_permissions").fetchall() == [(1, 0)]


def test_existing_database_is_never_changed(tmp_path, monkeypatch):
    monkeypatch.setenv("PT_ALLOW_FRESH_DB", "1")
    db_path = tmp_path / "tracker.db"
    schema.create_database(db_path)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("INSERT INTO projects (id, name, path, status) VALUES ('p', 'P', '/p', 'active')")
        conn.execute("DROP INDEX idx_projects_name")  # drift a real database might carry
        conn.commit()
    before = _objects(db_path)
    schema.create_database(db_path)
    assert _objects(db_path) == before
    with closing(sqlite3.connect(db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1


def test_database_without_the_ledger_is_refused_and_left_alone(tmp_path):
    db_path = tmp_path / "old.db"
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, text TEXT)")
        conn.execute("INSERT INTO tasks VALUES ('1', 'keep me')")
        conn.commit()
    before = _objects(db_path)
    with pytest.raises(schema.SafetyError, match="no schema_migrations ledger"):
        schema.create_database(db_path)
    assert _objects(db_path) == before


def test_a_failing_statement_leaves_the_new_database_empty(tmp_path, monkeypatch):
    broken = tmp_path / "schema.sql"
    broken.write_text(
        "-- Migrations: through 002\n"
        "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL);\n"
        "CREATE TABLE first (id INTEGER);\n"
        "CREATE TABLE first (id INTEGER);\n"
    )
    monkeypatch.setattr(schema, "SCHEMA_SQL", broken)
    db_path = tmp_path / "tracker.db"
    with pytest.raises(sqlite3.OperationalError, match="already exists"):
        schema.create_database(db_path)
    with closing(sqlite3.connect(db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0] == 0


def test_a_failed_fingerprint_leaves_the_database_buildable(tmp_path, monkeypatch):
    """Schema, ledger and fingerprint commit together, so a retry rebuilds."""
    db_path = tmp_path / "tracker.db"
    real = schema._get_or_create_fingerprint

    def unwritable(path):
        raise OSError("fingerprint file not writable")

    monkeypatch.setattr(schema, "_get_or_create_fingerprint", unwritable)
    with pytest.raises(OSError, match="not writable"):
        schema.create_database(db_path)
    monkeypatch.setattr(schema, "_get_or_create_fingerprint", real)
    schema.create_database(db_path)
    with closing(sqlite3.connect(db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM _metadata WHERE key = 'fingerprint'").fetchone()[0] == 1


def test_019_creates_task_attachments_where_it_is_missing(tmp_path):
    """A database whose attachments table was never created gets it from 019."""
    db_path = tmp_path / "tracker.db"
    schema.create_database(db_path)
    with closing(sqlite3.connect(db_path, isolation_level=None)) as conn:
        conn.execute("DROP TABLE task_attachments")
        conn.execute("DELETE FROM schema_migrations WHERE version = 19")
        assert [m.version for m in apply_all(conn, schema.MIGRATIONS_DIR)] == [19]
        columns = [row[1] for row in conn.execute("PRAGMA table_info(task_attachments)")]
        assert columns == ["id", "task_id", "filename", "stored_name", "mime_type",
                           "size_bytes", "uploaded_at", "uploaded_by"]
        assert "idx_attachments_task_id" in {row[1] for row in conn.execute("PRAGMA index_list(task_attachments)")}


def test_calendar_entry_points_create_a_fresh_database(tmp_path, monkeypatch):
    """The calendar no longer creates its own tables; its managers must reach create_database."""
    from fastapi.testclient import TestClient

    from dashboard.app import app

    monkeypatch.setenv("PT_DB_PATH", str(tmp_path / "fresh" / "tracker.db"))
    (tmp_path / "fresh").mkdir()
    response = TestClient(app).get("/api/calendar/events")
    assert response.status_code == 200, response.text
    assert response.json()["events"] == []


def test_fingerprint_read_failure_raises_instead_of_skipping_mismatch_check(tmp_path, monkeypatch):
    """#6900: an unreadable DB fingerprint must not read as "no fingerprint".

    That path skipped the mismatch guard and returned the file fingerprint,
    which create_database then wrote over the database's own.
    """
    db_path = tmp_path / "tracker.db"
    sqlite3.connect(db_path).close()
    (tmp_path / ".db-fingerprint").write_text("file-fingerprint")

    def locked(*_args, **_kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(schema.sqlite3, "connect", locked)
    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        schema._get_or_create_fingerprint(db_path)
