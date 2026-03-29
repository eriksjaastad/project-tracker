"""Database schema for project tracker.

SAFETY POLICY - READ BEFORE MODIFYING:
--------------------------------------
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
import os
import uuid
from pathlib import Path
from typing import Any, Optional
from datetime import datetime, timezone

try:
    from send2trash import send2trash
except ImportError:
    send2trash = None

# Add parent directory to path for config import
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from scripts.config import DATABASE_PATH, DB_FINGERPRINT_PATH, EXTERNAL_BACKUP_DIR
    from scripts.logger import get_logger
except ImportError:
    # Fallback for when scripts/config.py is not in path (e.g. during some test setups)
    DATABASE_PATH = Path("data/tracker.db")
    DB_FINGERPRINT_PATH = Path("data/.db-fingerprint")
    EXTERNAL_BACKUP_DIR = Path.home() / ".project-tracker" / "backups"

    def get_logger(_name: str):
        import logging
        return logging.getLogger(_name)


logger = get_logger(__name__)


class SafetyError(Exception):
    """Raised when a destructive operation is blocked by safety policy."""
    pass


def _prune_safety_backups(backup_dir: Path, keep: int = 10) -> None:
    """Prune old safety backups by sending them to Trash instead of deleting them."""
    safety_files = sorted(backup_dir.glob("tasks_safety_backup_*.json"))
    files_to_prune = safety_files[:-keep]
    if not files_to_prune:
        return

    if send2trash is None:
        logger.warning(
            "send2trash unavailable; retaining old safety backups in %s",
            backup_dir,
        )
        return

    for old in files_to_prune:
        try:
            send2trash(str(old))
        except Exception as e:
            logger.warning("Could not send old safety backup to Trash: %s", e)


def _safety_backup_tasks(db_path: Path) -> Optional[Path]:
    """Create automatic backup before any schema operation that touches tasks table.

    Returns the backup path if tasks were backed up, None if table was empty/missing.
    This runs BEFORE any migration attempt - even if migration will refuse.
    
    SAFETY: Writes to TWO locations:
    1. data/backups/ - local to project
    2. ~/.project-tracker/backups/ - external, survives project directory accidents
    """
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # External backup location - survives project directory accidents
    # Use EXTERNAL_BACKUP_DIR from config
    external_backup_dir = EXTERNAL_BACKUP_DIR
    
    try:
        external_backup_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        # If we can't even create the directory, we might be sandboxed
        # We don't warn here yet, wait until we actually try to write
        pass

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
        backup_filename = f"tasks_safety_backup_{timestamp}.json"
        backup_path = backup_dir / backup_filename

        export_data = {
            "backup_type": "safety_auto_backup",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "reason": "Pre-migration safety backup",
            "total_count": len(tasks),
            "tasks": tasks
        }

        # Write to local backup
        with open(backup_path, 'w') as f:
            json.dump(export_data, f, indent=2)

        # Write to external backup (survives project directory accidents)
        try:
            external_backup_path = external_backup_dir / backup_filename
            with open(external_backup_path, 'w') as f:
                json.dump(export_data, f, indent=2)
        except Exception as e:
            print(f"⚠️  Warning: Could not write external backup: {e}")
            print(f"    (Set PT_EXTERNAL_BACKUP_DIR to a writable path in sandboxed environments)")

        print(f"🛡️  SAFETY: Auto-backup created: {backup_path} ({len(tasks)} tasks)")

        # Rotate: keep only the 10 most recent safety backups per location.
        # Old backups go to Trash so they remain recoverable.
        dirs_to_prune = [backup_dir, external_backup_dir]

        for dir_to_prune in dirs_to_prune:
            if not dir_to_prune.exists():
                continue
            _prune_safety_backups(dir_to_prune)

        return backup_path

    except Exception as e:
        print(f"⚠️  Warning: Could not create safety backup: {e}")
        return None

# The following lines will be removed as they are now at the top


class FreshDatabaseError(Exception):
    """Raised when we detect a fresh database where we expected data."""
    pass


class FingerprintMismatchError(Exception):
    """Raised when the database fingerprint doesn't match the expected value."""
    pass


