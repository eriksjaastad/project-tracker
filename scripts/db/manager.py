"""Database manager for project tracker operations.

SAFETY POLICY:
==============
All DELETE operations must create a backup BEFORE executing.
This prevents data loss from accidental bulk deletions.
Backups are stored in data/backups/ with timestamps.
"""

import sqlite3
import json
import os
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from contextlib import contextmanager

from .schema import get_db_path
from scripts.utils.validation import (
    validate_task_input,
    validate_task_text,
    validate_status,
    validate_priority,
    contains_secret,
    sanitize_task_text
)
from logger import get_logger

logger = get_logger(__name__)


def _get_backup_dir(db_path: Path) -> Path:
    """Get or create backup directory."""
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


class DatabaseManager:
    """Manage all database operations."""
    
    def __init__(self, db_path: Optional[Path] = None):
        """Initialize database manager."""
        self.db_path = db_path or get_db_path()
        
    @contextmanager
    def _get_conn(self):
        """Get database connection context manager."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")  # Enable WAL mode for concurrent access
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        try:
            yield conn
        finally:
            conn.close()
    
    def _backup_before_delete(
        self,
        table: str,
        where_clause: str,
        params: Tuple,
        reason: str
    ) -> Optional[Path]:
        """Create backup before any DELETE operation.
        
        SAFETY: This method MUST be called before any DELETE FROM statement.
        
        Args:
            table: Table name being deleted from
            where_clause: WHERE clause of the DELETE (e.g., "project_id = ?")
            params: Parameters for the WHERE clause
            reason: Human-readable reason for deletion
            
        Returns:
            Path to backup file if data was backed up, None if no data to backup
        """
        backup_dir = _get_backup_dir(self.db_path)
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            
            # Fetch rows that will be deleted
            query = f"SELECT * FROM {table} WHERE {where_clause}"
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            if not rows:
                return None  # Nothing to backup
            
            # Convert to list of dicts
            data = [dict(row) for row in rows]
            
            # Create timestamped backup
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"{table}_delete_backup_{timestamp}.json"
            
            export_data = {
                "backup_type": "safety_auto_backup",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "table": table,
                "operation": "DELETE",
                "where_clause": where_clause,
                "reason": reason,
                "row_count": len(data),
                "data": data
            }
            
            with open(backup_path, 'w') as f:
                json.dump(export_data, f, indent=2, default=str)
            
            print(f"🛡️  SAFETY: Backup created before delete: {backup_path.name} ({len(data)} rows)")
            return backup_path
    
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
        index_updated_at: Optional[str] = None,
        health_score: Optional[int] = None,
        health_grade: Optional[str] = None,
        project_type: str = 'standard',
        scaffolding_version: Optional[str] = None,
        rules_version: Optional[str] = None,
        scaffolding_applied_at: Optional[str] = None
    ) -> None:
        """Add or update a project."""
        with self._get_conn() as conn:
            cursor = conn.cursor()

            self._add_project_with_cursor(
                cursor=cursor,
                project_id=project_id,
                name=name,
                path=path,
                status=status,
                description=description,
                phase=phase,
                last_modified=last_modified,
                completion_pct=completion_pct,
                is_infrastructure=is_infrastructure,
                has_index=has_index,
                index_is_valid=index_is_valid,
                index_updated_at=index_updated_at,
                health_score=health_score,
                health_grade=health_grade,
                project_type=project_type,
                scaffolding_version=scaffolding_version,
                rules_version=rules_version,
                scaffolding_applied_at=scaffolding_applied_at
            )

            conn.commit()

    def _add_project_with_cursor(
        self,
        cursor: sqlite3.Cursor,
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
        index_updated_at: Optional[str] = None,
        health_score: Optional[int] = None,
        health_grade: Optional[str] = None,
        project_type: str = 'standard',
        scaffolding_version: Optional[str] = None,
        rules_version: Optional[str] = None,
        scaffolding_applied_at: Optional[str] = None
    ) -> None:
        """Add or update a project using an existing cursor."""
        # 🛡️ Preserve created_at, health_score, and health_grade on update
        cursor.execute("SELECT created_at, health_score, health_grade FROM projects WHERE id = ?", (project_id,))
        existing = cursor.fetchone()

        created_at = existing["created_at"] if existing else datetime.now().isoformat()

        # Use provided health data or preserve existing
        final_health_score = health_score if health_score is not None else (existing["health_score"] if existing else None)
        final_health_grade = health_grade if health_grade is not None else (existing["health_grade"] if existing else None)

        # CRITICAL FIX: Use ON CONFLICT instead of INSERT OR REPLACE
        # INSERT OR REPLACE does DELETE + INSERT, which triggers ON DELETE CASCADE
        # and wipes all tasks. ON CONFLICT DO UPDATE modifies in-place, no cascade.
        cursor.execute("""
            INSERT INTO projects
            (id, name, path, status, description, phase, last_modified, created_at, completion_pct,
             is_infrastructure, has_index, index_is_valid, index_updated_at, health_score, health_grade, project_type,
             scaffolding_version, rules_version, scaffolding_applied_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                path = excluded.path,
                status = excluded.status,
                description = excluded.description,
                phase = excluded.phase,
                last_modified = excluded.last_modified,
                completion_pct = excluded.completion_pct,
                is_infrastructure = excluded.is_infrastructure,
                has_index = excluded.has_index,
                index_is_valid = excluded.index_is_valid,
                index_updated_at = excluded.index_updated_at,
                health_score = excluded.health_score,
                health_grade = excluded.health_grade,
                project_type = excluded.project_type,
                scaffolding_version = excluded.scaffolding_version,
                rules_version = excluded.rules_version,
                scaffolding_applied_at = excluded.scaffolding_applied_at
        """, (project_id, name, path, status, description, phase, last_modified, created_at, completion_pct,
              is_infrastructure, has_index, index_is_valid, index_updated_at, final_health_score, final_health_grade, project_type,
              scaffolding_version, rules_version, scaffolding_applied_at))
    
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
            "has_index", "index_is_valid", "index_updated_at",
            "health_score", "health_grade", "project_type"
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
    
    def update_health(self, project_id: str, score: int, grade: str) -> None:
        """Update health_score and health_grade for a project."""
        # 🛡️ Input validation
        if not isinstance(score, int) or not (0 <= score <= 100):
            raise ValueError(f"score must be int 0-100, got: {score}")
        if grade not in {"A", "B", "C", "D", "F"}:
            raise ValueError(f"grade must be A-F, got: {grade}")
            
        with self._get_conn() as conn:
            cursor = conn.cursor()
            self._update_health_with_cursor(cursor, project_id, score, grade)
            conn.commit()

    def _update_health_with_cursor(self, cursor: sqlite3.Cursor, project_id: str, score: int, grade: str) -> None:
        """Update health_score and health_grade using an existing cursor."""
        cursor.execute("""
            UPDATE projects 
            SET health_score = ?, health_grade = ?
            WHERE id = ?
        """, (score, grade, project_id))
    
    def delete_project(self, project_id: str) -> None:
        """Delete a project and all related data."""
        # 🛡️ SAFETY: Backup before delete
        self._backup_before_delete(
            table="projects",
            where_clause="id = ?",
            params=(project_id,),
            reason=f"Deleting project: {project_id}"
        )
        # Also backup related data (cascading deletes)
        self._backup_before_delete("tasks", "project_id = ?", (project_id,), f"Cascade from project delete: {project_id}")
        self._backup_before_delete("cron_jobs", "project_id = ?", (project_id,), f"Cascade from project delete: {project_id}")
        self._backup_before_delete("ai_agents", "project_id = ?", (project_id,), f"Cascade from project delete: {project_id}")
        self._backup_before_delete("service_dependencies", "project_id = ?", (project_id,), f"Cascade from project delete: {project_id}")
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            try:
                # Enable delete permission (project delete cascades to tasks)
                cursor.execute("UPDATE _delete_permissions SET enabled = 1 WHERE id = 1")
                cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
                conn.commit()
            finally:
                # Always disable delete permission after
                cursor.execute("UPDATE _delete_permissions SET enabled = 0 WHERE id = 1")
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
        # 🛡️ SAFETY: Backup before delete
        self._backup_before_delete(
            table="cron_jobs",
            where_clause="project_id = ?",
            params=(project_id,),
            reason=f"Deleting cron jobs for project: {project_id}"
        )
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM cron_jobs WHERE project_id = ?", (project_id,))
            conn.commit()

    def _sync_cron_jobs_with_cursor(
        self,
        cursor: sqlite3.Cursor,
        project_id: str,
        cron_jobs: List[Dict[str, Any]],
        allow_deletes: bool = True
    ) -> Dict[str, int]:
        """Sync cron jobs for a project using an existing cursor."""
        existing = cursor.execute(
            "SELECT id, schedule, command, description FROM cron_jobs WHERE project_id = ?",
            (project_id,)
        ).fetchall()

        existing_by_key = {(row["schedule"], row["command"]): row for row in existing}
        desired_keys = set()
        added = updated = deleted = 0

        for job in cron_jobs or []:
            schedule = (job.get("schedule") or "").strip()
            command = (job.get("command") or "").strip()
            if not schedule or not command:
                continue
            description = job.get("description")
            key = (schedule, command)
            desired_keys.add(key)

            existing_row = existing_by_key.get(key)
            if existing_row:
                if existing_row["description"] != description:
                    cursor.execute(
                        "UPDATE cron_jobs SET description = ? WHERE id = ?",
                        (description, existing_row["id"])
                    )
                    updated += 1
            else:
                cursor.execute(
                    "INSERT INTO cron_jobs (project_id, schedule, command, description) VALUES (?, ?, ?, ?)",
                    (project_id, schedule, command, description)
                )
                added += 1

        if allow_deletes:
            delete_ids = [row["id"] for row in existing if (row["schedule"], row["command"]) not in desired_keys]
            if delete_ids:
                # 🛡️ SAFETY: Backup before delete
                self._backup_before_delete(
                    table="cron_jobs",
                    where_clause="project_id = ?",
                    params=(project_id,),
                    reason=f"Sync cron jobs - prune stale ({project_id})"
                )
                cursor.execute(
                    f"DELETE FROM cron_jobs WHERE id IN ({','.join('?' for _ in delete_ids)})",
                    delete_ids
                )
                deleted = cursor.rowcount or 0

        return {"added": added, "updated": updated, "deleted": deleted}
    
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
        # 🛡️ SAFETY: Backup before delete
        self._backup_before_delete(
            table="ai_agents",
            where_clause="project_id = ?",
            params=(project_id,),
            reason=f"Deleting AI agents for project: {project_id}"
        )
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM ai_agents WHERE project_id = ?", (project_id,))
            conn.commit()

    def _sync_ai_agents_with_cursor(
        self,
        cursor: sqlite3.Cursor,
        project_id: str,
        agents: List[Dict[str, Any]],
        allow_deletes: bool = True
    ) -> Dict[str, int]:
        """Sync AI agents for a project using an existing cursor."""
        existing = cursor.execute(
            "SELECT id, agent_name, role, notes FROM ai_agents WHERE project_id = ?",
            (project_id,)
        ).fetchall()

        existing_by_name = {row["agent_name"]: row for row in existing}
        desired_names = set()
        added = updated = deleted = 0

        for agent in agents or []:
            agent_name = (agent.get("agent_name") or "").strip()
            if not agent_name:
                continue
            desired_names.add(agent_name)
            role = agent.get("role")

            existing_row = existing_by_name.get(agent_name)
            if existing_row:
                if existing_row["role"] != role:
                    cursor.execute(
                        "UPDATE ai_agents SET role = ? WHERE id = ?",
                        (role, existing_row["id"])
                    )
                    updated += 1
            else:
                cursor.execute(
                    "INSERT INTO ai_agents (project_id, agent_name, role) VALUES (?, ?, ?)",
                    (project_id, agent_name, role)
                )
                added += 1

        if allow_deletes:
            delete_ids = [row["id"] for row in existing if row["agent_name"] not in desired_names]
            if delete_ids:
                # 🛡️ SAFETY: Backup before delete
                self._backup_before_delete(
                    table="ai_agents",
                    where_clause="project_id = ?",
                    params=(project_id,),
                    reason=f"Sync AI agents - prune stale ({project_id})"
                )
                cursor.execute(
                    f"DELETE FROM ai_agents WHERE id IN ({','.join('?' for _ in delete_ids)})",
                    delete_ids
                )
                deleted = cursor.rowcount or 0

        return {"added": added, "updated": updated, "deleted": deleted}
    
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
        # 🛡️ SAFETY: Backup before delete
        self._backup_before_delete(
            table="service_dependencies",
            where_clause="project_id = ?",
            params=(project_id,),
            reason=f"Deleting services for project: {project_id}"
        )
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM service_dependencies WHERE project_id = ?", (project_id,))
            conn.commit()

    def _sync_services_with_cursor(
        self,
        cursor: sqlite3.Cursor,
        project_id: str,
        services: List[Dict[str, Any]],
        allow_deletes: bool = True
    ) -> Dict[str, int]:
        """Sync services for a project using an existing cursor."""
        existing = cursor.execute(
            "SELECT id, service_name, purpose, cost_monthly FROM service_dependencies WHERE project_id = ?",
            (project_id,)
        ).fetchall()

        existing_by_name = {row["service_name"]: row for row in existing}
        desired_names = set()
        added = updated = deleted = 0

        for service in services or []:
            service_name = (service.get("service_name") or "").strip()
            if not service_name:
                continue
            desired_names.add(service_name)
            purpose = service.get("purpose")
            cost_monthly = service.get("cost_monthly")

            existing_row = existing_by_name.get(service_name)
            if existing_row:
                if existing_row["purpose"] != purpose or existing_row["cost_monthly"] != cost_monthly:
                    cursor.execute(
                        "UPDATE service_dependencies SET purpose = ?, cost_monthly = ? WHERE id = ?",
                        (purpose, cost_monthly, existing_row["id"])
                    )
                    updated += 1
            else:
                cursor.execute(
                    "INSERT INTO service_dependencies (project_id, service_name, purpose, cost_monthly) VALUES (?, ?, ?, ?)",
                    (project_id, service_name, purpose, cost_monthly)
                )
                added += 1

        if allow_deletes:
            delete_ids = [row["id"] for row in existing if row["service_name"] not in desired_names]
            if delete_ids:
                # 🛡️ SAFETY: Backup before delete
                self._backup_before_delete(
                    table="service_dependencies",
                    where_clause="project_id = ?",
                    params=(project_id,),
                    reason=f"Sync services - prune stale ({project_id})"
                )
                cursor.execute(
                    f"DELETE FROM service_dependencies WHERE id IN ({','.join('?' for _ in delete_ids)})",
                    delete_ids
                )
                deleted = cursor.rowcount or 0

        return {"added": added, "updated": updated, "deleted": deleted}
    
    # ==================== ACTIVITY FEED ====================
    
    def get_activity(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent activity from the audit log (Interface placeholder)."""
        # TODO: Implement reading from WARDEN_LOG.yaml
        return []
    
    # ==================== TASK OPERATIONS ====================
    
    def add_task(
        self,
        text: str,
        project_id: str,
        status: str = "Backlog",
        priority: Optional[str] = None,
        prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new task.
        
        Args:
            text: Task description (1-1000 characters)
            project_id: Project identifier
            status: Task status (default: "Backlog")
            priority: Task priority (optional)
            prompt: Structured execution instructions for agents (optional)
            
        Returns:
            Task dictionary with all fields including generated id and timestamps
            
        Raises:
            ValueError: If validation fails (invalid input, secret detected, etc.)
        """
        # Comprehensive validation including secret detection
        is_valid, error_message = validate_task_input(
            text=text,
            project_id=project_id,
            status=status,
            priority=priority,
            db_manager=self
        )
        if not is_valid:
            raise ValueError(error_message)
        
        # Sanitize text to prevent XSS attacks
        sanitized_text = sanitize_task_text(text)
        
        now = datetime.now().isoformat()
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            
            # Insert task with sanitized text
            cursor.execute("""
                INSERT INTO tasks (text, status, project_id, priority, created_at, updated_at, completed_at, prompt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (sanitized_text, status, project_id, priority, now, now, None if status != "Done" else now, prompt))
            
            task_id = cursor.lastrowid
            
            # Record history entry for creation
            cursor.execute("""
                INSERT INTO task_history (task_id, project_id, event_type, old_status, new_status, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (task_id, project_id, "created", None, status, now))
            
            conn.commit()
            
            # Return the created task
            return self.get_task(task_id)
    
    def get_tasks(
        self,
        project_id: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get tasks with optional filtering.

        Args:
            project_id: Filter by project ID (optional)
            status: Filter by status (optional)

        Returns:
            List of task dictionaries
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM tasks WHERE 1=1"
            params = []

            if project_id:
                query += " AND project_id = ?"
                params.append(project_id)

            if status:
                query += " AND status = ?"
                params.append(status)

            query += " ORDER BY CASE priority WHEN 'Critical' THEN 0 WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 WHEN 'Low' THEN 3 ELSE 4 END, created_at DESC"

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Get a single task by ID.
        
        Args:
            task_id: Task ID
            
        Returns:
            Task dictionary or None if not found
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def update_task(
        self,
        task_id: int,
        **updates
    ) -> Dict[str, Any]:
        """Update task fields.
        
        Args:
            task_id: Task ID
            **updates: Fields to update (text, status, priority)
            
        Returns:
            Updated task dictionary
            
        Raises:
            ValueError: If task not found or invalid field values
        """
        if not updates:
            return self.get_task(task_id)
        
        # Whitelist allowed fields
        allowed_fields = {"text", "status", "priority", "prompt"}
        for key in updates.keys():
            if key not in allowed_fields:
                raise ValueError(f"Invalid field name: {key}. Allowed: {allowed_fields}")
        
        # Get existing task
        existing_task = self.get_task(task_id)
        if not existing_task:
            raise ValueError(f"Task with ID {task_id} not found")
        
        # Validate and sanitize text if provided (includes secret detection)
        if "text" in updates:
            text = updates["text"]
            # Validate text length
            is_valid, error_message = validate_task_text(text)
            if not is_valid:
                raise ValueError(error_message)
            # Check for secrets
            is_secret, pattern = contains_secret(text)
            if is_secret:
                raise ValueError(f"Task text contains potential secret pattern: {pattern}")
            # Sanitize text to prevent XSS attacks
            updates["text"] = sanitize_task_text(text)
        
        # Validate status if provided
        if "status" in updates:
            is_valid, error_message = validate_status(updates["status"])
            if not is_valid:
                raise ValueError(error_message)
        
        # Validate priority if provided
        if "priority" in updates:
            is_valid, error_message = validate_priority(updates["priority"])
            if not is_valid:
                raise ValueError(error_message)
        
        now = datetime.now().isoformat()
        old_status = existing_task["status"]
        new_status = updates.get("status", old_status)

        # Require prompt before moving to In Progress
        if new_status == "In Progress":
            prompt_value = updates.get("prompt")
            if prompt_value is None:
                prompt_value = existing_task.get("prompt")
            if not prompt_value:
                raise ValueError("Cannot start task without a prompt. Add execution instructions first.")
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            
            # Build UPDATE query
            fields = []
            values = []
            
            for key, value in updates.items():
                fields.append(f"{key} = ?")
                values.append(value)
            
            # Always update updated_at
            fields.append("updated_at = ?")
            values.append(now)
            
            # Set completed_at if moving to Done
            if new_status == "Done" and old_status != "Done":
                fields.append("completed_at = ?")
                values.append(now)
            elif new_status != "Done" and old_status == "Done":
                # Clear completed_at if moving away from Done
                fields.append("completed_at = ?")
                values.append(None)
            
            values.append(task_id)
            
            query = f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?"
            cursor.execute(query, values)
            
            # Record history entry if status changed
            if old_status != new_status:
                event_type = "completed" if new_status == "Done" else "status_changed"
                cursor.execute("""
                    INSERT INTO task_history (task_id, project_id, event_type, old_status, new_status, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (task_id, existing_task["project_id"], event_type, old_status, new_status, now))
            
            conn.commit()
            
            # Return updated task
            return self.get_task(task_id)

    def get_subtasks(self, parent_id: int) -> List[Dict[str, Any]]:
        """Get all subtasks of a parent task."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM tasks
                WHERE parent_id = ?
                ORDER BY sequence_order ASC, created_at ASC
            """, (parent_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_subtask_progress(self, parent_id: int) -> Dict[str, Any]:
        """Get completion progress for a parent task's subtasks."""
        subtasks = self.get_subtasks(parent_id)
        total = len(subtasks)
        done = len([t for t in subtasks if t["status"] == "Done"])
        return {
            "total": total,
            "done": done,
            "percent": int(done / total * 100) if total > 0 else 0
        }

    def get_blocking_tasks(self, task_id: int) -> List[Dict[str, Any]]:
        """Get tasks that are blocking this task from starting."""
        task = self.get_task(task_id)
        if not task or not task.get("blocked_by"):
            return []

        try:
            blocked_by_ids = json.loads(task["blocked_by"])
        except (json.JSONDecodeError, TypeError):
            return []

        results = []
        for tid in blocked_by_ids:
            blocking_task = self.get_task(tid)
            if blocking_task:
                results.append(blocking_task)
        return results

    def get_blocked_tasks(self, task_id: int) -> List[Dict[str, Any]]:
        """Get tasks that are blocked by this task (reverse lookup)."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM tasks
                WHERE blocked_by IS NOT NULL
            """)

            results = []
            for row in cursor.fetchall():
                task = dict(row)
                if task.get("blocked_by"):
                    try:
                        blocked_by = json.loads(task["blocked_by"])
                        if task_id in blocked_by:
                            results.append(task)
                    except (json.JSONDecodeError, TypeError):
                        continue
            return results

    def is_blocked(self, task_id: int) -> Tuple[bool, List[int]]:
        """Check if task is blocked by incomplete tasks."""
        blocking = self.get_blocking_tasks(task_id)
        incomplete = [t["id"] for t in blocking if t["status"] != "Done"]
        return (len(incomplete) > 0, incomplete)
    
    def delete_task(self, task_id: int) -> None:
        """Delete a task.

        Args:
            task_id: Task ID

        Raises:
            ValueError: If task not found
        """
        # Verify task exists
        if not self.get_task(task_id):
            raise ValueError(f"Task with ID {task_id} not found")

        self._ensure_delete_allowed(operation=f"delete_task:{task_id}")

        # 🛡️ SAFETY: Backup before delete
        self._backup_before_delete(
            table="tasks",
            where_clause="id = ?",
            params=(task_id,),
            reason=f"Deleting task: {task_id}"
        )

        with self._get_conn() as conn:
            cursor = conn.cursor()
            try:
                # Enable delete permission (triggers check this flag)
                cursor.execute("UPDATE _delete_permissions SET enabled = 1 WHERE id = 1")
                # Foreign key cascade will delete related task_history entries
                cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
                conn.commit()
            finally:
                # Always disable delete permission after
                cursor.execute("UPDATE _delete_permissions SET enabled = 0 WHERE id = 1")
                conn.commit()

    def delete_done_tasks(self, project_id: Optional[str] = None) -> int:
        """Delete all tasks in Done status.

        Args:
            project_id: Filter by project ID (optional). If None, deletes Done tasks from all projects.

        Returns:
            Number of tasks deleted
        """
        self._ensure_delete_allowed(operation="delete_done_tasks")

        # 🛡️ SAFETY: Backup before bulk delete
        if project_id:
            self._backup_before_delete(
                table="tasks",
                where_clause="status = 'Done' AND project_id = ?",
                params=(project_id,),
                reason=f"Bulk delete Done tasks for project: {project_id}"
            )
        else:
            self._backup_before_delete(
                table="tasks",
                where_clause="status = 'Done'",
                params=(),
                reason="Bulk delete ALL Done tasks across all projects"
            )
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            try:
                # Enable delete permission (triggers check this flag)
                cursor.execute("UPDATE _delete_permissions SET enabled = 1 WHERE id = 1")
                if project_id:
                    cursor.execute("DELETE FROM tasks WHERE status = 'Done' AND project_id = ?", (project_id,))
                else:
                    cursor.execute("DELETE FROM tasks WHERE status = 'Done'")
                deleted_count = cursor.rowcount
                conn.commit()
                return deleted_count
            finally:
                # Always disable delete permission after
                cursor.execute("UPDATE _delete_permissions SET enabled = 0 WHERE id = 1")
                conn.commit()

    def get_task_history(
        self,
        days: int = 30,
        project_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get task completion history for productivity graphs.
        
        Args:
            days: Number of days to look back (default: 30)
            project_id: Filter by project ID (optional)
            
        Returns:
            List of dictionaries with date, completed count, and project_id
            Format: [{"date": "2026-01-25", "completed": 5, "project_id": "project-tracker"}, ...]
        """
        # Calculate start date
        start_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            
            # Query for completion events (event_type = 'completed')
            if project_id:
                cursor.execute("""
                    SELECT 
                        DATE(timestamp) as date,
                        project_id,
                        COUNT(*) as completed
                    FROM task_history
                    WHERE event_type = 'completed'
                        AND timestamp >= ?
                        AND project_id = ?
                    GROUP BY DATE(timestamp), project_id
                    ORDER BY date ASC
                """, (start_date, project_id))
            else:
                cursor.execute("""
                    SELECT 
                        DATE(timestamp) as date,
                        project_id,
                        COUNT(*) as completed
                    FROM task_history
                    WHERE event_type = 'completed'
                        AND timestamp >= ?
                    GROUP BY DATE(timestamp), project_id
                    ORDER BY date ASC
                """, (start_date,))
            
            rows = cursor.fetchall()
            
            # Convert to list of dicts
            result = []
            for row in rows:
                result.append({
                    "date": row["date"],
                    "completed": row["completed"],
                    "project_id": row["project_id"]
                })
            
            return result
    def raw_import_tasks(self, tasks: list[dict[str, Any]]) -> int:
        """Raw import tasks, preserving IDs. Use for disaster recovery."""
        success_count = 0
        with self._get_conn() as conn:
            cursor = conn.cursor()
            for task in tasks:
                try:
                    # Check if project exists
                    cursor.execute("SELECT 1 FROM projects WHERE id = ?", (task["project_id"],))
                    if not cursor.fetchone():
                        print(f"  ⚠️ Skipping task #{task['id']}: Project '{task['project_id']}' not found")
                        continue
                        
                    cursor.execute("""
                        INSERT OR REPLACE INTO tasks 
                        (id, text, status, project_id, priority, created_at, updated_at, completed_at, prompt)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        task["id"], task["text"], task["status"], task["project_id"],
                        task.get("priority"), task["created_at"], task["updated_at"],
                        task.get("completed_at"), task.get("prompt")
                    ))
                    success_count += 1
                except Exception as e:
                    print(f"  ❌ Failed to import task #{task.get('id')}: {e}")
            conn.commit()
        return success_count

    def _ensure_delete_allowed(self, operation: str) -> None:
        """Enforce SAFE_MODE before any delete operation."""
        if os.getenv("SAFE_MODE", "1") == "1":
            logger.error(
                "Blocked delete attempt due to SAFE_MODE: %s\n%s",
                operation,
                "".join(traceback.format_stack())
            )
            raise ValueError("SAFE_MODE=1 - deletes are disabled")

    
    # ==================== IDEAS OPERATIONS (Task #4583) ====================
    
    def add_idea(self, text: str) -> Dict[str, Any]:
        """Create a new idea.
        
        Args:
            text: Idea text content
            
        Returns:
            Idea dictionary with all fields including generated id and timestamps
            
        Raises:
            ValueError: If validation fails
        """
        if not text or not text.strip():
            raise ValueError("Idea text cannot be empty")
        
        if len(text) > 5000:
            raise ValueError("Idea text too long (max 5000 characters)")
        
        now = datetime.now().isoformat()
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ideas (text, created_at, updated_at)
                VALUES (?, ?, ?)
            """, (text.strip(), now, now))
            
            idea_id = cursor.lastrowid
            conn.commit()
            
            return self.get_idea(idea_id)
    
    def get_idea(self, idea_id: int) -> Optional[Dict[str, Any]]:
        """Get a single idea by ID.
        
        Args:
            idea_id: Idea ID
            
        Returns:
            Idea dictionary or None if not found
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_all_ideas(self) -> List[Dict[str, Any]]:
        """Get all ideas, ordered by creation date (newest first).
        
        Returns:
            List of idea dictionaries
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM ideas ORDER BY created_at DESC")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def update_idea(self, idea_id: int, text: str) -> Dict[str, Any]:
        """Update an idea's text.
        
        Args:
            idea_id: Idea ID
            text: New text content
            
        Returns:
            Updated idea dictionary
            
        Raises:
            ValueError: If idea not found or invalid text
        """
        if not text or not text.strip():
            raise ValueError("Idea text cannot be empty")
        
        if len(text) > 5000:
            raise ValueError("Idea text too long (max 5000 characters)")
        
        existing_idea = self.get_idea(idea_id)
        if not existing_idea:
            raise ValueError(f"Idea with ID {idea_id} not found")
        
        now = datetime.now().isoformat()
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE ideas 
                SET text = ?, updated_at = ?
                WHERE id = ?
            """, (text.strip(), now, idea_id))
            conn.commit()
            
            return self.get_idea(idea_id)
    
    def delete_idea(self, idea_id: int) -> None:
        """Delete an idea.
        
        Args:
            idea_id: Idea ID
            
        Raises:
            ValueError: If idea not found
        """
        if not self.get_idea(idea_id):
            raise ValueError(f"Idea with ID {idea_id} not found")
        
        # 🛡️ SAFETY: Backup before delete
        self._backup_before_delete(
            table="ideas",
            where_clause="id = ?",
            params=(idea_id,),
            reason=f"Deleting idea: {idea_id}"
        )
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
            conn.commit()
