"""Database schema for project tracker.

SAFETY POLICY - READ BEFORE MODIFYING:
======================================
1. NEVER use DROP TABLE on tables that may contain data
2. NEVER use DELETE FROM without explicit user confirmation
3. All migrations must be ADDITIVE ONLY (ALTER TABLE ADD COLUMN)
4. If schema is incompatible, REFUSE and print instructions - don't auto-fix
5. Any destructive operation requires:
   - Explicit backup first
   - User confirmation
   - Audit log entry

This policy exists because we lost 94 tasks on 2026-01-27 due to an
auto-migration that dropped tables without backup.
"""

import sqlite3
import sys
import json
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone


class SafetyError(Exception):
    """Raised when a destructive operation is blocked by safety policy."""
    pass


def _safety_backup_tasks(db_path: Path) -> Optional[Path]:
    """Create automatic backup before any schema operation that touches tasks table.

    Returns the backup path if tasks were backed up, None if table was empty/missing.
    This runs BEFORE any migration attempt - even if migration will refuse.
    """
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Check if tasks table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
        if not cursor.fetchone():
            conn.close()
            return None

        # Get all tasks
        cursor.execute("SELECT * FROM tasks")
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return None

        # Convert to list of dicts
        tasks = [dict(row) for row in rows]

        # Create timestamped backup
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"tasks_safety_backup_{timestamp}.json"

        export_data = {
            "backup_type": "safety_auto_backup",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "reason": "Pre-migration safety backup",
            "total_count": len(tasks),
            "tasks": tasks
        }

        with open(backup_path, 'w') as f:
            json.dump(export_data, f, indent=2)

        print(f"🛡️  SAFETY: Auto-backup created: {backup_path} ({len(tasks)} tasks)")
        return backup_path

    except Exception as e:
        print(f"⚠️  Warning: Could not create safety backup: {e}")
        return None

# Add parent directory to path for config import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import DATABASE_PATH


def get_db_path() -> Path:
    """Get the database file path."""
    return DATABASE_PATH


