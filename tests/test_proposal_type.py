"""Tests for the proposal task type feature.

Covers:
- validate_task_type validation for valid/invalid types
- Creating proposal tasks via DatabaseManager
- Default task listing excludes proposals
- --proposals flag returns only proposals
- Approve converts proposal to manual type
- Reject cancels a proposal
"""

import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from db.manager import DatabaseManager
from db.schema import create_database
from pt import tasks_group
from utils.validation import validate_task_type, VALID_TASK_TYPES


def _setup_db(tmp_path: Path) -> tuple[Path, DatabaseManager, str]:
    db_path = tmp_path / "test.db"
    create_database(db_path)
    db = DatabaseManager(db_path=db_path)
    db.add_project(
        project_id="test-project",
        name="Test Project",
        path="/tmp/test-project",
        status="active",
    )
    return db_path, db, "test-project"


# --- validate_task_type tests ---


class TestValidateTaskType:
    def test_proposal_is_valid(self):
        is_valid, error = validate_task_type("proposal")
        assert is_valid is True
        assert error is None

    def test_manual_is_valid(self):
        is_valid, error = validate_task_type("manual")
        assert is_valid is True
        assert error is None

    def test_agent_is_valid(self):
        is_valid, error = validate_task_type("agent")
        assert is_valid is True
        assert error is None

    def test_none_is_valid(self):
        is_valid, error = validate_task_type(None)
        assert is_valid is True
        assert error is None

    def test_invalid_type_rejected(self):
        is_valid, error = validate_task_type("invalid")
        assert is_valid is False
        assert "Task type must be one of" in error

    def test_empty_string_rejected(self):
        is_valid, error = validate_task_type("")
        assert is_valid is False
        assert "Task type must be one of" in error

    def test_valid_types_constant(self):
        assert "proposal" in VALID_TASK_TYPES
        assert "manual" in VALID_TASK_TYPES
        assert "agent" in VALID_TASK_TYPES


# --- DatabaseManager proposal creation ---


class TestProposalCreation:
    def test_create_proposal_task(self, tmp_path: Path):
        _, db, project_id = _setup_db(tmp_path)
        task = db.add_task(
            text="Add caching layer",
            project_id=project_id,
            task_type="proposal",
        )
        assert task["task_type"] == "proposal"
        assert task["status"] == "Backlog"

    def test_create_manual_task_default(self, tmp_path: Path):
        _, db, project_id = _setup_db(tmp_path)
        task = db.add_task(text="Fix bug", project_id=project_id)
        assert task["task_type"] == "manual"

    def test_get_proposal_task(self, tmp_path: Path):
        _, db, project_id = _setup_db(tmp_path)
        task = db.add_task(
            text="Proposal task",
            project_id=project_id,
            task_type="proposal",
        )
        fetched = db.get_task(task["id"])
        assert fetched is not None
        assert fetched["task_type"] == "proposal"


# --- Default listing excludes proposals ---


class TestProposalFiltering:
    def test_default_listing_excludes_proposals(self, tmp_path: Path):
        db_path, db, project_id = _setup_db(tmp_path)
        db.add_task(text="Regular task", project_id=project_id)
        db.add_task(text="Proposal task", project_id=project_id, task_type="proposal")

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setenv("PT_DB_PATH", str(db_path))
        # Prevent auto-detection from cwd
        monkeypatch.setattr("pt._detect_project_from_cwd", lambda db: None)

        runner = CliRunner()
        result = runner.invoke(tasks_group, ["-p", "test-project"])
        assert result.exit_code == 0
        assert "Regular task" in result.output
        assert "Proposal task" not in result.output
        monkeypatch.undo()

    def test_proposals_flag_shows_only_proposals(self, tmp_path: Path):
        db_path, db, project_id = _setup_db(tmp_path)
        db.add_task(text="Regular task", project_id=project_id)
        db.add_task(text="Proposal task", project_id=project_id, task_type="proposal")

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setenv("PT_DB_PATH", str(db_path))
        monkeypatch.setattr("pt._detect_project_from_cwd", lambda db: None)

        runner = CliRunner()
        result = runner.invoke(tasks_group, ["-p", "test-project", "--proposals"])
        assert result.exit_code == 0
        assert "Proposal task" in result.output
        assert "Regular task" not in result.output
        monkeypatch.undo()


# --- Approve command ---


class TestApproveCommand:
    def test_approve_converts_to_manual(self, tmp_path: Path):
        db_path, db, project_id = _setup_db(tmp_path)
        task = db.add_task(
            text="Proposed feature",
            project_id=project_id,
            task_type="proposal",
        )

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setenv("PT_DB_PATH", str(db_path))

        runner = CliRunner()
        result = runner.invoke(tasks_group, ["approve", str(task["id"])])
        assert result.exit_code == 0
        assert "Approved" in result.output

        updated = db.get_task(task["id"])
        assert updated["task_type"] == "manual"
        # Status should remain unchanged (Backlog)
        assert updated["status"] == "Backlog"
        monkeypatch.undo()

    def test_approve_rejects_non_proposal(self, tmp_path: Path):
        db_path, db, project_id = _setup_db(tmp_path)
        task = db.add_task(text="Regular task", project_id=project_id)

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setenv("PT_DB_PATH", str(db_path))

        runner = CliRunner()
        result = runner.invoke(tasks_group, ["approve", str(task["id"])])
        assert "not a proposal" in result.output
        monkeypatch.undo()

    def test_approve_nonexistent_task(self, tmp_path: Path):
        db_path, db, _ = _setup_db(tmp_path)

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setenv("PT_DB_PATH", str(db_path))

        runner = CliRunner()
        result = runner.invoke(tasks_group, ["approve", "99999"])
        assert "not found" in result.output
        monkeypatch.undo()


# --- Reject command ---


class TestRejectCommand:
    def test_reject_cancels_proposal(self, tmp_path: Path):
        db_path, db, project_id = _setup_db(tmp_path)
        task = db.add_task(
            text="Bad proposal",
            project_id=project_id,
            task_type="proposal",
        )

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setenv("PT_DB_PATH", str(db_path))

        runner = CliRunner()
        result = runner.invoke(tasks_group, ["reject", str(task["id"])])
        assert result.exit_code == 0
        assert "Rejected" in result.output

        updated = db.get_task(task["id"])
        assert updated["status"] == "Cancelled"
        monkeypatch.undo()

    def test_reject_rejects_non_proposal(self, tmp_path: Path):
        db_path, db, project_id = _setup_db(tmp_path)
        task = db.add_task(text="Regular task", project_id=project_id)

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setenv("PT_DB_PATH", str(db_path))

        runner = CliRunner()
        result = runner.invoke(tasks_group, ["reject", str(task["id"])])
        assert "not a proposal" in result.output
        monkeypatch.undo()

    def test_reject_nonexistent_task(self, tmp_path: Path):
        db_path, db, _ = _setup_db(tmp_path)

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setenv("PT_DB_PATH", str(db_path))

        runner = CliRunner()
        result = runner.invoke(tasks_group, ["reject", "99999"])
        assert "not found" in result.output
        monkeypatch.undo()
