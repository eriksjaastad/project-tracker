"""Tests for the `pt retire-project` CLI command (#5851)."""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from db.schema import create_database


@pytest.fixture
def fabricated_project(monkeypatch):
    """Build a disposable project with a real on-disk dir and fully populated DB."""
    with tempfile.TemporaryDirectory() as tmp:
        projects_root = Path(tmp)
        project_dir = projects_root / "humpty-dumpty"
        project_dir.mkdir()
        (project_dir / "README.md").write_text("# humpty-dumpty\n")

        db_path = projects_root / "tracker.db"
        create_database(db_path)

        monkeypatch.setenv("PT_DB_PATH", str(db_path))
        monkeypatch.setenv("PROJECTS_ROOT", str(projects_root))

        # Re-import pt inside the patched env so PROJECTS_BASE_DIR + DB point at temp
        for mod in ("scripts.pt", "scripts.config", "db.manager"):
            sys.modules.pop(mod, None)

        from db.manager import DatabaseManager as DM
        db = DM()
        db.add_project(
            project_id="humpty-dumpty",
            name="humpty-dumpty",
            path=str(project_dir),
            status="active",
        )

        import sqlite3
        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE _delete_permissions SET enabled = 1 WHERE id = 1")
            conn.execute(
                "INSERT INTO tasks (text, status, project_id, priority, created_at, updated_at) "
                "VALUES (?, 'Backlog', 'humpty-dumpty', 'Medium', datetime('now'), datetime('now'))",
                ("First shell crack",),
            )
            conn.execute(
                "INSERT INTO tasks (text, status, project_id, priority, created_at, updated_at) "
                "VALUES (?, 'Backlog', 'humpty-dumpty', 'Medium', datetime('now'), datetime('now'))",
                ("Put him back together",),
            )
            conn.execute("UPDATE _delete_permissions SET enabled = 0 WHERE id = 1")

        db.add_cron_job("humpty-dumpty", "0 * * * *", "echo wall", "hourly wall check")
        db.add_ai_agent("humpty-dumpty", "king-horse", "attempts reconstruction")

        yield {
            "projects_root": projects_root,
            "project_dir": project_dir,
            "db_path": db_path,
            "db": db,
        }


def _get_cli():
    from scripts.pt import cli as pt_cli
    return pt_cli


def test_dry_run_reports_but_changes_nothing(fabricated_project):
    cli = _get_cli()
    runner = CliRunner()
    with patch("send2trash.send2trash") as trash_mock:
        result = runner.invoke(cli, ["retire-project", "humpty-dumpty"])

    assert result.exit_code == 0, result.output
    assert "DRY RUN" in result.output
    assert "Tasks:    2" in result.output
    assert "Crons:    1" in result.output
    assert "Agents:   1" in result.output
    assert "Dry run complete" in result.output
    trash_mock.assert_not_called()

    # Verify DB and filesystem untouched
    db = fabricated_project["db"]
    assert db.get_project("humpty-dumpty") is not None
    assert len(db.get_tasks(project_id="humpty-dumpty")) == 2
    assert fabricated_project["project_dir"].exists()


def test_execute_trashes_dir_and_cascades_db(fabricated_project):
    cli = _get_cli()
    runner = CliRunner()
    with patch("send2trash.send2trash") as trash_mock:
        result = runner.invoke(
            cli, ["retire-project", "humpty-dumpty", "--execute", "-y"]
        )

    assert result.exit_code == 0, result.output
    assert "EXECUTE" in result.output
    assert "Retired" in result.output
    trash_mock.assert_called_once()
    called_with = trash_mock.call_args[0][0]
    assert "humpty-dumpty" in str(called_with)

    db = fabricated_project["db"]
    assert db.get_project("humpty-dumpty") is None
    assert len(db.get_tasks(project_id="humpty-dumpty")) == 0
    assert len(db.get_cron_jobs("humpty-dumpty")) == 0
    assert len(db.get_ai_agents("humpty-dumpty")) == 0


def test_keep_files_skips_trash_but_cleans_db(fabricated_project):
    cli = _get_cli()
    runner = CliRunner()
    with patch("send2trash.send2trash") as trash_mock:
        result = runner.invoke(
            cli,
            ["retire-project", "humpty-dumpty", "--execute", "--keep-files", "-y"],
        )

    assert result.exit_code == 0, result.output
    trash_mock.assert_not_called()
    assert fabricated_project["project_dir"].exists()

    db = fabricated_project["db"]
    assert db.get_project("humpty-dumpty") is None
    assert len(db.get_tasks(project_id="humpty-dumpty")) == 0


def test_unknown_project_exits_nonzero_and_touches_nothing(fabricated_project):
    cli = _get_cli()
    runner = CliRunner()
    with patch("send2trash.send2trash") as trash_mock:
        result = runner.invoke(
            cli, ["retire-project", "nonexistent-project", "--execute", "-y"]
        )

    assert result.exit_code != 0
    assert "not found" in result.output.lower()
    trash_mock.assert_not_called()

    # Humpty is unharmed
    db = fabricated_project["db"]
    assert db.get_project("humpty-dumpty") is not None
    assert fabricated_project["project_dir"].exists()


def test_stale_reference_scan_finds_hits_in_sibling_project(fabricated_project):
    sibling = fabricated_project["projects_root"] / "other-project"
    sibling.mkdir()
    (sibling / "notes.md").write_text("Depends on humpty-dumpty for reconstruction.\n")

    cli = _get_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["retire-project", "humpty-dumpty"])

    assert result.exit_code == 0
    assert "notes.md" in result.output
    assert "humpty-dumpty" in result.output.lower()
