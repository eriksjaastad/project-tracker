"""The task_notes_history migration creates a local-only audit table (#7642)."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from db.crr_manifest import (  # noqa: E402
    CRR_TABLES,
    LOCAL_ONLY_TABLES,
    assert_tables_classified,
)
from db.migration_runner import discover_migrations  # noqa: E402
from db.schema import ensure_schema  # noqa: E402


MIGRATIONS_DIR = Path(__file__).parent.parent / "scripts" / "db" / "migrations"


def _migration_up(conn: sqlite3.Connection) -> None:
    migration = next(
        m for m in discover_migrations(MIGRATIONS_DIR) if m.version == 14
    )
    assert migration.crr_tables == frozenset()
    migration.up(conn)


def test_notes_history_migration_is_additive_idempotent_and_preserves_data(
    tmp_path: Path,
) -> None:
    original = sqlite3.connect(tmp_path / "original.db")
    original.execute("CREATE TABLE existing_record (value TEXT NOT NULL)")
    original.execute("INSERT INTO existing_record VALUES ('retained')")
    original.commit()
    copy = sqlite3.connect(tmp_path / "copy.db")
    original.backup(copy)
    original.close()

    _migration_up(copy)
    _migration_up(copy)
    assert copy.execute("SELECT value FROM existing_record").fetchall() == [
        ("retained",)
    ]
    assert {
        row[0]
        for row in copy.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    } >= {"task_notes_history", "existing_record"}
    copy.close()


def test_notes_history_columns_defaults_and_index(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "notes.db")
    _migration_up(conn)

    names = [row[1] for row in conn.execute("PRAGMA table_info(task_notes_history)")]
    assert names == [
        "id", "task_id", "project_id", "old_notes", "new_notes", "source", "timestamp",
    ]
    index_names = {
        row[1] for row in conn.execute("PRAGMA index_list(task_notes_history)").fetchall()
    }
    assert "idx_task_notes_history_task_timestamp" in index_names

    conn.execute(
        "INSERT INTO task_notes_history (task_id, project_id, timestamp) "
        "VALUES (1, 'project-tracker', '2026-09-26T00:00:00')"
    )
    assert conn.execute("SELECT source FROM task_notes_history").fetchone()[0] == "unknown"
    conn.close()


def test_fresh_schema_matches_migration_and_manifest() -> None:
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn.cursor())
    _migration_up(conn)
    assert "task_notes_history" in LOCAL_ONLY_TABLES
    assert not ({"task_notes_history"} & CRR_TABLES)
    assert_tables_classified(conn)

    migrated = sqlite3.connect(":memory:")
    _migration_up(migrated)
    for table in ("task_notes_history",):
        assert conn.execute(f"PRAGMA table_info({table})").fetchall() == (
            migrated.execute(f"PRAGMA table_info({table})").fetchall()
        )
        assert conn.execute(f"PRAGMA index_list({table})").fetchall() == (
            migrated.execute(f"PRAGMA index_list({table})").fetchall()
        )
    conn.close()
    migrated.close()