def create_database(db_path: Optional[Path] = None) -> None:
    """Create database with all tables and indexes."""
    if db_path is None:
        db_path = get_db_path()
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 0. Schema Versioning
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            updated_at TEXT NOT NULL
        )
    """)
    
    # 1. Core projects table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            path TEXT NOT NULL,
            status TEXT NOT NULL,
            description TEXT,
            phase TEXT,
            last_modified TEXT,
            created_at TEXT NOT NULL,
            completion_pct INTEGER DEFAULT 0,
            is_infrastructure BOOLEAN DEFAULT 0,
            has_index BOOLEAN DEFAULT 0,
            index_is_valid BOOLEAN DEFAULT 0,
            index_updated_at TEXT,
            project_type TEXT DEFAULT 'standard'
        )
    """)
    
    # Migration: add project_type column
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN project_type TEXT DEFAULT 'standard'")
    except sqlite3.OperationalError:
        pass
    
    # Migration: add is_infrastructure column if it doesn't exist
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN is_infrastructure BOOLEAN DEFAULT 0")
    except sqlite3.OperationalError:
        # Column already exists
        pass
    
    # Migration: add index tracking columns
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN has_index BOOLEAN DEFAULT 0")
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN index_is_valid BOOLEAN DEFAULT 0")
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN index_updated_at TEXT")
    except sqlite3.OperationalError:
        pass
    
    # Migration: add health columns
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN health_score INTEGER")
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN health_grade TEXT")
    except sqlite3.OperationalError:
        pass
    
    # Migration: add scaffolding version tracking columns
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN scaffolding_version TEXT")
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN rules_version TEXT")
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN scaffolding_applied_at TEXT")
    except sqlite3.OperationalError:
        pass
    
    # Scheduled automation
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cron_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            schedule TEXT NOT NULL,
            command TEXT NOT NULL,
            description TEXT,
            last_run TEXT,
            is_active BOOLEAN DEFAULT 1,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """)
    
    # External services
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS service_dependencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            service_name TEXT NOT NULL,
            purpose TEXT,
            cost_monthly REAL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """)
    
    # AI assistance tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            role TEXT,
            notes TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """)
    
    # 2. Kanban tasks table
    # SAFETY: Always backup before ANY operation that might affect tasks
    _safety_backup_tasks(db_path)

    # SAFETY: Check if tasks table exists with data - NEVER drop automatically
    cursor.execute("PRAGMA table_info(tasks)")
    columns = cursor.fetchall()
    if columns:
        # Check for incompatible schema (TEXT id instead of INTEGER)
        id_column = next((c for c in columns if c[1] == 'id'), None)
        if id_column and id_column[2].upper() == 'TEXT':
            # Count existing tasks before refusing
            cursor.execute("SELECT COUNT(*) FROM tasks")
            task_count = cursor.fetchone()[0]
            if task_count > 0:
                print(f"⚠️  SCHEMA INCOMPATIBILITY DETECTED")
                print(f"    Tasks table has TEXT id (old schema) with {task_count} tasks.")
                print(f"    REFUSING to drop table with data.")
                print(f"    To migrate manually:")
                print(f"    1. Export: ./pt tasks export")
                print(f"    2. Backup: cp data/tracker.db data/tracker.db.backup")
                print(f"    3. Run dedicated migration script")
                print(f"    4. Restore from export if needed")
                conn.close()
                raise SafetyError(f"Cannot auto-migrate: {task_count} tasks would be lost. See instructions above.")
            else:
                # Table is empty, safe to recreate (but still log it)
                print("ℹ️  Empty tasks table with old schema detected, will recreate.")
                cursor.execute("DROP TABLE IF EXISTS task_history")
                cursor.execute("DROP TABLE IF EXISTS tasks")

    # Kanban tasks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('Backlog', 'To Do', 'In Progress', 'Review', 'Done')),
            project_id TEXT NOT NULL,
            priority TEXT CHECK(priority IN ('Critical', 'High', 'Medium', 'Low', NULL)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            prompt TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """)
    
    # Migration: add prompt column if it doesn't exist
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN prompt TEXT")
    except sqlite3.OperationalError:
        pass

    # Migration: ensure tasks table has all columns
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN completed_at TEXT")
    except sqlite3.OperationalError:
        pass
    
    # Migration: add title column for short task names
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN title TEXT")
    except sqlite3.OperationalError:
        pass
    
    # Migration: add notes column for freeform text notes
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN notes TEXT")
    except sqlite3.OperationalError:
        pass
    
    # Migration: add commit_sha column for linking to commits/PRs
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN commit_sha TEXT")
    except sqlite3.OperationalError:
        pass
    
    # Migration: add category column for task categorization/tagging
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN category TEXT")
    except sqlite3.OperationalError:
        pass
    
    # Task history table for productivity graphs
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
    
    # ==========================================================================
    # SAFETY: Delete audit log - catches ALL deletions including raw SQL
    # ==========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS delete_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            deleted_id TEXT NOT NULL,
            deleted_data TEXT NOT NULL,
            deleted_at TEXT NOT NULL,
            source TEXT DEFAULT 'unknown'
        )
    """)
    
    # SAFETY TRIGGER: Log all task deletions (catches raw SQL too)
    cursor.execute("DROP TRIGGER IF EXISTS audit_task_delete")
    cursor.execute("""
        CREATE TRIGGER audit_task_delete
        BEFORE DELETE ON tasks
        FOR EACH ROW
        BEGIN
            INSERT INTO delete_audit_log (table_name, deleted_id, deleted_data, deleted_at, source)
            VALUES (
                'tasks',
                OLD.id,
                json_object(
                    'id', OLD.id,
                    'text', OLD.text,
                    'status', OLD.status,
                    'project_id', OLD.project_id,
                    'priority', OLD.priority,
                    'created_at', OLD.created_at,
                    'updated_at', OLD.updated_at,
                    'completed_at', OLD.completed_at
                ),
                datetime('now'),
                'trigger'
            );
        END
    """)
    
    # SAFETY TRIGGER: Log all project deletions
    cursor.execute("DROP TRIGGER IF EXISTS audit_project_delete")
    cursor.execute("""
        CREATE TRIGGER audit_project_delete
        BEFORE DELETE ON projects
        FOR EACH ROW
        BEGIN
            INSERT INTO delete_audit_log (table_name, deleted_id, deleted_data, deleted_at, source)
            VALUES (
                'projects',
                OLD.id,
                json_object(
                    'id', OLD.id,
                    'name', OLD.name,
                    'path', OLD.path,
                    'status', OLD.status,
                    'description', OLD.description
                ),
                datetime('now'),
                'trigger'
            );
        END
    """)
    
    # Create indexes for performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_projects_last_modified ON projects(last_modified DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cron_jobs_project ON cron_jobs(project_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_agents_project ON ai_agents(project_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_service_deps_project ON service_dependencies(project_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_completed ON tasks(completed_at) WHERE completed_at IS NOT NULL")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_timestamp ON task_history(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_project ON task_history(project_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_event ON task_history(event_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_delete_audit_table ON delete_audit_log(table_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_delete_audit_time ON delete_audit_log(deleted_at)")
    
    # Update schema version (current version: 3 - added delete audit triggers)
    cursor.execute("INSERT OR REPLACE INTO schema_version (version, updated_at) VALUES (3, ?)", (datetime.now().isoformat(),))
    
    conn.commit()
    conn.close()


def init_db() -> Path:
    """Initialize database if it doesn't exist."""
    db_path = get_db_path()
    create_database(db_path)
    return db_path


if __name__ == "__main__":
    # For testing
    db_path = init_db()
    print(f"Database created at: {db_path}")
