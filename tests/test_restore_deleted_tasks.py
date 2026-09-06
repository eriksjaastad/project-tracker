"""Restoring Done cards the old trim deleted (#6871).

The portfolio-wide `trim_done_tasks` hard-deleted 1,288 Done cards before
#6870 replaced it with per-project archiving. `delete_audit_log` snapshotted
each row before deletion, so they are recoverable. These tests pin the rules
that keep the restore from causing a *second* incident: never overwrite a live
row, never resurrect a deliberately-removed project, never write a dangling
reference, and never double-insert on a re-run.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from db.schema import create_database  # noqa: E402
from restore_deleted_tasks import (  # noqa: E402
    apply_restore,
    connect,
    latest_deleted_rows,
    plan_restore,
)


def _log_delete(conn: sqlite3.Connection, deleted_at: str, **row) -> None:
    row.setdefault("status", "Done")
    row.setdefault("project_id", "alpha")
    row.setdefault("text", f"card {row['id']}")
    row.setdefault("priority", None)
    row.setdefault("created_at", "2026-01-01T00:00:00")
    row.setdefault("updated_at", "2026-01-02T00:00:00")
    row.setdefault("completed_at", "2026-01-02T00:00:00")
    row.setdefault("parent_id", None)
    row.setdefault("blocked_by", None)
    row.setdefault("sequence_order", None)
    conn.execute(
        "INSERT INTO delete_audit_log (table_name, deleted_id, deleted_data, "
        "deleted_at, source) VALUES ('tasks', ?, ?, ?, 'test')",
        (row["id"], json.dumps(row), deleted_at),
    )
    conn.commit()


@pytest.fixture
def db(tmp_path: Path):
    db_path = tmp_path / "tracker.db"
    create_database(db_path)
    conn = connect(db_path)
    conn.execute(
        "INSERT INTO projects (id, name, path, status, created_at) "
        "VALUES ('alpha', 'Alpha', '/tmp/alpha', 'active', '2026-01-01T00:00:00')"
    )
    conn.commit()
    return conn


def test_latest_audit_entry_per_id_wins(db: sqlite3.Connection) -> None:
    _log_delete(db, "2026-02-01 00:00:00", id=1, text="first", status="Backlog")
    _log_delete(db, "2026-03-01 00:00:00", id=1, text="second", status="Done")

    latest = latest_deleted_rows(db)
    assert len(latest) == 1
    assert latest[1]["text"] == "second"
    assert latest[1]["status"] == "Done"


def test_only_done_cards_are_restored(db: sqlite3.Connection) -> None:
    _log_delete(db, "2026-02-01 00:00:00", id=1, status="Done")
    _log_delete(db, "2026-02-01 00:00:00", id=2, status="Backlog")
    _log_delete(db, "2026-02-01 00:00:00", id=3, status="Review")

    plan = plan_restore(db, include_dead_projects=False)
    assert set(plan["restore"]) == {1}


def test_never_overwrites_a_live_row(db: sqlite3.Connection) -> None:
    """The id may have been reused by a different card — restoring over it
    would be a second data-loss incident."""
    db.execute(
        "INSERT INTO tasks (id, text, status, project_id) "
        "VALUES (7, 'live card that reused the id', 'Backlog', 'alpha')"
    )
    db.commit()
    _log_delete(db, "2026-02-01 00:00:00", id=7, text="deleted card")

    plan = plan_restore(db, include_dead_projects=False)
    assert plan["restore"] == {}
    assert plan["skipped_live_id"] == [7]

    apply_restore(db, plan["restore"])
    text = db.execute("SELECT text FROM tasks WHERE id = 7").fetchone()[0]
    assert text == "live card that reused the id"


def test_skips_projects_that_no_longer_exist(db: sqlite3.Connection) -> None:
    _log_delete(db, "2026-02-01 00:00:00", id=1, project_id="alpha")
    _log_delete(db, "2026-02-01 00:00:00", id=2, project_id="deleted-project")

    plan = plan_restore(db, include_dead_projects=False)
    assert set(plan["restore"]) == {1}
    assert plan["skipped_dead_projects"]["deleted-project"] == 1

    permissive = plan_restore(db, include_dead_projects=True)
    assert set(permissive["restore"]) == {1, 2}


def test_dangling_references_are_nulled(db: sqlite3.Connection) -> None:
    _log_delete(db, "2026-02-01 00:00:00", id=1, parent_id=999, blocked_by=998)

    plan = plan_restore(db, include_dead_projects=False)
    assert plan["dangling_nulled"] == {"parent_id": 1, "blocked_by": 1}
    assert plan["restore"][1]["parent_id"] is None
    assert plan["restore"][1]["blocked_by"] is None


def test_surviving_references_are_kept(db: sqlite3.Connection) -> None:
    _log_delete(db, "2026-02-01 00:00:00", id=1)
    _log_delete(db, "2026-02-01 00:00:00", id=2, parent_id=1)

    plan = plan_restore(db, include_dead_projects=False)
    assert plan["dangling_nulled"]["parent_id"] == 0
    assert plan["restore"][2]["parent_id"] == 1


def test_restored_cards_are_done_and_archived(db: sqlite3.Connection) -> None:
    _log_delete(db, "2026-02-01 00:00:00", id=1, completed_at="2026-01-02T00:00:00")

    plan = plan_restore(db, include_dead_projects=False)
    assert apply_restore(db, plan["restore"]) == 1

    row = db.execute(
        "SELECT status, archived_at, completed_at, text FROM tasks WHERE id = 1"
    ).fetchone()
    assert row[0] == "Done"
    assert row[1] is not None, "restored cards must not flood the board"
    assert row[2] == "2026-01-02T00:00:00", "original completion date preserved"
    assert row[3] == "card 1"


def test_restore_is_idempotent(db: sqlite3.Connection) -> None:
    for i in (1, 2, 3):
        _log_delete(db, "2026-02-01 00:00:00", id=i)

    first = plan_restore(db, include_dead_projects=False)
    assert apply_restore(db, first["restore"]) == 3

    second = plan_restore(db, include_dead_projects=False)
    assert second["restore"] == {}
    assert apply_restore(db, second["restore"]) == 0
    assert db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 3


def test_restore_inserts_only_never_deletes(db: sqlite3.Connection) -> None:
    db.execute(
        "INSERT INTO tasks (id, text, status, project_id) "
        "VALUES (100, 'untouched', 'In Progress', 'alpha')"
    )
    db.commit()
    _log_delete(db, "2026-02-01 00:00:00", id=1)

    before = db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    plan = plan_restore(db, include_dead_projects=False)
    apply_restore(db, plan["restore"])
    after = db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]

    assert after == before + 1
    assert db.execute(
        "SELECT text FROM tasks WHERE id = 100"
    ).fetchone()[0] == "untouched"
