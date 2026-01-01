"""Database schema for project tracker."""

import sqlite3
from pathlib import Path
from typing import Optional


def get_db_path() -> Path:
    """Get the database file path."""
    db_dir = Path(__file__).parent.parent.parent / "data"
    db_dir.mkdir(exist_ok=True)
    return db_dir / "tracker.db"


def create_database(db_path: Optional[Path] = None) -> None:
    """Create database with all tables and indexes."""
    if db_path is None:
        db_path = get_db_path()
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Core projects table
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
            index_updated_at TEXT
        )
    """)
    
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
    
    # Activity log (DEPRECATED - not providing value, consider removing)
    # cursor.execute("""
    #     CREATE TABLE IF NOT EXISTS work_log (
    #         id INTEGER PRIMARY KEY AUTOINCREMENT,
    #         project_id TEXT NOT NULL,
    #         timestamp TEXT NOT NULL,
    #         event_type TEXT,
    #         details TEXT,
    #         FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    #     )
    # """)
    
    # Create indexes for performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_projects_last_modified 
        ON projects(last_modified DESC)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_projects_status 
        ON projects(status)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_cron_jobs_project 
        ON cron_jobs(project_id)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ai_agents_project 
        ON ai_agents(project_id)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_service_deps_project 
        ON service_dependencies(project_id)
    """)
    
    # cursor.execute("""
    #     CREATE INDEX IF NOT EXISTS idx_work_log_project 
    #     ON work_log(project_id)
    # """)
    
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

