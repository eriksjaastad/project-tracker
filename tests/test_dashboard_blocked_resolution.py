"""The board must not render a blocked card as unblocked (#6885).

`task_lookup.get(blocked_id)` dropped misses silently, so a card whose blockers
were not in the fetched set came back with `is_blocked = False`. That is the
dashboard's version of #6747, where `pt tasks show` printed "(all resolved)"
for a card that was genuinely blocked — the failure states the opposite of the
truth, which is worse than an error.

A miss has two causes that must not be conflated: the blocker may be archived
(Done, excluded by default since #6870, so genuinely not blocking), or it may
not exist at all.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from db.manager import DatabaseManager  # noqa: E402
from db.schema import create_database  # noqa: E402


@pytest.fixture
def board(tmp_path, monkeypatch):
    db_path = tmp_path / "tracker.db"
    create_database(db_path)
    db = DatabaseManager(db_path=db_path)
    db.add_project("alpha", "Alpha", str(tmp_path / "alpha"), "active")
    monkeypatch.setenv("PT_DB_PATH", str(db_path))
    return db


def _blocked_view(db, task_id, monkeypatch):
    """Call the real /api/tasks handler, not a reimplementation of it.

    A test that re-derives the logic it checks passes even when the endpoint is
    wrong, which is the failure this file exists to prevent.

    The handler is invoked directly rather than through TestClient as a context
    manager: that runs the app lifespan, which rebuilds the project graph and
    scans the filesystem — it made unrelated hygiene tests fail intermittently
    and added a minute to the suite.
    """
    import asyncio

    import dashboard.app as dashboard_app

    monkeypatch.setattr(dashboard_app, "DatabaseManager", lambda *a, **k: db)
    # status_filter must be passed explicitly: its default is a FastAPI
    # Query() marker that only the framework resolves.
    #
    # run_until_complete on the existing loop, NOT asyncio.run() — the latter
    # closes the loop on exit, and the other dashboard tests reach for
    # get_event_loop() afterwards and got a closed one. That took out seven
    # unrelated tests.
    loop = asyncio.get_event_loop_policy().get_event_loop()
    payload = loop.run_until_complete(
        dashboard_app.list_tasks(project_id="alpha", status_filter=None)
    )
    rows = payload["tasks"] if isinstance(payload, dict) else payload
    row = next(r for r in rows if r["id"] == task_id)
    return {
        "is_blocked": row.get("is_blocked"),
        "incomplete": row.get("incomplete_blocking_ids", []),
        "unresolved": row.get("unresolved_blocking_ids", []),
    }


def test_incomplete_blocker_marks_the_card_blocked(board, monkeypatch):
    blocker = board.add_task("blocker", "alpha")
    target = board.add_task("target", "alpha")
    board.update_task(target["id"], blocked_by=json.dumps([blocker["id"]]))

    view = _blocked_view(board, target["id"], monkeypatch)
    assert view["is_blocked"] is True
    assert view["incomplete"] == [blocker["id"]]


def test_archived_done_blocker_does_not_block(board, monkeypatch):
    """The blocker is Done and archived off the board — genuinely not blocking.

    Naively treating every lookup miss as 'blocked' would get this wrong.
    """
    blocker = board.add_task("blocker", "alpha")
    target = board.add_task("target", "alpha")
    board.update_task(target["id"], blocked_by=json.dumps([blocker["id"]]))
    board.update_task(blocker["id"], status="To Do")
    board.update_task(blocker["id"], status="In Progress")
    board.update_task(blocker["id"], status="Review")
    board.update_task(blocker["id"], status="Done")
    board.archive_done_tasks(keep_per_project=0)

    assert blocker["id"] not in {t["id"] for t in board.get_tasks(project_id="alpha")}, (
        "fixture precondition: the blocker must be archived off the board"
    )
    view = _blocked_view(board, target["id"], monkeypatch)
    assert view["is_blocked"] is False, "an archived Done blocker still blocked the card"
    assert view["unresolved"] == []


def test_nonexistent_blocker_is_surfaced_not_silently_cleared(board, monkeypatch):
    """The #6885 case: an id that resolves to nothing must not read as unblocked."""
    target = board.add_task("target", "alpha")
    board.update_task(target["id"], blocked_by=json.dumps([999999999]))

    view = _blocked_view(board, target["id"], monkeypatch)
    assert view["unresolved"] == [999999999]
    assert view["is_blocked"] is True, (
        "an unresolvable blocker rendered as unblocked — the card claims it is "
        "ready to work when nothing proved that"
    )
