"""Done-column retention: archive, never delete (#6870).

`pt tasks done` used to call `trim_done_tasks(keep=75)`, which counted Done
cards portfolio-wide with no project filter and hard-DELETEd everything past
75. A busy project's completions evicted a quiet project's history — 1,288
Done cards were destroyed, 244 of them project-tracker's — and because the
delete cascaded to `task_history` it erased its own evidence.

These tests pin the replacement behavior: retention is a *display* concern.
Cards past the per-project cap get `archived_at` stamped and drop off the
board; the rows, their status, and their completion timestamps all survive.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from db.manager import DatabaseManager  # noqa: E402
from db.schema import create_database  # noqa: E402
import pt as pt_cli  # noqa: E402


def _setup_db(tmp_path: Path) -> tuple[Path, DatabaseManager]:
    db_path = tmp_path / "tracker.db"
    create_database(db_path)
    db = DatabaseManager(db_path=db_path)
    db.add_project("alpha", "Alpha", "/tmp/alpha", "active")
    db.add_project("beta", "Beta", "/tmp/beta", "active")
    return db_path, db


def _add_done(db: DatabaseManager, db_path: Path, project_id: str, n: int) -> list[int]:
    """Create `n` Done cards in `project_id`, oldest first, with distinct
    completion timestamps so the retention ordering is unambiguous."""
    ids = []
    for i in range(n):
        task = db.add_task(f"{project_id} done {i}", project_id, status="Done")
        stamp = f"2026-01-{(i % 28) + 1:02d}T{(i % 24):02d}:00:00"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE tasks SET completed_at = ?, updated_at = ? WHERE id = ?",
                (stamp, stamp, task["id"]),
            )
            conn.commit()
        ids.append(task["id"])
    return ids


def _row_count(db_path: Path, table: str) -> int:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ---------------------------------------------------------------------
# (a) completing a card deletes nothing
# ---------------------------------------------------------------------


def test_pt_tasks_done_deletes_zero_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path, db = _setup_db(tmp_path)
    monkeypatch.setenv("PT_DB_PATH", str(db_path))
    monkeypatch.setenv("PT_ALLOW_FRESH_DB", "1")
    monkeypatch.setattr(pt_cli, "_notify_inbox", lambda *a, **k: None)

    # Well past the old keep=75 portfolio cap and the new per-project cap.
    _add_done(db, db_path, "alpha", 80)
    _add_done(db, db_path, "beta", 5)

    finishing = db.add_task("Finish me", "alpha", status="Review")

    tasks_before = _row_count(db_path, "tasks")
    history_before = _row_count(db_path, "task_history")
    audit_before = _row_count(db_path, "delete_audit_log")

    result = CliRunner().invoke(pt_cli.tasks_group, ["done", str(finishing["id"])])
    assert result.exit_code == 0, result.output

    assert _row_count(db_path, "tasks") == tasks_before
    # task_history only grows — the completion event is appended, never trimmed.
    assert _row_count(db_path, "task_history") >= history_before
    assert _row_count(db_path, "delete_audit_log") == audit_before

    # And it archived rather than trimmed.
    assert "Archived" in result.output
    assert "Trimmed" not in result.output


# ---------------------------------------------------------------------
# (b) archiving is per-project
# ---------------------------------------------------------------------


def test_archiving_is_per_project(tmp_path: Path) -> None:
    db_path, db = _setup_db(tmp_path)
    _add_done(db, db_path, "alpha", 40)
    beta_ids = _add_done(db, db_path, "beta", 3)

    archived = db.archive_done_tasks(keep_per_project=25)
    assert archived == 15  # alpha's oldest 15; beta untouched

    alpha_visible = db.get_tasks(project_id="alpha", status="Done")
    beta_visible = db.get_tasks(project_id="beta", status="Done")
    assert len(alpha_visible) == 25
    assert len(beta_visible) == 3

    # Beta's cards specifically were not archived by alpha's burst.
    assert {t["id"] for t in beta_visible} == set(beta_ids)
    assert all(t["archived_at"] is None for t in beta_visible)

    # The newest alpha cards are the ones kept.
    kept_stamps = sorted(t["completed_at"] for t in alpha_visible)
    all_alpha = db.get_tasks(project_id="alpha", status="Done", include_archived=True)
    archived_stamps = sorted(
        t["completed_at"] for t in all_alpha if t["archived_at"] is not None
    )
    assert max(archived_stamps) <= min(kept_stamps)


def test_archiving_is_idempotent(tmp_path: Path) -> None:
    db_path, db = _setup_db(tmp_path)
    _add_done(db, db_path, "alpha", 30)

    assert db.archive_done_tasks(keep_per_project=25) == 5
    # Already-archived cards don't count against the cap, so a second run
    # must not archive the next 5.
    assert db.archive_done_tasks(keep_per_project=25) == 0
    assert len(db.get_tasks(project_id="alpha", status="Done")) == 25


def test_archiving_ignores_non_done_cards(tmp_path: Path) -> None:
    db_path, db = _setup_db(tmp_path)
    _add_done(db, db_path, "alpha", 30)
    backlog = db.add_task("Still open", "alpha", status="Backlog")

    db.archive_done_tasks(keep_per_project=0)

    assert db.get_task(backlog["id"])["archived_at"] is None
    assert len(db.get_tasks(project_id="alpha")) == 1


# ---------------------------------------------------------------------
# (c) get_tasks hides archived by default
# ---------------------------------------------------------------------


def test_get_tasks_hides_archived_by_default(tmp_path: Path) -> None:
    db_path, db = _setup_db(tmp_path)
    _add_done(db, db_path, "alpha", 30)

    db.archive_done_tasks(keep_per_project=25)

    assert len(db.get_tasks(project_id="alpha")) == 25
    assert len(db.get_tasks(project_id="alpha", include_archived=True)) == 30
    assert len(db.get_tasks()) == 25
    assert len(db.get_tasks(include_archived=True)) == 30

    # The status filter is orthogonal to the archived filter.
    assert len(db.get_tasks(status="Done")) == 25
    assert len(db.get_tasks(status="Done", include_archived=True)) == 30


def test_cli_archived_flag_shows_hidden_cards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path, db = _setup_db(tmp_path)
    monkeypatch.setenv("PT_DB_PATH", str(db_path))
    monkeypatch.setenv("PT_ALLOW_FRESH_DB", "1")

    ids = _add_done(db, db_path, "alpha", 30)
    db.archive_done_tasks(keep_per_project=25)
    archived_ids = {
        t["id"]
        for t in db.get_tasks(project_id="alpha", include_archived=True)
        if t["archived_at"] is not None
    }
    assert len(archived_ids) == 5
    assert archived_ids <= set(ids)

    runner = CliRunner()

    default_view = runner.invoke(pt_cli.tasks_group, ["list", "-p", "alpha", "--all"])
    assert default_view.exit_code == 0, default_view.output
    assert "Total: 25 tasks" in default_view.output

    archived_view = runner.invoke(
        pt_cli.tasks_group, ["list", "-p", "alpha", "--archived"]
    )
    assert archived_view.exit_code == 0, archived_view.output
    assert "Total: 5 tasks" in archived_view.output


# ---------------------------------------------------------------------
# (d) archiving preserves the card
# ---------------------------------------------------------------------


def test_archiving_preserves_status_and_completed_at(tmp_path: Path) -> None:
    db_path, db = _setup_db(tmp_path)
    ids = _add_done(db, db_path, "alpha", 30)

    before = {
        t["id"]: (t["status"], t["completed_at"], t["updated_at"], t["text"])
        for t in db.get_tasks(project_id="alpha", include_archived=True)
    }

    db.archive_done_tasks(keep_per_project=25)

    after = db.get_tasks(project_id="alpha", include_archived=True)
    assert len(after) == 30
    assert {t["id"] for t in after} == set(ids)

    archived = [t for t in after if t["archived_at"] is not None]
    assert len(archived) == 5

    for task in after:
        status, completed_at, updated_at, text = before[task["id"]]
        assert task["status"] == status == "Done"
        assert task["completed_at"] == completed_at
        assert task["updated_at"] == updated_at
        assert task["text"] == text

    # task_history for archived cards survives too — the old trim deleted it.
    with sqlite3.connect(db_path) as conn:
        for task in archived:
            assert (
                conn.execute(
                    "SELECT COUNT(*) FROM task_history WHERE task_id = ?",
                    (task["id"],),
                ).fetchone()[0]
                > 0
            )


def test_archive_rejects_negative_cap(tmp_path: Path) -> None:
    _, db = _setup_db(tmp_path)
    with pytest.raises(ValueError):
        db.archive_done_tasks(keep_per_project=-1)


# ---------------------------------------------------------------------
# Destructive paths still see everything they are about to destroy
# ---------------------------------------------------------------------


def test_clear_done_counts_archived_cards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path, db = _setup_db(tmp_path)
    monkeypatch.setenv("PT_DB_PATH", str(db_path))
    monkeypatch.setenv("PT_ALLOW_FRESH_DB", "1")
    monkeypatch.setenv("SAFE_MODE", "0")
    monkeypatch.setenv("ALLOW_BULK_DELETE", "1")
    monkeypatch.setattr(pt_cli, "_notify_inbox", lambda *a, **k: None)

    _add_done(db, db_path, "alpha", 30)
    db.archive_done_tasks(keep_per_project=25)

    result = CliRunner().invoke(
        pt_cli.tasks_group, ["clear-done", "-p", "alpha"], input="n\n"
    )
    assert result.exit_code == 0, result.output
    # 30, not 25 — clear-done deletes archived rows too.
    assert "Delete 30 Done task(s)?" in result.output
