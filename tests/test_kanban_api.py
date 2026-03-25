"""Property-based tests for Kanban board API endpoints.

Feature: kanban-board
Properties tested:
- Property 2: Query Filtering Accuracy (API layer)
- Property 8: Task Edit Persistence
- Property 18: Transaction Rollback on API Error
- Property 19: Database Lock Retry
"""

import pytest
import sqlite3
import tempfile
import time
import threading
import html
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from contextlib import contextmanager
from unittest.mock import patch, MagicMock

from hypothesis import given, strategies as st, assume, settings
from fastapi.testclient import TestClient
from fastapi import FastAPI, HTTPException

from scripts.db.manager import DatabaseManager
from scripts.db.schema import create_database
from scripts.utils.validation import (
    validate_task_input,
    validate_task_text,
    validate_status,
    validate_priority,
    contains_secret
)


def _setup_fresh_database():
    """Create a fresh database for each Hypothesis example.
    
    This function sets up a temporary database with schema and test projects.
    Returns a tuple of (db_path, db_manager, project_ids).
    """
    # Create temporary database file
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = Path(f.name)
    
    # Create database schema
    create_database(db_path)
    
    # Add tasks and task_history tables (align with current schema)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN (
                'Backlog',
                'TRIAGED',
                'READY_FOR_PATCH',
                'To Do',
                'In Progress',
                'PR_READY',
                'Review',
                'Done',
                'Cancelled'
            )),
            project_id TEXT NOT NULL,
            priority TEXT CHECK(priority IN ('Critical', 'High', 'Medium', 'Low', NULL)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            prompt TEXT,
            task_type TEXT NOT NULL DEFAULT 'manual' CHECK(task_type IN ('manual', 'agent')),
            review_comment TEXT,
            parent_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
            blocked_by TEXT,
            sequence_order INTEGER,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            project_id TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK(event_type IN ('created', 'status_changed', 'completed')),
            old_status TEXT,
            new_status TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_completed ON tasks(completed_at) WHERE completed_at IS NOT NULL")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_timestamp ON task_history(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_project ON task_history(project_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_event ON task_history(event_type)")
    
    conn.commit()
    conn.close()
    
    # Create DatabaseManager instance
    db_manager = DatabaseManager(db_path=db_path)
    
    # Create test projects
    projects = [
        ("project-tracker", "Project Tracker", "/path/to/project-tracker"),
        ("image-workflow", "Image Workflow", "/path/to/image-workflow"),
        ("trading-copilot", "Trading Copilot", "/path/to/trading-copilot"),
        ("test-project-1", "Test Project 1", "/path/to/test-project-1"),
        ("test-project-2", "Test Project 2", "/path/to/test-project-2"),
    ]
    
    project_ids = []
    for project_id, name, path in projects:
        db_manager.add_project(
            project_id=project_id,
            name=name,
            path=path,
            status="active"
        )
        project_ids.append(project_id)
    
    return db_path, db_manager, project_ids


