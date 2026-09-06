"""Backfilling display IDs stored in `tasks.blocked_by` (#6747).

Before the CLI fix, `--blocked-by` stored whatever integer the operator typed.
Display IDs are what the board prints, so that is what landed in the column —
matching no `tasks.id`. `get_blocking_tasks` dropped them silently and the card
reported itself unblocked while genuinely blocked.

These tests pin the rules that keep the repair from inventing dependencies:
rewrite only what `task_display_ids` can resolve, never guess at an ID that
matches nothing, never touch a row that is already correct, and never rewrite
a malformed value.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from backfill_blocked_by import (  # noqa: E402
    apply_backfill,
    connect,
    plan_backfill,
)
from db.schema import create_database  # noqa: E402


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "tracker.db"
    create_database(db_path)
    conn = connect(db_path)
    conn.execute(
        "INSERT INTO projects (id, name, path, status, created_at) "
        "VALUES ('alpha', 'Alpha', '/tmp/alpha', 'active', '2026-01-01T00:00:00')"
    )
    conn.commit()
    return conn


def _task(conn: sqlite3.Connection, pk: int, display_id: int | None = None,
          blocked_by=None) -> int:
    conn.execute(
        "INSERT INTO tasks (id, text, status, project_id, created_at, updated_at, "
        "blocked_by) VALUES (?, ?, 'Backlog', 'alpha', '2026-01-01T00:00:00', "
        "'2026-01-01T00:00:00', ?)",
        (pk, f"card {pk}", json.dumps(blocked_by) if blocked_by is not None else None),
    )
    if display_id is not None:
        conn.execute(
            "INSERT INTO task_display_ids (task_id, display_id) VALUES (?, ?)",
            (pk, display_id),
        )
    conn.commit()
    return pk


def _blocked_by(conn: sqlite3.Connection, pk: int):
    raw = conn.execute("SELECT blocked_by FROM tasks WHERE id = ?", (pk,)).fetchone()[0]
    return None if raw is None else json.loads(raw)


def test_rewrites_display_ids_to_canonical_pks(db):
    blocker = _task(db, 10 ** 15 + 1, display_id=100)
    target = _task(db, 10 ** 15 + 2, display_id=101, blocked_by=[100])

    plan = plan_backfill(db)
    assert len(plan["rewrites"]) == 1
    entry = plan["rewrites"][0]
    assert entry["task_id"] == target
    assert entry["before"] == [100]
    assert entry["after"] == [blocker]
    assert entry["unresolved"] == []

    assert apply_backfill(db, plan["rewrites"]) == 1
    assert _blocked_by(db, target) == [blocker]


def test_leaves_already_correct_rows_alone(db):
    blocker = _task(db, 10 ** 15 + 1, display_id=100)
    _task(db, 10 ** 15 + 2, display_id=101, blocked_by=[blocker])

    plan = plan_backfill(db)
    assert plan["rewrites"] == []
    assert plan["already_correct"] == 1


def test_does_not_guess_at_ids_that_resolve_to_nothing(db):
    """An unresolvable value stays put — inventing a dependency would be
    worse than the bug being fixed."""
    blocker = _task(db, 10 ** 15 + 1, display_id=100)
    target = _task(db, 10 ** 15 + 2, display_id=101, blocked_by=[100, 4242])

    plan = plan_backfill(db)
    entry = plan["rewrites"][0]
    assert entry["after"] == [blocker, 4242]
    assert entry["unresolved"] == [4242]
    assert plan["partial"] == [entry]

    apply_backfill(db, plan["rewrites"])
    assert _blocked_by(db, target) == [blocker, 4242]


def test_row_of_only_unresolvable_ids_is_never_written(db):
    target = _task(db, 10 ** 15 + 2, display_id=101, blocked_by=[4242])

    plan = plan_backfill(db)
    assert plan["rewrites"] == []
    assert plan["already_correct"] == 1
    assert _blocked_by(db, target) == [4242]


def test_display_id_pointing_at_a_deleted_task_is_not_rewritten(db):
    """A stale task_display_ids row must not resurrect a dependency on a card
    that no longer exists."""
    db.execute(
        "INSERT INTO task_display_ids (task_id, display_id) VALUES (?, ?)",
        (10 ** 15 + 99, 100),
    )
    db.commit()
    target = _task(db, 10 ** 15 + 2, display_id=101, blocked_by=[100])

    plan = plan_backfill(db)
    assert plan["rewrites"] == []
    assert _blocked_by(db, target) == [100]


def test_duplicates_are_collapsed(db):
    blocker = _task(db, 10 ** 15 + 1, display_id=100)
    target = _task(db, 10 ** 15 + 2, display_id=101, blocked_by=[100, blocker])

    plan = plan_backfill(db)
    assert plan["rewrites"][0]["after"] == [blocker]
    apply_backfill(db, plan["rewrites"])
    assert _blocked_by(db, target) == [blocker]


def test_malformed_blocked_by_is_reported_not_rewritten(db):
    target = _task(db, 10 ** 15 + 2, display_id=101)
    db.execute("UPDATE tasks SET blocked_by = 'not json' WHERE id = ?", (target,))
    db.commit()

    plan = plan_backfill(db)
    assert plan["rewrites"] == []
    assert [m["task_id"] for m in plan["malformed"]] == [target]
    assert db.execute(
        "SELECT blocked_by FROM tasks WHERE id = ?", (target,)
    ).fetchone()[0] == "not json"


def test_backfill_is_idempotent(db):
    blocker = _task(db, 10 ** 15 + 1, display_id=100)
    target = _task(db, 10 ** 15 + 2, display_id=101, blocked_by=[100])

    apply_backfill(db, plan_backfill(db)["rewrites"])
    second = plan_backfill(db)
    assert second["rewrites"] == []
    assert _blocked_by(db, target) == [blocker]
