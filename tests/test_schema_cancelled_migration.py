"""Regression tests for the 'Cancelled' status migration in ensure_schema.

That migration recreates the tasks table to widen a CHECK constraint, which
means it drops the original. It did so with a hardcoded 17-column list, no
backup, and no verification -- so on any database whose tasks table had grown
past those 17 columns it silently discarded the rest and reported success.

The live table now has 27 columns. Card #6955.
"""

import sqlite3

import scripts.db.schema as schema

# The columns this migration's hardcoded list knew about...
_LEGACY_COLUMNS = [
    ("id", "INTEGER PRIMARY KEY NOT NULL"),
    ("text", "TEXT NOT NULL"),
    ("status", "TEXT NOT NULL CHECK(status IN ('Backlog', 'To Do', 'In Progress', 'Review', 'Done'))"),
    ("project_id", "TEXT NOT NULL"),
    ("priority", "TEXT"),
    ("created_at", "TEXT NOT NULL"),
    ("updated_at", "TEXT NOT NULL"),
    ("sequence_order", "INTEGER"),
]
# ...and columns added to the real table long afterwards, which it did not.
_LATER_COLUMNS = [
    ("task_type", "TEXT"),
    ("archived_at", "TEXT"),
    ("created_by", "TEXT"),
    ("evidence", "TEXT"),
]


def _old_schema_db(path):
    """A tasks table whose CHECK predates 'Cancelled' (so the migration fires)
    but which carries columns added after the migration was written."""
    conn = sqlite3.connect(path)
    cols = ", ".join(f"{name} {decl}" for name, decl in _LEGACY_COLUMNS + _LATER_COLUMNS)
    conn.execute(f"CREATE TABLE tasks ({cols})")
    conn.execute(
        "INSERT INTO tasks (id, text, status, project_id, created_at, updated_at,"
        " sequence_order, task_type, archived_at, created_by, evidence)"
        " VALUES (1, 'keep me', 'Backlog', 'demo', 'x', 'y', 3, 'proposal',"
        " '2026-01-01', 'architect', 'card-factory finding')"
    )
    conn.commit()
    return conn


def test_migration_preserves_columns_added_after_it_was_written(tmp_path):
    db = tmp_path / "old.db"
    conn = _old_schema_db(db)

    schema.ensure_schema(conn.cursor())
    conn.commit()

    columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
    for name, _decl in _LATER_COLUMNS:
        assert name in columns, f"migration dropped column {name!r}"

    row = conn.execute(
        "SELECT text, task_type, archived_at, created_by, evidence FROM tasks WHERE id = 1"
    ).fetchone()
    assert row == ("keep me", "proposal", "2026-01-01", "architect", "card-factory finding")
    conn.close()


def test_migration_preserves_column_types(tmp_path):
    """A rebuild that flattens every column to TEXT is data loss too."""
    db = tmp_path / "types.db"
    conn = _old_schema_db(db)

    schema.ensure_schema(conn.cursor())
    conn.commit()

    types = {row[1]: row[2].upper() for row in conn.execute("PRAGMA table_info(tasks)")}
    assert types["sequence_order"] == "INTEGER"
    assert types["id"] == "INTEGER"
    conn.close()


def test_migration_leaves_a_backup_table(tmp_path):
    db = tmp_path / "backup.db"
    conn = _old_schema_db(db)

    schema.ensure_schema(conn.cursor())
    conn.commit()

    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "tasks_backup_cancelled_migration" in tables, (
        "no recovery path if the rebuild goes wrong"
    )
    kept = conn.execute(
        "SELECT COUNT(*) FROM tasks_backup_cancelled_migration"
    ).fetchone()[0]
    assert kept == 1
    conn.close()


def test_migration_widens_the_status_check(tmp_path):
    """The point of the migration: 'Cancelled' must be accepted afterwards."""
    db = tmp_path / "check.db"
    conn = _old_schema_db(db)

    schema.ensure_schema(conn.cursor())
    conn.commit()

    conn.execute("UPDATE tasks SET status = 'Cancelled' WHERE id = 1")
    conn.commit()
    assert conn.execute("SELECT status FROM tasks WHERE id = 1").fetchone()[0] == "Cancelled"
    conn.close()


def test_row_count_is_preserved(tmp_path):
    db = tmp_path / "rows.db"
    conn = _old_schema_db(db)
    conn.execute(
        "INSERT INTO tasks (id, text, status, project_id, created_at, updated_at)"
        " VALUES (2, 'second', 'Done', 'demo', 'x', 'y')"
    )
    conn.commit()

    schema.ensure_schema(conn.cursor())
    conn.commit()

    assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 2
    conn.close()