def _get_or_create_fingerprint(db_path: Path) -> str:
    """Get or create a unique fingerprint for this database.
    
    The fingerprint is stored in both:
    1. A file: data/.db-fingerprint
    2. A _metadata table in the database
    
    If both exist and don't match, we have a problem (database was replaced).
    """
    fingerprint_path = db_path.parent / ".db-fingerprint"
    
    # Check if fingerprint file exists
    file_fingerprint = None
    if fingerprint_path.exists():
        file_fingerprint = fingerprint_path.read_text().strip()
    
    # Check if database has fingerprint in _metadata table
    db_fingerprint = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='_metadata'")
        if cursor.fetchone():
            cursor.execute("SELECT value FROM _metadata WHERE key='fingerprint'")
            row = cursor.fetchone()
            if row:
                db_fingerprint = row[0]
        conn.close()
    except Exception:
        pass
    
    # If both exist and don't match - ERROR!
    if file_fingerprint and db_fingerprint and file_fingerprint != db_fingerprint:
        raise FingerprintMismatchError(
            f"⛔ DATABASE FINGERPRINT MISMATCH!\n"
            f"   File fingerprint:     {file_fingerprint}\n"
            f"   Database fingerprint: {db_fingerprint}\n"
            f"   This means the database file was replaced with a different database.\n"
            f"   To fix:\n"
            f"   - If the current DB is correct: delete {fingerprint_path} and restart\n"
            f"   - If wrong DB: restore from backup in data/backups/ or ~/.project-tracker/backups/"
        )
    
    # If we have a file fingerprint but no DB fingerprint, write it to DB
    if file_fingerprint and not db_fingerprint:
        return file_fingerprint
    
    # If we have a DB fingerprint but no file, write it to file
    if db_fingerprint and not file_fingerprint:
        fingerprint_path.write_text(db_fingerprint)
        return db_fingerprint
    
    # If neither exists, create new fingerprint
    if not file_fingerprint and not db_fingerprint:
        new_fingerprint = str(uuid.uuid4())
        fingerprint_path.write_text(new_fingerprint)
        return new_fingerprint
    
    # Both exist and match
    return file_fingerprint


