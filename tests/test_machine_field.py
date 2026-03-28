"""Tests verifying machine designation removal (#5366).

The machine designation system (MacBook/OpenClaw/Both) has been removed.
These tests confirm:
- VALID_MACHINES and validate_machine no longer exist in validation.py
- add_task() no longer accepts a machine parameter
- get_tasks() no longer accepts a machine parameter
- The DB column still exists (governance: never drop columns)
"""

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
from scripts.utils import validation


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
    )
    return manager


class TestMachineRemoved:
    """Verify machine designation code has been removed."""

    def test_valid_machines_constant_removed(self):
        assert not hasattr(validation, "VALID_MACHINES")

    def test_validate_machine_function_removed(self):
        assert not hasattr(validation, "validate_machine")

    def test_validate_task_input_no_machine_param(self):
        """validate_task_input should not accept machine parameter."""
        import inspect
        sig = inspect.signature(validation.validate_task_input)
        assert "machine" not in sig.parameters


class TestTaskWithoutMachine:
    """Tasks should work without machine parameter."""

    def test_create_task_no_machine(self, db):
        task = db.add_task(text="Test task", project_id="test-project")
        assert task["id"] is not None
        # machine column still exists in DB but should be NULL
        assert task.get("machine") is None

    def test_get_tasks_no_machine_filter(self, db):
        """get_tasks() should not accept machine parameter."""
        import inspect
        sig = inspect.signature(db.get_tasks)
        assert "machine" not in sig.parameters

    def test_db_column_still_exists(self, db):
        """The machine column should still exist in the DB (governance rule)."""
        task = db.add_task(text="Column check", project_id="test-project")
        # The column exists, it's just not populated
        assert "machine" in task


class TestProjectWithoutMachine:
    def test_add_project_without_machine(self, db):
        """Projects can be added without machine."""
        db.add_project(
            project_id="new-project",
            name="new-project",
            path="/tmp/new-project",
            status="active",
        )
        project = db.get_project("new-project")
        assert project is not None
        assert project.get("machine") is None