def _create_test_app(db_manager: DatabaseManager) -> FastAPI:
    """Create a FastAPI app with task routes for testing."""
    app = FastAPI()
    
    @app.post("/api/tasks")
    async def create_task(task_data: dict):
        """Create a new task."""
        try:
            task = db_manager.add_task(
                text=task_data["text"],
                project_id=task_data["project_id"],
                status=task_data.get("status", "Backlog"),
                priority=task_data.get("priority")
            )
            return task
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/tasks")
    async def list_tasks(project_id: Optional[str] = None, status: Optional[str] = None):
        """List tasks with optional filtering."""
        try:
            tasks = db_manager.get_tasks(project_id=project_id, status=status)
            return {"tasks": tasks, "total": len(tasks)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/tasks/{task_id}")
    async def get_task(task_id: int):
        """Get a single task by ID."""
        task = db_manager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task with ID {task_id} not found")
        return task
    
    @app.patch("/api/tasks/{task_id}")
    async def update_task(task_id: int, updates: dict):
        """Update a task."""
        try:
            task = db_manager.update_task(task_id, **updates)
            return task
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.delete("/api/tasks/{task_id}")
    async def delete_task(task_id: int):
        """Delete a task."""
        try:
            db_manager.delete_task(task_id)
            return {"success": True}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    return app


# Property 2: Query Filtering Accuracy (API Layer)
# For any set of tasks with various projects, statuses, and priorities,
# querying the API with filter parameters should return only tasks matching all specified filters
@given(
    num_tasks=st.integers(min_value=5, max_value=20),
    filter_project_id=st.one_of(st.none(), st.sampled_from(["project-tracker", "image-workflow", "trading-copilot", "test-project-1", "test-project-2"])),
    filter_status=st.one_of(st.none(), st.sampled_from(["Backlog", "To Do", "In Progress", "Done"]))
)
@settings(max_examples=50)
def test_property_2_api_filtering_accuracy(num_tasks, filter_project_id, filter_status):
    """
    Feature: kanban-board, Property 2: Query Filtering Accuracy (API Layer)
    Validates: Requirements 1.4
    
    For any set of tasks with various projects, statuses, and priorities,
    querying the API with filter parameters should return only tasks matching
    all specified filters.
    """
    # Setup fresh database for this example
    db_path, db_manager, test_projects = _setup_fresh_database()
    
    try:
        # Create FastAPI app with routes
        app = _create_test_app(db_manager)
        client = TestClient(app)
        
        # Create a diverse set of tasks via API
        all_projects = ["project-tracker", "image-workflow", "trading-copilot", "test-project-1", "test-project-2"]
        all_statuses = ["Backlog", "To Do", "In Progress", "Done"]
        all_priorities = [None, "Critical", "High", "Medium", "Low"]
        
        created_tasks = []
        
        for i in range(num_tasks):
            project_id = all_projects[i % len(all_projects)]
            status = all_statuses[i % len(all_statuses)]
            priority = all_priorities[i % len(all_priorities)]
            text = f"Test task {i}"
            
            response = client.post("/api/tasks", json={
                "text": text,
                "project_id": project_id,
                "status": status,
                "priority": priority
            })
            
            assert response.status_code == 200, f"Failed to create task: {response.text}"
            created_tasks.append(response.json())
        
        # Query API with filters
        params = {}
        if filter_project_id is not None:
            params["project_id"] = filter_project_id
        if filter_status is not None:
            params["status"] = filter_status
        
        response = client.get("/api/tasks", params=params)
        assert response.status_code == 200, f"Failed to query tasks: {response.text}"
        
        result = response.json()
        results = result["tasks"]
        
        # Verify all results match the filters
        for task in results:
            if filter_project_id is not None:
                assert task["project_id"] == filter_project_id, \
                    f"Task {task['id']} has project_id {task['project_id']}, expected {filter_project_id}"
            
            if filter_status is not None:
                assert task["status"] == filter_status, \
                    f"Task {task['id']} has status {task['status']}, expected {filter_status}"
        
        # Verify we got all matching tasks (completeness check)
        expected_count = sum(
            1 for task in created_tasks
            if (filter_project_id is None or task["project_id"] == filter_project_id)
            and (filter_status is None or task["status"] == filter_status)
        )
        
        assert len(results) == expected_count, \
            f"Expected {expected_count} tasks matching filters, got {len(results)}"
    finally:
        # Cleanup
        db_path.unlink()


# Property 8: Task Edit Persistence
# For any task, editing the task text via API should update the task in the database,
# update the updated_at timestamp, and the changes should persist across reloads
@given(
    initial_text=st.text(min_size=1, max_size=100).map(lambda s: s.strip()).filter(lambda s: len(s) > 0),
    new_text=st.text(min_size=1, max_size=100).map(lambda s: s.strip()).filter(lambda s: len(s) > 0),
    project_id=st.sampled_from(["project-tracker", "image-workflow", "trading-copilot", "test-project-1", "test-project-2"]),
    status=st.sampled_from(["Backlog", "To Do", "In Progress", "Done"]),
    priority=st.one_of(st.none(), st.sampled_from(["Critical", "High", "Medium", "Low"]))
)
@settings(max_examples=100)
def test_property_8_task_edit_persistence(initial_text, new_text, project_id, status, priority):
    """
    Feature: kanban-board, Property 8: Task Edit Persistence
    Validates: Requirements 8.4, 8.5
    
    For any task, editing the task text via API should update the task in the database,
    update the updated_at timestamp, and the changes should persist across reloads.
    """
    # Setup fresh database for this example
    db_path, db_manager, test_projects = _setup_fresh_database()
    
    try:
        # Ensure project exists
        assume(project_id in test_projects)
        
        # Ensure texts don't contain secrets
        is_secret_initial, _ = contains_secret(initial_text)
        is_secret_new, _ = contains_secret(new_text)
        assume(not is_secret_initial and not is_secret_new)
        
        # Ensure texts are different
        assume(initial_text != new_text)
        
        # Create FastAPI app with routes
        app = _create_test_app(db_manager)
        client = TestClient(app)
        
        # Create task via API
        create_response = client.post("/api/tasks", json={
            "text": initial_text,
            "project_id": project_id,
            "status": status,
            "priority": priority
        })
        
        assert create_response.status_code == 200, f"Failed to create task: {create_response.text}"
        created_task = create_response.json()
        task_id = created_task["id"]
        original_updated_at = created_task["updated_at"]
        
        # Wait a small amount to ensure timestamp difference
        time.sleep(0.01)
        
        # Edit task text via API
        update_response = client.patch(f"/api/tasks/{task_id}", json={
            "text": new_text
        })
        
        assert update_response.status_code == 200, f"Failed to update task: {update_response.text}"
        updated_task = update_response.json()
        
        # Verify text was updated
        # Text is sanitized (HTML-escaped) before storage, so compare against escaped version
        assert updated_task["text"] == html.escape(new_text, quote=True), \
            f"Task text not updated. Expected '{html.escape(new_text, quote=True)}', got '{updated_task['text']}'"
        
        # Verify updated_at timestamp changed
        assert updated_task["updated_at"] != original_updated_at, \
            "updated_at timestamp should have changed after edit"
        
        # Verify timestamp is valid ISO format
        datetime.fromisoformat(updated_task["updated_at"])
        
        # Verify other fields unchanged
        assert updated_task["project_id"] == project_id
        assert updated_task["status"] == status
        assert updated_task["priority"] == priority
        assert updated_task["created_at"] == created_task["created_at"]
        
        # Verify persistence: reload task via API
        get_response = client.get(f"/api/tasks/{task_id}")
        assert get_response.status_code == 200, f"Failed to get task: {get_response.text}"
        
        reloaded_task = get_response.json()
        
        # Verify changes persisted
        # Text is sanitized (HTML-escaped) before storage, so compare against escaped version
        assert reloaded_task["text"] == html.escape(new_text, quote=True), \
            f"Task text changes did not persist across reload. Expected '{html.escape(new_text, quote=True)}', got '{reloaded_task['text']}'"
        assert reloaded_task["updated_at"] == updated_task["updated_at"], \
            "updated_at timestamp did not persist"
    finally:
        # Cleanup
        db_path.unlink()


# Property 18: Transaction Rollback on API Error
# For any database write operation that fails mid-transaction via API,
# all changes in that transaction should be rolled back, leaving the database
# in its pre-operation state
@given(
    text=st.text(min_size=1, max_size=100).map(lambda s: s.strip()).filter(lambda s: len(s) > 0),
    project_id=st.sampled_from(["project-tracker", "image-workflow", "trading-copilot", "test-project-1", "test-project-2"]),
    status=st.sampled_from(["Backlog", "To Do", "In Progress", "Done"]),
    priority=st.one_of(st.none(), st.sampled_from(["Critical", "High", "Medium", "Low"]))
)
@settings(max_examples=50)
def test_property_18_transaction_rollback_on_api_error(text, project_id, status, priority):
    """
    Feature: kanban-board, Property 18: Transaction Rollback on API Error
    Validates: Requirements 15.2
    
    For any database write operation that fails mid-transaction via API,
    all changes in that transaction should be rolled back, leaving the database
    in its pre-operation state.
    """
    # Setup fresh database for this example
    db_path, db_manager, test_projects = _setup_fresh_database()
    
    try:
        # Ensure project exists
        assume(project_id in test_projects)
        
        # Ensure text doesn't contain secrets
        is_secret, _ = contains_secret(text)
        assume(not is_secret)
        
        # Create FastAPI app with routes
        app = _create_test_app(db_manager)
        client = TestClient(app)
        
        # Get initial task count
        initial_response = client.get("/api/tasks")
        assert initial_response.status_code == 200
        initial_tasks = initial_response.json()["tasks"]
        initial_count = len(initial_tasks)
        
        # Create a task successfully first
        create_response = client.post("/api/tasks", json={
            "text": text,
            "project_id": project_id,
            "status": status,
            "priority": priority
        })
        
        assert create_response.status_code == 200
        created_task = create_response.json()
        task_id = created_task["id"]
        
        # Verify task was created
        verify_response = client.get("/api/tasks")
        assert verify_response.status_code == 200
        verify_tasks = verify_response.json()["tasks"]
        assert len(verify_tasks) == initial_count + 1
        
        # Now simulate a transaction failure by patching _get_conn to return
        # a connection whose commit method raises an error when UPDATE statements
        # have been executed. This is more robust than counting calls since
        # update_task calls _get_conn multiple times internally.
        original_get_conn = db_manager._get_conn
        
        @contextmanager
        def failing_get_conn(self):
            """Simulate a failure during commit for UPDATE operations."""
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.row_factory = sqlite3.Row
            
            # Track if UPDATE was executed in this connection context
            has_update = [False]
            
            # Wrap cursor.execute to detect UPDATE statements
            original_cursor = conn.cursor
            original_commit = conn.commit
            
            def wrapped_cursor():
                cursor = original_cursor()
                original_execute = cursor.execute
                
                def execute_wrapper(sql, *args):
                    sql_upper = sql.upper().strip()
                    # Mark that we're executing an UPDATE in this connection
                    if sql_upper.startswith("UPDATE"):
                        has_update[0] = True
                    return original_execute(sql, *args)
                
                cursor.execute = execute_wrapper
                return cursor
            
            def failing_commit():
                """Raise error on commit if UPDATE was executed in this connection."""
                if has_update[0]:
                    raise sqlite3.OperationalError("Simulated database error during commit")
                return original_commit()
            
            conn.cursor = wrapped_cursor
            conn.commit = failing_commit
            
            try:
                yield conn
                conn.commit()
            except sqlite3.OperationalError:
                # Rollback on error
                conn.rollback()
                raise
            finally:
                conn.close()
        
        # Patch the connection method to simulate failure
        db_manager._get_conn = failing_get_conn.__get__(db_manager, DatabaseManager)
        
        # Attempt to update task via API - should fail
        update_response = client.patch(f"/api/tasks/{task_id}", json={
            "text": "This should not persist"
        })
        
        # Should get an error response
        assert update_response.status_code in [400, 500], \
            f"Expected error response, got {update_response.status_code}"
        
        # Restore original method
        db_manager._get_conn = original_get_conn
        
        # Verify database state unchanged (transaction rolled back)
        final_response = client.get("/api/tasks")
        assert final_response.status_code == 200
        final_tasks = final_response.json()["tasks"]
        
        # Task count should be unchanged
        assert len(final_tasks) == initial_count + 1, \
            "Task count changed after failed transaction"
        
        # Verify task text was not updated (rollback worked)
        task_response = client.get(f"/api/tasks/{task_id}")
        assert task_response.status_code == 200
        task = task_response.json()
        
        # Text is sanitized (HTML-escaped) before storage, so compare against escaped version
        assert task["text"] == html.escape(text, quote=True), \
            f"Task text was modified despite transaction rollback. Expected '{html.escape(text, quote=True)}', got '{task['text']}'"
    finally:
        # Cleanup
        db_path.unlink()


# Property 19: Database Lock Retry
# For any database operation that encounters a lock via API,
# the system should retry with exponential backoff until success or max retries reached
@given(
    text=st.text(min_size=1, max_size=100).map(lambda s: s.strip()).filter(lambda s: len(s) > 0),
    project_id=st.sampled_from(["project-tracker", "image-workflow", "trading-copilot", "test-project-1", "test-project-2"]),
    status=st.sampled_from(["Backlog", "To Do", "In Progress", "Done"]),
    priority=st.one_of(st.none(), st.sampled_from(["Critical", "High", "Medium", "Low"]))
)
@settings(max_examples=1)
def test_property_19_database_lock_retry(text, project_id, status, priority):
    """
    Feature: kanban-board, Property 19: Database Lock Retry
    Validates: Requirements 15.5
    
    For any database operation that encounters a lock via API,
    the system should retry with exponential backoff until success or max retries reached.
    """
    # Setup fresh database for this example
    db_path, db_manager, test_projects = _setup_fresh_database()
    
    try:
        # Ensure project exists
        assume(project_id in test_projects)
        
        # Ensure text doesn't contain secrets
        is_secret, _ = contains_secret(text)
        assume(not is_secret)
        
        # Create FastAPI app with routes
        app = _create_test_app(db_manager)
        client = TestClient(app)
        
        # Create a task first
        create_response = client.post("/api/tasks", json={
            "text": text,
            "project_id": project_id,
            "status": status,
            "priority": priority
        })
        
        assert create_response.status_code == 200
        created_task = create_response.json()
        task_id = created_task["id"]
        
        # Simulate database lock by holding a connection
        lock_conn = None
        release_thread = None
        original_sleep = time.sleep
        sleep_calls = []
        release_event = threading.Event()
        
        try:
            lock_conn = sqlite3.connect(db_manager.db_path, check_same_thread=False)
            lock_conn.execute("BEGIN EXCLUSIVE TRANSACTION")
            
            def mock_sleep(seconds):
                """Mock sleep that records calls but uses real delay."""
                sleep_calls.append(seconds)
                if not release_event.is_set():
                    release_event.set()
                original_sleep(seconds)
            
            # Start a thread that will release the lock after first retry sleep (or timeout)
            def release_lock_after_delay():
                release_event.wait(timeout=0.2)
                if lock_conn:
                    try:
                        lock_conn.rollback()
                        lock_conn.close()
                    except (sqlite3.Error, OSError):
                        pass
            
            release_thread = threading.Thread(target=release_lock_after_delay)
            release_thread.start()
            
            original_get_conn = db_manager._get_conn
            
            @contextmanager
            def get_conn_with_zero_timeout(self):
                conn = sqlite3.connect(self.db_path, timeout=0.0)
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("PRAGMA journal_mode = WAL")
                conn.row_factory = sqlite3.Row
                try:
                    yield conn
                    conn.commit()
                finally:
                    conn.close()
            
            # Patch connection to use timeout=0 to force lock errors and time.sleep to track backoff
            db_manager._get_conn = get_conn_with_zero_timeout.__get__(db_manager, DatabaseManager)
            
            with patch('time.sleep', side_effect=mock_sleep):
                # Attempt to update task via API - should retry and eventually succeed
                update_response = client.patch(f"/api/tasks/{task_id}", json={
                    "text": "Updated with retry"
                }, timeout=2.0)
            
            # Should eventually succeed (lock released after retry)
            assert update_response.status_code == 200, \
                f"Update should succeed after retries. Got {update_response.status_code}: {update_response.text}"
            
            # Verify retry logic was used
            assert sleep_calls, "Expected retry backoff due to database lock"
            
            # Verify task was updated
            task_response = client.get(f"/api/tasks/{task_id}")
            assert task_response.status_code == 200
            task = task_response.json()
            # Text is sanitized (HTML-escaped) before storage, so compare against escaped version
            assert task["text"] == html.escape("Updated with retry", quote=True)
            
        finally:
            db_manager._get_conn = original_get_conn
            # Cleanup lock connection
            if lock_conn:
                try:
                    lock_conn.rollback()
                    lock_conn.close()
                except (sqlite3.Error, OSError):
                    pass
            
            # Wait for release thread to finish
            if release_thread:
                release_thread.join(timeout=0.5)
    finally:
        # Cleanup database file
        db_path.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