def _check_fresh_database(db_path: Path) -> None:
    """Check if database looks unexpectedly fresh.
    
    If tasks table exists but is empty, and we're not in test mode,
    this is suspicious - the database may have been replaced.
    """
    # Skip check in test environments
    if os.getenv("PT_TEST_MODE") == "1" or os.getenv("PT_ALLOW_FRESH_DB") == "1":
        return
    
    # Skip check if pytest is running
    if "pytest" in sys.modules:
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if tasks table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
        if not cursor.fetchone():
            conn.close()
            return  # No tasks table yet - this is a truly new database
        
        # Check task and project counts
        cursor.execute("SELECT COUNT(*) FROM tasks")
        task_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM projects")
        project_count = cursor.fetchone()[0]

        history_count = 0
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='task_history'")
        if cursor.fetchone():
            cursor.execute("SELECT COUNT(*) FROM task_history")
            history_count = cursor.fetchone()[0]

        delete_audit_count = 0
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='delete_audit_log'")
        if cursor.fetchone():
            cursor.execute("SELECT COUNT(*) FROM delete_audit_log")
            delete_audit_count = cursor.fetchone()[0]
        conn.close()
        
        if task_count == 0:
            # Check if fingerprint file exists - if so, we expected data!
            fingerprint_path = db_path.parent / ".db-fingerprint"
            if fingerprint_path.exists() and project_count == 0:
                raise FreshDatabaseError(
                    f"⛔ UNEXPECTED FRESH DATABASE DETECTED!\n"
                    f"   Database has tasks table but 0 tasks and 0 projects.\n"
                    f"   Fingerprint file exists - we expected existing data.\n"
                    f"   This suggests the database file was replaced.\n"
                    f"\n"
                    f"   To proceed anyway: PT_ALLOW_FRESH_DB=1 ./pt <command>\n"
                    f"   To restore: check data/backups/ or ~/.project-tracker/backups/\n"
                    f"\n"
                    f"   If this IS intentional (first run after clean install):\n"
                    f"   Delete {fingerprint_path} and try again."
                )

            backup_dir = db_path.parent / "backups"
            prior_task_backups = list(backup_dir.glob("tasks_*.json")) if backup_dir.exists() else []
            suspicious_missing_tasks = history_count > 0 or (bool(prior_task_backups) and delete_audit_count == 0)

            if fingerprint_path.exists() and project_count > 0 and suspicious_missing_tasks:
                raise FreshDatabaseError(
                    f"⛔ SUSPICIOUS EMPTY TASK BOARD DETECTED!\n"
                    f"   Database has 0 tasks but {project_count} projects.\n"
                    f"   Prior task activity exists without a matching delete trail.\n"
                    f"   This suggests tasks may have been wiped while project metadata survived.\n"
                    f"\n"
                    f"   To proceed anyway: PT_ALLOW_FRESH_DB=1 ./pt <command>\n"
                    f"   To restore: check data/backups/ or ~/.project-tracker/backups/"
                )
    except FreshDatabaseError:
        raise
    except Exception as e:
        # Don't block startup for check errors - just warn
        print(f"⚠️  Warning: Could not check database freshness: {e}")


def get_db_path() -> Path:
    """Get the database file path."""
    env_path = os.getenv("PT_DB_PATH")
    return Path(env_path) if env_path else DATABASE_PATH


