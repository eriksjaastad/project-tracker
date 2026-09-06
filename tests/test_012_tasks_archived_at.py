"""Migration 012 — tasks.archived_at, and the CRR guard it depends on (#6870).

`tasks` is a live cr-sqlite CRR table: `crsql_as_crr('tasks')` created
`tasks__crsql_clock` and rewrote `tasks__crsql_{i,u,d}trig` with the base
table's columns spelled out literally. A bare `ALTER TABLE tasks ADD COLUMN`
would leave those triggers on a stale column list, so the column would never
replicate. The runner's `crsql_begin_alter` / `crsql_commit_alter` bracketing
is what prevents that — and it only fires when cr-sqlite is loaded on the
connection, which is what `apply_migration`'s guard now enforces.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from db.crr_manifest import CRR_TABLES as MANIFEST_CRR_TABLES  # noqa: E402
from db.migration_runner import (  # noqa: E402
    MigrationError,
    apply_migration,
    discover_migrations,
)
from db.schema import create_database  # noqa: E402


MIGRATIONS_DIR = Path(__file__).parent.parent / "scripts" / "db" / "migrations"


def _migration_012():
    [migration] = [
        m for m in discover_migrations(MIGRATIONS_DIR, verbose=False) if m.version == 12
    ]
    return migration


def test_012_declares_tasks_as_crr() -> None:
    """The declaration is what buys the crsql_*_alter bracketing."""
    migration = _migration_012()
    assert migration.crr_tables == frozenset({"tasks"})
    assert "tasks" in MANIFEST_CRR_TABLES


def test_012_adds_archived_at() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, status TEXT)")

    _migration_012().up(conn)

    cols = {r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    assert "archived_at" in cols


def test_012_is_a_noop_when_column_already_exists(tmp_path: Path) -> None:
    """Fresh databases get archived_at from the CREATE TABLE in schema.py,
    so the migration has to tolerate the column already being there."""
    db_path = tmp_path / "tracker.db"
    create_database(db_path)

    conn = sqlite3.connect(db_path)
    cols_before = {r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    assert "archived_at" in cols_before, "schema.py should create the column"

    _migration_012().up(conn)  # must not raise "duplicate column name"

    cols_after = {r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    assert cols_after == cols_before


def test_runner_refuses_unbracketed_alter_on_crr_ified_table(tmp_path: Path) -> None:
    """cr-sqlite isn't loaded under stock sqlite3. If the table has already
    been through crsql_as_crr (proved on disk by the clock table), applying
    the DDL anyway would desync the column — refuse instead."""
    conn = sqlite3.connect(tmp_path / "crr.db")
    conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE tasks__crsql_clock (key INTEGER)")

    with pytest.raises(MigrationError) as exc:
        apply_migration(conn, _migration_012())

    assert "cr-sqlite is not loaded" in str(exc.value)
    # Nothing was applied, and nothing was recorded.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    assert "archived_at" not in cols


def test_012_skips_when_tasks_table_does_not_exist() -> None:
    """`pt db migrate` can run against a bare database file, before
    schema.py has created any tables."""
    conn = sqlite3.connect(":memory:")

    _migration_012().up(conn)  # must not raise "no such table: tasks"

    assert (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'"
        ).fetchone()
        is None
    )


def test_runner_still_applies_when_table_is_not_yet_crr_ified(tmp_path: Path) -> None:
    """The pre-CRR path the runner shipped with stays intact: no clock table
    means skipping the bracket is safe."""
    conn = sqlite3.connect(tmp_path / "plain.db", isolation_level=None)
    conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY)")
    conn.execute(
        "CREATE TABLE schema_migrations ("
        "version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
    )

    apply_migration(conn, _migration_012())

    cols = {r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    assert "archived_at" in cols
