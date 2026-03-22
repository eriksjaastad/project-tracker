"""Tests for machine designation field (#5236)."""

import os
import sys
import pytest
import tempfile
from pathlib import Path

# Set test mode before imports
os.environ["PT_TEST_MODE"] = "1"

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.db.schema import create_database
from scripts.db.manager import DatabaseManager
from scripts.utils.validation import validate_machine, VALID_MACHINES


@pytest.fixture
def db(tmp_path):
    """Create a test database with a project."""
    db_path = tmp_path / "test.db"
    create_database(db_path)
    manager = DatabaseManager(db_path=db_path)
    manager.add_project(
        project_id="test-project",
        name="test-project",
        path="/tmp/test-project",
        status="active",
        machine="MacBook"
    )
    return manager


class TestValidateMachine:
    def test_valid_values(self):
        for m in VALID_MACHINES:
            is_valid, err = validate_machine(m)
            assert is_valid is True
            assert err is None

    def test_none_is_valid(self):
        is_valid, err = validate_machine(None)
        assert is_valid is True

    def test_invalid_value(self):
        is_valid, err = validate_machine("laptop")
        assert is_valid is False
        assert "Machine must be one of" in err

    def test_case_sensitive(self):
        is_valid, err = validate_machine("macbook")
        assert is_valid is False


class TestTaskMachine:
    def test_create_with_machine(self, db):
        task = db.add_task(text="Test task", project_id="test-project", machine="OpenClaw")
        assert task["machine"] == "OpenClaw"

    def test_create_inherits_from_project(self, db):
        task = db.add_task(text="Test inheritance", project_id="test-project")
        assert task["machine"] == "MacBook"

    def test_create_explicit_overrides_project(self, db):
        task = db.add_task(text="Test override", project_id="test-project", machine="Both")
        assert task["machine"] == "Both"

    def test_filter_by_machine(self, db):
        db.add_task(text="MacBook task", project_id="test-project", machine="MacBook")
        db.add_task(text="OpenClaw task", project_id="test-project", machine="OpenClaw")
        db.add_task(text="Both task", project_id="test-project", machine="Both")

        macbook_tasks = db.get_tasks(machine="MacBook")
        assert all(t["machine"] == "MacBook" for t in macbook_tasks)

        openclaw_tasks = db.get_tasks(machine="OpenClaw")
        assert len(openclaw_tasks) == 1
        assert openclaw_tasks[0]["text"] == "OpenClaw task"

    def test_update_machine(self, db):
        task = db.add_task(text="Update me", project_id="test-project", machine="MacBook")
        db.update_task(task["id"], machine="OpenClaw")
        updated = db.get_task(task["id"])
        assert updated["machine"] == "OpenClaw"

    def test_update_rejects_invalid_machine(self, db):
        task = db.add_task(text="Bad update", project_id="test-project")
        with pytest.raises(ValueError, match="Machine must be one of"):
            db.update_task(task["id"], machine="invalid")


class TestProjectMachine:
    def test_project_machine_set(self, db):
        project = db.get_project("test-project")
        assert project["machine"] == "MacBook"

    def test_update_project_machine(self, db):
        db.update_project("test-project", machine="Both")
        project = db.get_project("test-project")
        assert project["machine"] == "Both"

    def test_scan_preserves_machine(self, db):
        """Verify that re-adding a project (like pt scan does) preserves existing machine."""
        db.update_project("test-project", machine="OpenClaw")
        # Re-add without machine (simulates pt scan)
        db.add_project(
            project_id="test-project",
            name="test-project",
            path="/tmp/test-project",
            status="active",
            machine=None
        )
        project = db.get_project("test-project")
        assert project["machine"] == "OpenClaw"