def ensure_schema(cursor: Any) -> None:
    """Run all DDL migrations against the given cursor.

    This is backend-agnostic — works with both sqlite3 and libsql (Turso).
    All statements are idempotent (CREATE IF NOT EXISTS, ALTER ADD COLUMN
    wrapped in try/except). Safe to run on every startup.
    """
    # 0. Schema Versioning — check if already current to skip 100+ migration queries
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            updated_at TEXT NOT NULL
        )
    """)
    CURRENT_SCHEMA_VERSION = 6
    try:
        cursor.execute("SELECT MAX(version) FROM schema_version")
        row = cursor.fetchone()
        if row and row[0] and row[0] >= CURRENT_SCHEMA_VERSION:
            return  # Schema is current, skip all migrations
    except Exception:
        pass  # Table might be empty or broken — run migrations

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
    except Exception:
        pass
    
    # Migration: add is_infrastructure column if it doesn't exist
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN is_infrastructure BOOLEAN DEFAULT 0")
    except Exception:
        pass
    
    # Migration: add index tracking columns
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN has_index BOOLEAN DEFAULT 0")
    except Exception:
        pass
        
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN index_is_valid BOOLEAN DEFAULT 0")
    except Exception:
        pass
        
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN index_updated_at TEXT")
    except Exception:
        pass
    
    # Migration: add health columns
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN health_score INTEGER")
    except Exception:
        pass
        
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN health_grade TEXT")
    except Exception:
        pass
    
    # Migration: add scaffolding version tracking columns
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN scaffolding_version TEXT")
    except Exception:
        pass
        
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN rules_version TEXT")
    except Exception:
        pass
        
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN scaffolding_applied_at TEXT")
    except Exception:
        pass
    
    # Migration: add autonomous loop tracker fields (Task #4856)
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN tier INTEGER")  # 1=hourly, 2=daily, 3=weekly
    except Exception:
        pass
    
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN healthcheck_cmd TEXT")  # Command to run for health checks
    except Exception:
        pass
    
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN commands_to_run TEXT")  # JSON array of commands for automated fixes
    except Exception:
        pass
    
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN cron_jobs_config TEXT")  # JSON object with cron schedules
    except Exception:
        pass
    
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN template_version_installed TEXT")  # Current scaffolding version
    except Exception:
        pass
    
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN template_version_expected TEXT")  # Expected scaffolding version
    except Exception:
        pass
    
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN drift_status TEXT")  # clean, drift_detected, needs_update
    except Exception:
        pass
    
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN autonomy_level TEXT DEFAULT 'report'")  # report, fix_safe, fix_full
    except Exception:
        pass

    # Migration: add machine designation field (#5236)
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN machine TEXT")  # deprecated: machine designation removed
    except Exception:
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
    # Migration: add machine designation to cron_jobs (must run AFTER CREATE TABLE above)
    try:
        cursor.execute("ALTER TABLE cron_jobs ADD COLUMN machine TEXT")  # deprecated: machine designation removed, web
    except Exception:
        pass  # Column already exists
    
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
            status TEXT NOT NULL CHECK(status IN ('Backlog', 'To Do', 'In Progress', 'Review', 'Done', 'Cancelled', 'TRIAGED', 'READY_FOR_PATCH', 'PR_READY')),
            project_id TEXT NOT NULL,
            priority TEXT CHECK(priority IN ('Critical', 'High', 'Medium', 'Low', NULL)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            prompt TEXT,
            task_type TEXT NOT NULL DEFAULT 'manual' CHECK(task_type IN ('manual', 'agent', 'proposal')),
            review_comment TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """)
    
    # Migration: add prompt column if it doesn't exist
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN prompt TEXT")
    except Exception:
        pass
    
    # Migration: add review_comment column if it doesn't exist
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN review_comment TEXT")
    except Exception:
        pass

    # Migration: ensure tasks table has all columns
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN completed_at TEXT")
    except Exception:
        pass
    
    # Migration: add title column for short task names
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN title TEXT")
    except Exception:
        pass
    
    # Migration: add notes column for freeform text notes
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN notes TEXT")
    except Exception:
        pass
    
    # Migration: add commit_sha column for linking to commits/PRs
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN commit_sha TEXT")
    except Exception:
        pass
    
    # Migration: add category column for task categorization/tagging
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN category TEXT")
    except Exception:
        pass
    
    # Migration: add parent_id column for subtask support (Task #4645)
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN parent_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE")
    except Exception:
        pass
    
    # Migration: add blocked_by column for task dependencies (Task #4579)
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN blocked_by TEXT")  # JSON array of task IDs
    except Exception:
        pass
    
    
    # Migration: add sequence_order column for execution ordering (Task #4645)
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN sequence_order INTEGER")
    except Exception:
        pass

    # Migration: add task_type column for manual/agent tasks
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN task_type TEXT DEFAULT 'manual'")
    except Exception:
        pass

    # Backfill task_type for existing rows
    try:
        cursor.execute("UPDATE tasks SET task_type = 'manual' WHERE task_type IS NULL")
    except Exception:
        pass
    
    # Migration: add autonomous loop metadata fields (Task #4857)
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN source TEXT")  # janitor/librarian/patch-bot/human
    except Exception:
        pass
    
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN severity TEXT")  # P0/P1/P2
    except Exception:
        pass
    
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN detected_at TEXT")  # When issue was first detected
    except Exception:
        pass
    
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN evidence TEXT")  # JSON with logs/errors
    except Exception:
        pass
    
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN allowed_paths TEXT")  # JSON array for Patch-Bot
    except Exception:
        pass
    
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN definition_of_done TEXT")  # Acceptance criteria
    except Exception:
        pass

    # Migration: add machine designation field (#5236)
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN machine TEXT")  # deprecated: machine designation removed
    except Exception:
        pass
    
    # Migration: add 'Cancelled' to status CHECK constraint (Task #4749)
    # SQLite cannot ALTER CHECK constraints, so we recreate the table if needed.
    # Only runs if the old constraint rejects 'Cancelled'.
    try:
        # Test if current schema accepts 'Cancelled'
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'")
        tasks_sql = cursor.fetchone()
        if tasks_sql and "'Cancelled'" not in tasks_sql[0]:
            # Need to recreate table with new CHECK constraint
            cursor.execute("SELECT COUNT(*) FROM tasks")
            task_count = cursor.fetchone()[0]
            print(f"ℹ️  Migrating tasks table CHECK constraint to add 'Cancelled' status ({task_count} tasks)")
            
            cursor.execute("""
                CREATE TABLE tasks_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('Backlog', 'To Do', 'In Progress', 'Review', 'Done', 'Cancelled')),
                    project_id TEXT NOT NULL,
                    priority TEXT CHECK(priority IN ('Critical', 'High', 'Medium', 'Low', NULL)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    prompt TEXT,
                    review_comment TEXT,
                    title TEXT,
                    notes TEXT,
                    commit_sha TEXT,
                    category TEXT,
                    parent_id INTEGER REFERENCES tasks_new(id) ON DELETE CASCADE,
                    blocked_by TEXT,
                    sequence_order INTEGER,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                INSERT INTO tasks_new
                SELECT id, text, status, project_id, priority, created_at, updated_at,
                       completed_at, prompt, review_comment, title, notes, commit_sha,
                       category, parent_id, blocked_by, sequence_order
                FROM tasks
            """)
            cursor.execute("DROP TABLE tasks")
            cursor.execute("ALTER TABLE tasks_new RENAME TO tasks")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_id)")
            print(f"  ✓ Migrated {task_count} tasks successfully")
            
            # CRITICAL: Recreate triggers after migration (they were dropped when we dropped the table)
            cursor.execute("DROP TRIGGER IF EXISTS audit_task_delete")
            cursor.execute("""
                CREATE TRIGGER audit_task_delete
                BEFORE DELETE ON tasks
                WHEN (SELECT enabled FROM _delete_permissions WHERE id = 1) = 1
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
                            'completed_at', OLD.completed_at,
                            'parent_id', OLD.parent_id,
                            'blocked_by', OLD.blocked_by,
                            'sequence_order', OLD.sequence_order
                        ),
                        datetime('now'),
                        'application'
                    );
                END
            """)
            
            cursor.execute("DROP TRIGGER IF EXISTS block_task_delete")
            cursor.execute("""
                CREATE TRIGGER block_task_delete
                BEFORE DELETE ON tasks
                WHEN (SELECT enabled FROM _delete_permissions WHERE id = 1) = 0
                BEGIN
                    INSERT INTO delete_attempt_log (table_name, attempted_at, reason)
                    VALUES ('tasks', datetime('now'), 'blocked: _delete_permissions.enabled = 0');
                    SELECT RAISE(FAIL, 'Task deletes are blocked. Set _delete_permissions.enabled=1 first (application only).');
                END
            """)
            print(f"  ✓ Recreated audit triggers after migration")
    except Exception as e:
        print(f"⚠️  Warning: Could not migrate tasks CHECK constraint: {e}")
    
    # Migration: add 'proposal' to task_type CHECK constraint (Task #5361)
    # SQLite cannot ALTER CHECK constraints, so we recreate the table if needed.
    # Only runs if the current schema has a task_type CHECK that excludes 'proposal'.
    try:
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'")
        tasks_sql = cursor.fetchone()
        if tasks_sql and "task_type" in tasks_sql[0] and "'proposal'" not in tasks_sql[0] and "CHECK" in tasks_sql[0]:
            # The table has a task_type CHECK constraint that doesn't include 'proposal'
            cursor.execute("SELECT COUNT(*) FROM tasks")
            task_count = cursor.fetchone()[0]
            print(f"ℹ️  Migrating tasks table CHECK constraint to add 'proposal' task_type ({task_count} tasks)")

            # Create backup before destructive migration
            cursor.execute("DROP TABLE IF EXISTS tasks_backup_proposal_migration")
            cursor.execute("CREATE TABLE tasks_backup_proposal_migration AS SELECT * FROM tasks")
            print(f"  ✓ Backup created: tasks_backup_proposal_migration ({task_count} rows)")

            # Get current column names dynamically
            cursor.execute("PRAGMA table_info(tasks)")
            all_columns = [col[1] for col in cursor.fetchall()]

            # Build the new table with updated CHECK constraint
            # We include all columns that exist in the current table
            col_defs = []
            for col in all_columns:
                if col == "id":
                    col_defs.append("id INTEGER PRIMARY KEY AUTOINCREMENT")
                elif col == "text":
                    col_defs.append("text TEXT NOT NULL")
                elif col == "status":
                    col_defs.append("status TEXT NOT NULL CHECK(status IN ('Backlog', 'To Do', 'In Progress', 'Review', 'Done', 'Cancelled', 'TRIAGED', 'READY_FOR_PATCH', 'PR_READY'))")
                elif col == "project_id":
                    col_defs.append("project_id TEXT NOT NULL")
                elif col == "priority":
                    col_defs.append("priority TEXT CHECK(priority IN ('Critical', 'High', 'Medium', 'Low', NULL))")
                elif col == "task_type":
                    col_defs.append("task_type TEXT NOT NULL DEFAULT 'manual' CHECK(task_type IN ('manual', 'agent', 'proposal'))")
                elif col == "parent_id":
                    col_defs.append("parent_id INTEGER REFERENCES tasks_new(id) ON DELETE CASCADE")
                else:
                    col_defs.append(f"{col} TEXT")
            col_defs.append("FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE")

            col_list = ", ".join(all_columns)
            create_sql = f"CREATE TABLE tasks_new ({', '.join(col_defs)})"
            cursor.execute(create_sql)
            cursor.execute(f"INSERT INTO tasks_new SELECT {col_list} FROM tasks")
            cursor.execute("DROP TABLE tasks")
            cursor.execute("ALTER TABLE tasks_new RENAME TO tasks")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_id)")
            print(f"  ✓ Migrated {task_count} tasks successfully")

            # CRITICAL: Recreate triggers after migration
            cursor.execute("DROP TRIGGER IF EXISTS audit_task_delete")
            cursor.execute("""
                CREATE TRIGGER audit_task_delete
                BEFORE DELETE ON tasks
                WHEN (SELECT enabled FROM _delete_permissions WHERE id = 1) = 1
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
                            'completed_at', OLD.completed_at,
                            'parent_id', OLD.parent_id,
                            'blocked_by', OLD.blocked_by,
                            'sequence_order', OLD.sequence_order
                        ),
                        datetime('now'),
                        'application'
                    );
                END
            """)

            cursor.execute("DROP TRIGGER IF EXISTS block_task_delete")
            cursor.execute("""
                CREATE TRIGGER block_task_delete
                BEFORE DELETE ON tasks
                WHEN (SELECT enabled FROM _delete_permissions WHERE id = 1) = 0
                BEGIN
                    INSERT INTO delete_attempt_log (table_name, attempted_at, reason)
                    VALUES ('tasks', datetime('now'), 'blocked: _delete_permissions.enabled = 0');
                    SELECT RAISE(FAIL, 'Task deletes are blocked. Set _delete_permissions.enabled=1 first (application only).');
                END
            """)
            print(f"  ✓ Recreated audit triggers after migration")
    except Exception as e:
        print(f"⚠️  Warning: Could not migrate task_type CHECK constraint: {e}")

    # Loop executions table for monitoring autonomous loops
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS loop_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loop_name TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL CHECK(status IN ('running', 'success', 'failed', 'timeout')),
            error_message TEXT,
            cards_created INTEGER DEFAULT 0,
            metadata TEXT
        )
    """)
    
    # Create index on loop_name and started_at for efficient queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_loop_executions_name_time 
        ON loop_executions(loop_name, started_at DESC)
    """)
    
    # Task history table for productivity graphs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            project_id TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK(event_type IN ('created', 'status_changed', 'completed', 'cancelled')),
            old_status TEXT,
            new_status TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """)
    
    # Ideas table for pre-project thoughts (Task #4583)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ideas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    
    # SAFETY: Delete audit log - catches ALL deletions including raw SQL
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

    # SAFETY: Track blocked delete attempts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS delete_attempt_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            attempted_at TEXT NOT NULL,
            reason TEXT NOT NULL
        )
    """)

    # SAFETY: Delete permission flag table
    # Application sets enabled=1 before delete, enabled=0 after
    # Raw SQL cannot delete because enabled defaults to 0
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS _delete_permissions (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            enabled INTEGER NOT NULL DEFAULT 0
        )
    """)
    # Ensure the single row exists
    cursor.execute("INSERT OR IGNORE INTO _delete_permissions (id, enabled) VALUES (1, 0)")

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
    
    # NOTE: Task delete triggers are created after the Cancelled migration (if it runs)
    # to ensure they survive the table recreation. See the migration section above.
    # If migration doesn't run, create them here:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name='audit_task_delete'")
    if not cursor.fetchone():
        # Triggers don't exist, so migration didn't run - create them now
        cursor.execute("DROP TRIGGER IF EXISTS audit_task_delete")
        cursor.execute("""
            CREATE TRIGGER audit_task_delete
            BEFORE DELETE ON tasks
            WHEN (SELECT enabled FROM _delete_permissions WHERE id = 1) = 1
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
                        'completed_at', OLD.completed_at,
                        'parent_id', OLD.parent_id,
                        'blocked_by', OLD.blocked_by,
                        'sequence_order', OLD.sequence_order
                    ),
                    datetime('now'),
                    'application'
                );
            END
        """)

        # SAFETY TRIGGER: Block task deletes unless permission flag is set
        # Uses RAISE(FAIL) not RAISE(ABORT) so the log INSERT isn't rolled back
        cursor.execute("DROP TRIGGER IF EXISTS block_task_delete")
        cursor.execute("""
            CREATE TRIGGER block_task_delete
            BEFORE DELETE ON tasks
            WHEN (SELECT enabled FROM _delete_permissions WHERE id = 1) = 0
            BEGIN
                INSERT INTO delete_attempt_log (table_name, attempted_at, reason)
                VALUES ('tasks', datetime('now'), 'blocked: _delete_permissions.enabled = 0');
                SELECT RAISE(FAIL, 'Task deletes are blocked. Set _delete_permissions.enabled=1 first (application only).');
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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_id) WHERE parent_id IS NOT NULL")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_blocked ON tasks(blocked_by) WHERE blocked_by IS NOT NULL")
    
    # SAFETY: Metadata table for database fingerprinting
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS _metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # Update schema version
    cursor.execute("INSERT OR REPLACE INTO schema_version (version, updated_at) VALUES (6, ?)", (datetime.now().isoformat(),))


def create_database(db_path: Optional[Path] = None) -> None:
    """Create/migrate a LOCAL SQLite database.

    Handles local-only safety checks (fresh-DB guard, file-based fingerprint,
    safety backups) then delegates all DDL to ensure_schema().
    """
    if db_path is None:
        db_path = get_db_path()

    # SAFETY: Check for unexpected fresh database
    if db_path.exists():
        _check_fresh_database(db_path)

    # SAFETY: Backup tasks before any schema operation
    _safety_backup_tasks(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Run all DDL migrations
    ensure_schema(cursor)

    # Local-only: store/validate fingerprint
    fingerprint = _get_or_create_fingerprint(db_path)
    cursor.execute("""
        INSERT OR REPLACE INTO _metadata (key, value, created_at)
        VALUES ('fingerprint', ?, ?)
    """, (fingerprint, datetime.now(timezone.utc).isoformat()))

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
