"""Database manager for project tracker operations."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from contextlib import contextmanager

from .schema import get_db_path


class DatabaseManager:
    """Manage all database operations."""
    
    def __init__(self, db_path: Optional[Path] = None):
        """Initialize database manager."""
        self.db_path = db_path or get_db_path()
        
    @contextmanager
    def _get_conn(self):
        """Get database connection context manager."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        try:
            yield conn
        finally:
            conn.close()
    
    # ==================== PROJECT OPERATIONS ====================
    
    def add_project(
        self,
        project_id: str,
        name: str,
        path: str,
        status: str,
        description: Optional[str] = None,
        phase: Optional[str] = None,
        last_modified: Optional[str] = None,
        completion_pct: int = 0,
        is_infrastructure: bool = False,
        has_index: bool = False,
        index_is_valid: bool = False,
        index_updated_at: Optional[str] = None
    ) -> None:
        """Add or update a project."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            created_at = datetime.now().isoformat()
            
            cursor.execute("""
                INSERT OR REPLACE INTO projects 
                (id, name, path, status, description, phase, last_modified, created_at, completion_pct, is_infrastructure, has_index, index_is_valid, index_updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (project_id, name, path, status, description, phase, last_modified, created_at, completion_pct, is_infrastructure, has_index, index_is_valid, index_updated_at))
            
            conn.commit()
    
    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get a single project by ID."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_all_projects(self, order_by: str = "last_modified DESC") -> List[Dict[str, Any]]:
        """Get all projects, sorted."""
        # Whitelist allowed order_by values to prevent SQL injection
        allowed_order = {
            "name", "name ASC", "name DESC",
            "status", "status ASC", "status DESC",
            "last_modified", "last_modified ASC", "last_modified DESC",
            "completion_pct", "completion_pct ASC", "completion_pct DESC"
        }
        
        if order_by not in allowed_order:
            raise ValueError(f"Invalid order_by parameter: {order_by}")
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            query = f"SELECT * FROM projects ORDER BY {order_by}"
            cursor.execute(query)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def update_project(self, project_id: str, **kwargs) -> None:
        """Update specific fields of a project."""
        if not kwargs:
            return
        
        # Whitelist allowed fields to prevent SQL injection
        allowed_fields = {
            "name", "path", "status", "phase", "description",
            "completion_pct", "last_modified", "is_infrastructure",
            "has_index", "index_is_valid", "index_updated_at"
        }
        
        # Validate all field names
        for key in kwargs.keys():
            if key not in allowed_fields:
                raise ValueError(f"Invalid field name: {key}")
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            
            # Build UPDATE query dynamically (now safe - fields are whitelisted)
            fields = ", ".join(f"{key} = ?" for key in kwargs.keys())
            values = list(kwargs.values()) + [project_id]
            
            cursor.execute(f"UPDATE projects SET {fields} WHERE id = ?", values)
            conn.commit()
    
    def delete_project(self, project_id: str) -> None:
        """Delete a project and all related data."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            conn.commit()
    
    # ==================== CRON JOB OPERATIONS ====================
    
    def add_cron_job(
        self,
        project_id: str,
        schedule: str,
        command: str,
        description: Optional[str] = None
    ) -> None:
        """Add a cron job for a project."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO cron_jobs (project_id, schedule, command, description)
                VALUES (?, ?, ?, ?)
            """, (project_id, schedule, command, description))
            conn.commit()
    
    def get_cron_jobs(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get cron jobs, optionally filtered by project."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if project_id:
                cursor.execute("SELECT * FROM cron_jobs WHERE project_id = ?", (project_id,))
            else:
                cursor.execute("SELECT * FROM cron_jobs")
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def delete_cron_jobs(self, project_id: str) -> None:
        """Delete all cron jobs for a project."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM cron_jobs WHERE project_id = ?", (project_id,))
            conn.commit()
    
    # ==================== AI AGENT OPERATIONS ====================
    
    def add_ai_agent(
        self,
        project_id: str,
        agent_name: str,
        role: Optional[str] = None,
        notes: Optional[str] = None
    ) -> None:
        """Add an AI agent for a project."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ai_agents (project_id, agent_name, role, notes)
                VALUES (?, ?, ?, ?)
            """, (project_id, agent_name, role, notes))
            conn.commit()
    
    def get_ai_agents(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get AI agents, optionally filtered by project."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if project_id:
                cursor.execute("SELECT * FROM ai_agents WHERE project_id = ?", (project_id,))
            else:
                cursor.execute("SELECT * FROM ai_agents")
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def delete_ai_agents(self, project_id: str) -> None:
        """Delete all AI agents for a project."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM ai_agents WHERE project_id = ?", (project_id,))
            conn.commit()
    
    # ==================== SERVICE OPERATIONS ====================
    
    def add_service(
        self,
        project_id: str,
        service_name: str,
        purpose: Optional[str] = None,
        cost_monthly: Optional[float] = None
    ) -> None:
        """Add a service dependency for a project."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO service_dependencies (project_id, service_name, purpose, cost_monthly)
                VALUES (?, ?, ?, ?)
            """, (project_id, service_name, purpose, cost_monthly))
            conn.commit()
    
    def get_services(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get service dependencies, optionally filtered by project."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if project_id:
                cursor.execute("SELECT * FROM service_dependencies WHERE project_id = ?", (project_id,))
            else:
                cursor.execute("SELECT * FROM service_dependencies")
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def delete_services(self, project_id: str) -> None:
        """Delete all services for a project."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM service_dependencies WHERE project_id = ?", (project_id,))
            conn.commit()
    
