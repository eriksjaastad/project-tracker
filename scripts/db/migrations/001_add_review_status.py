#!/usr/bin/env python3
"""
Migration script to add 'Review' status to tasks table.

DEPRECATED: This migration is no longer needed - the 'Review' status is now
included in the base schema. This file is kept for historical reference only.

DO NOT RUN THIS SCRIPT - it contains destructive operations.

If you need to add 'Review' status to an old database:
1. Export tasks: ./pt tasks export
2. Backup database: cp data/tracker.db data/tracker.db.backup
3. The schema.py will handle additive migrations safely
"""

import sqlite3
from pathlib import Path
import sys
from datetime import datetime

# Direct path to database
DATABASE_PATH = Path(__file__).parent.parent.parent / "tracker.db"

def migrate_add_review_status():
    """Migrate database to include 'Review' status in tasks.

    DEPRECATED: This function should NOT be run. See module docstring.
    """
    print("❌ MIGRATION BLOCKED")
    print("   This migration script is deprecated and contains destructive operations.")
    print("   The 'Review' status is now part of the base schema.")
    print("")
    print("   If you need to migrate an old database:")
    print("   1. Export: ./pt tasks export")
    print("   2. Backup: cp data/tracker.db data/tracker.db.backup")
    print("   3. Run: ./pt scan (schema.py handles safe migrations)")
    print("")
    print("   To force run this (DANGEROUS), edit this file and remove the safety block.")
    sys.exit(1)

    # SAFETY BLOCK - code below will not execute
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("📦 Starting migration: Add 'Review' status to tasks")
    print(f"   Database: {DATABASE_PATH}")
    
    # Check if migration is needed
    cursor.execute("PRAGMA table_info(tasks)")
    columns = cursor.fetchall()
    
    # Get current CHECK constraint by inspecting schema
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'")
    result = cursor.fetchone()
    if result:
        schema = result[0]
        if "'Review'" in schema:
            print("✅ Migration already applied. Database is up to date.")
            conn.close()
            return
    
    print("   Backing up tasks and history...")
    
    # 1. Create backup tables
    cursor.execute("""
        CREATE TABLE tasks_backup AS
        SELECT * FROM tasks
    """)
    
    cursor.execute("""
        CREATE TABLE task_history_backup AS
        SELECT * FROM task_history
    """)
    
    task_count = cursor.execute("SELECT COUNT(*) FROM tasks_backup").fetchone()[0]
    history_count = cursor.execute("SELECT COUNT(*) FROM task_history_backup").fetchone()[0]
    
    print(f"   ✓ Backed up {task_count} tasks and {history_count} history entries")
    
    # 2. Drop old tables (CASCADE will drop task_history due to FK)
    print("   Dropping old tables...")
    cursor.execute("DROP TABLE IF EXISTS task_history")
    cursor.execute("DROP TABLE IF EXISTS tasks")
    
    # 3. Create new tables with 'Review' status
    print("   Creating new schema with 'Review' status...")
    cursor.execute("""
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('Backlog', 'To Do', 'In Progress', 'Review', 'Done')),
            project_id TEXT NOT NULL,
            priority TEXT CHECK(priority IN ('Critical', 'High', 'Medium', 'Low', NULL)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """)
    
    cursor.execute("""
        CREATE TABLE task_history (
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
    
    # 4. Restore data from backup
    print("   Restoring data...")
    cursor.execute("""
        INSERT INTO tasks (id, text, status, project_id, priority, created_at, updated_at, completed_at)
        SELECT id, text, status, project_id, priority, created_at, updated_at, completed_at
        FROM tasks_backup
    """)
    
    cursor.execute("""
        INSERT INTO task_history (id, task_id, project_id, event_type, old_status, new_status, timestamp)
        SELECT id, task_id, project_id, event_type, old_status, new_status, timestamp
        FROM task_history_backup
    """)
    
    # 5. Recreate indexes
    print("   Recreating indexes...")
    cursor.execute("CREATE INDEX idx_tasks_project ON tasks(project_id)")
    cursor.execute("CREATE INDEX idx_tasks_status ON tasks(status)")
    cursor.execute("CREATE INDEX idx_tasks_completed ON tasks(completed_at) WHERE completed_at IS NOT NULL")
    cursor.execute("CREATE INDEX idx_history_timestamp ON task_history(timestamp)")
    cursor.execute("CREATE INDEX idx_history_project ON task_history(project_id)")
    cursor.execute("CREATE INDEX idx_history_event ON task_history(event_type)")
    
    # 6. Drop backup tables
    print("   Cleaning up backup tables...")
    cursor.execute("DROP TABLE tasks_backup")
    cursor.execute("DROP TABLE task_history_backup")
    
    # 7. Update schema version
    cursor.execute("INSERT OR REPLACE INTO schema_version (version, updated_at) VALUES (3, ?)", 
                  (datetime.now().isoformat(),))
    
    conn.commit()
    conn.close()
    
    print("✅ Migration complete!")
    print(f"   • Added 'Review' status to tasks workflow")
    print(f"   • Restored {task_count} tasks and {history_count} history entries")
    print(f"   • Updated schema to version 3")
    print("\nYou can now use: Backlog → To Do → In Progress → Review → Done")

if __name__ == "__main__":
    try:
        migrate_add_review_status()
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
