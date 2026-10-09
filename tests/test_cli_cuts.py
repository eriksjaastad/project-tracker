"""#8093 PR 1: unused commands are gone, `status` takes an id, and the shared
card-transition loop keeps its contract (a skip is neither success nor failure).
"""

import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pt  # noqa: E402
from db.manager import DatabaseManager  # noqa: E402
from db.schema import create_database  # noqa: E402


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DatabaseManager:
    db_path = tmp_path / "test.db"
    create_database(db_path)
    monkeypatch.setenv("PT_DB_PATH", str(db_path))
    manager = DatabaseManager(db_path)
    manager.add_project(project_id="proj-id", name="Proj Name", path="/tmp/proj", status="active")
    manager.add_project(project_id="other", name="Other", path="/tmp/other", status="active")
    return manager


@pytest.mark.parametrize(
    "args",
    [
        ["remove-project", "x"],
        ["orphans"],
        ["export-projects"],
        ["add-agent", "p", "a"],
        ["add-service", "p", "s"],
        ["inbox"],
        ["tasks", "prompt-validate", "1"],
        ["tasks", "import", "f.json"],
        ["tasks", "clear-done"],
    ],
)
def test_cut_commands_are_gone(args) -> None:
    result = CliRunner().invoke(pt.cli, args)
    assert result.exit_code == 2
    assert "No such command" in result.output


@pytest.mark.parametrize("name", ["proj-id", "PROJ NAME", "Proj Name"])
def test_status_accepts_id_or_name(db, name: str) -> None:
    result = CliRunner().invoke(pt.cli, ["status", name])
    assert result.exit_code == 0, result.output
    assert "Proj Name" in result.output
    assert "not found" not in result.output


def test_status_unknown_project_says_not_found(db) -> None:
    result = CliRunner().invoke(pt.cli, ["status", "nope"])
    assert "Project 'nope' not found" in result.output


def test_move_skip_is_not_a_failure(db) -> None:
    a = db.add_task(text="already there", project_id="other", status="To Do")
    b = db.add_task(text="moves", project_id="proj-id", status="To Do")
    result = CliRunner().invoke(pt.tasks_group, ["move", "other", str(a["id"]), str(b["id"])])
    assert result.exit_code == 0, result.output
    assert f"Task #{a['id']} already in project 'Other'" in result.output
    assert "Moved 1/2 tasks to 'Other'" in result.output
    assert db.get_task(b["id"])["project_id"] == "other"


def test_mixed_batch_keeps_going_then_exits_one(db) -> None:
    ok = db.add_task(text="fine", project_id="proj-id", status="To Do")
    result = CliRunner().invoke(pt.tasks_group, ["start", "999999", str(ok["id"])])
    assert result.exit_code == 1
    assert "Task #999999 not found" in result.output
    assert f"Started: #{ok['id']} - fine" in result.output
    assert "Started 1/2 tasks" in result.output
    assert db.get_task(ok["id"])["status"] == "In Progress"


def test_approve_refuses_non_proposal(db) -> None:
    t = db.add_task(text="plain", project_id="proj-id", status="To Do")
    result = CliRunner().invoke(pt.tasks_group, ["approve", str(t["id"])])
    assert result.exit_code == 1
    assert f"Task #{t['id']} is not a proposal (type: " in result.output
