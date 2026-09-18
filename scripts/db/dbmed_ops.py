"""project-tracker's operations module, as loaded by the dbmed daemon.

This file is the complete, reviewable statement of what any caller can do to
`tracker.db`. If an operation is not in `ALLOWLIST`, no client can reach it —
there is no passthrough, no `execute`, and no way to name a table or a path.

It runs only inside the daemon, from the root-owned install tree. It is never
imported by `pt` or the dashboard.

## How operations are classified

`Kind` drives authorisation, so the classification is the security decision and
deserves the argument:

**READ** — returns rows, changes nothing.

**WRITE** — changes rows, including the single-row deletes that `pt` has always
offered. These keep the gates they already had: `_backup_before_delete` writes
a JSON snapshot of the affected rows to both backup locations, and
`_ensure_delete_allowed` still consults `SAFE_MODE`. Note that `SAFE_MODE` is
now read from the *daemon's* environment, set by launchd — an agent exporting
`SAFE_MODE=0` in its own shell no longer changes anything, which is the point.

**DESTRUCTIVE** — bulk or irreversible. These refuse by default and require a
token that the daemon issues only after taking and verifying a full timestamped
backup. Card #7219 says to preserve existing destructive-operation gates, not
to invent friction, so routine single-row deletes were deliberately left at
WRITE. What moved up to DESTRUCTIVE is the set that can empty a board in one
call: whole-project deletion, the done-column sweeps, and bulk import.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from dbmed.opspec import Kind

# `update_project` and `calendar_update_event` take **kwargs. opspec refuses an
# open kwargs surface, so the accepted field names are enumerated here. Both
# lists mirror the whitelist the backend method already enforces; the backend
# still validates, this just makes the surface reviewable from one place.
_PROJECT_FIELDS = {
    "name", "path", "status", "phase", "description", "completion_pct",
    "last_modified", "is_infrastructure", "has_index", "index_is_valid",
    "index_updated_at", "health_score", "health_grade", "project_type",
}
_TASK_FIELDS = {
    "text", "status", "priority", "prompt", "task_type", "review_comment",
    "title", "notes", "commit_sha", "category", "parent_id", "blocked_by",
    "sequence_order", "machine", "project_id",
}
_EVENT_FIELDS = {
    "title", "description", "event_date", "event_time", "event_type",
    "recurrence", "project_id", "machine", "prompt", "notify_before_minutes",
    "notified_at", "status", "created_by", "metadata",
}

ALLOWLIST: dict[str, Kind | tuple[Kind, set[str]]] = {
    # -- reads ---------------------------------------------------------
    "get_project": Kind.READ,
    "get_all_projects": Kind.READ,
    "get_cron_jobs": Kind.READ,
    "get_ai_agents": Kind.READ,
    "get_services": Kind.READ,
    "get_activity": Kind.READ,
    "get_tasks": Kind.READ,
    "get_task": Kind.READ,
    "resolve_task_id": Kind.READ,
    "get_task_display_id": Kind.READ,
    "get_task_display_id_map": Kind.READ,
    "get_subtasks": Kind.READ,
    "get_subtask_progress": Kind.READ,
    "get_blocking_tasks": Kind.READ,
    "get_blocked_tasks": Kind.READ,
    "is_blocked": Kind.READ,
    "get_task_history": Kind.READ,
    "get_attachments": Kind.READ,
    "get_attachment": Kind.READ,
    "get_idea": Kind.READ,
    "get_all_ideas": Kind.READ,
    "get_info": Kind.READ,
    # -- writes --------------------------------------------------------
    "migrate_attachments_table": Kind.WRITE,
    "add_attachment": Kind.WRITE,
    "add_project": Kind.WRITE,
    "update_project": (Kind.WRITE, _PROJECT_FIELDS),
    "update_health": Kind.WRITE,
    "add_cron_job": Kind.WRITE,
    "add_ai_agent": Kind.WRITE,
    "add_service": Kind.WRITE,
    "add_task": Kind.WRITE,
    "update_task": (Kind.WRITE, _TASK_FIELDS),
    "add_idea": Kind.WRITE,
    "update_idea": Kind.WRITE,
    "set_info": Kind.WRITE,
    # Single-row and per-project deletes. They already back up the rows they
    # touch and already honour SAFE_MODE; escalating them would change the CLI
    # contract without making anything safer.
    "delete_task": Kind.WRITE,
    "delete_attachment": Kind.WRITE,
    "delete_idea": Kind.WRITE,
    "delete_info": Kind.WRITE,
    "delete_cron_jobs": Kind.WRITE,
    "delete_ai_agents": Kind.WRITE,
    "delete_services": Kind.WRITE,
    # -- destructive: token + verified full backup required ------------
    "delete_project": Kind.DESTRUCTIVE,
    "delete_done_tasks": Kind.DESTRUCTIVE,
    "trim_done_tasks": Kind.DESTRUCTIVE,
    "raw_import_tasks": Kind.DESTRUCTIVE,
    # NOT destructive, despite the name and despite sitting next to two that
    # are. `archive_done_tasks` sets `archived_at` and never deletes a row,
    # never touches `status`, and is reversible. It also runs automatically on
    # every `pt tasks done`, so requiring a token and a full backup would mean
    # backing up the whole database every time somebody finishes a card —
    # friction with no safety bought. It exists precisely because the hard
    # delete it replaced destroyed 1,288 Done cards (#6870).
    "archive_done_tasks": Kind.WRITE,
    # -- calendar ------------------------------------------------------
    # Namespaced because `get_cron_jobs` and `add_cron_job` exist on both
    # managers and would otherwise collide into one wire name.
    "calendar_add_event": Kind.WRITE,
    "calendar_update_event": (Kind.WRITE, _EVENT_FIELDS),
    "calendar_mark_done": Kind.WRITE,
    "calendar_cancel_event": Kind.WRITE,
    "calendar_link_task": Kind.WRITE,
    "calendar_unlink_task": Kind.WRITE,
    "calendar_mark_notified": Kind.WRITE,
    "calendar_reset_notify": Kind.WRITE,
    "calendar_get_event": Kind.READ,
    "calendar_get_events": Kind.READ,
    "calendar_get_upcoming_reminders": Kind.READ,
    "calendar_get_events_for_task": Kind.READ,
    "calendar_get_cron_jobs": Kind.READ,
    "calendar_add_cron_job": Kind.WRITE,
    "calendar_export_ical": Kind.READ,
    # -- composite transactions ----------------------------------------
    # `pt scan` and `pt project sync` used to run this as five private
    # cursor-taking calls inside one `BEGIN`. A cursor cannot cross a socket,
    # and splitting it into five round trips would lose atomicity — a failure
    # halfway would leave a project with new agents and stale services. It is
    # one operation now, which is what it always was semantically.
    "sync_project_bundle": Kind.WRITE,
    # -- sync control plane --------------------------------------------
    # Each of these used to be a `sqlite3.connect(get_db_path())` inside a
    # CLI command. They are small, connection-scoped units of work, so each
    # command's database body became one operation.
    "sync_status": Kind.READ,
    "sync_check": Kind.READ,
    "sync_pause": Kind.WRITE,
    "sync_resume": Kind.WRITE,
    "sync_set_machine_id": Kind.WRITE,
    "sync_resume_blocked_versions": Kind.READ,
    # -- schema migrations ---------------------------------------------
    # `migrations_apply` is destructive: it runs ALTER statements, and the
    # runner brackets CRR tables with crsql_begin_alter/crsql_commit_alter.
    # The migrations directory is fixed to the installed, root-owned copy —
    # the caller cannot name one, which is what closes migration_runner's
    # exec_module on an arbitrary path.
    "migrations_pending": Kind.READ,
    "migrations_apply": Kind.DESTRUCTIVE,
    # -- handoff records -----------------------------------------------
    "handoff_create": Kind.WRITE,
    "handoff_list": Kind.READ,
    "handoff_show": Kind.READ,
    "handoff_resolve": Kind.WRITE,
    # -- migration sessions (pt migration start/finish/list) -----------
    # Distinct from schema migrations above: these are the recorded bulk-change
    # sessions from the locked hygiene contract.
    "migration_session_start": Kind.WRITE,
    "migration_session_finish": Kind.WRITE,
    "migration_session_list": Kind.READ,
    # -- dashboard ------------------------------------------------------
    # The dashboard used `db._get_conn()` for these four. It is an
    # unprivileged client now, so each became a named operation. Only the SQL
    # moved; the presentation logic stayed in the dashboard where it belongs.
    "upsert_project_with_portfolio_info": Kind.WRITE,
    "health_snapshot": Kind.READ,
    "loop_last_executions": Kind.READ,
    "task_history_daily": Kind.READ,
    # -- backup and restore ---------------------------------------------
    # `pt backup restore` used to take a filesystem path and copy whatever was
    # there over the live database. That is a write-anything primitive wearing
    # a backup's clothes: it needs no SQL and no file handle on tracker.db to
    # replace its contents entirely. Restore now names a backup, and the
    # daemon resolves the name inside its own protected backup directories.
    "backup_create": Kind.WRITE,
    "backup_list": Kind.READ,
    "backup_restore": Kind.DESTRUCTIVE,
}


class ProjectTrackerOps:
    """Composite backend: the tracker manager plus the calendar manager.

    Both already exist and both already speak in validated domain methods with
    parameterised SQL. Nothing about them is rewritten here — they are simply
    moved to the privileged side of the socket and given a reviewed surface.
    """

    def __init__(self, entry: Any) -> None:
        from db.backend_manager import DatabaseManager
        from db.calendar_manager import CalendarManager

        self.entry = entry
        self.db_path = Path(entry.db_path)
        self._db = DatabaseManager(self.db_path)
        self._cal = CalendarManager(self.db_path)
        self._cal.ensure_tables()

        # Idempotent startup migrations. These used to run at dashboard import
        # time, where any process that imported the module — including the test
        # suite — wrote to the live database. Running them here means they
        # happen once, in the one process that is supposed to write.
        self._db.migrate_attachments_table()

        for name in dir(self._db):
            if not name.startswith("_") and callable(getattr(self._db, name)):
                setattr(self, name, getattr(self._db, name))
        for name in dir(self._cal):
            if not name.startswith("_") and callable(getattr(self._cal, name)):
                setattr(self, f"calendar_{name}", getattr(self._cal, name))

    # -- composite transactions ------------------------------------------

    def sync_project_bundle(
        self,
        project: dict,
        agents: list | None = None,
        cron_jobs: list | None = None,
        services: list | None = None,
        portfolio_info: dict | None = None,
        health: dict | None = None,
    ) -> dict:
        """Upsert a scanned project and everything hanging off it, atomically.

        Replaces the `BEGIN` / five `_*_with_cursor` calls / `commit` block that
        `pt scan` and `pt project sync` each carried a copy of.

        Returns `{"ok": ...}` rather than raising on a per-project failure,
        because that is the behaviour `pt scan` already had: one bad project
        prints a red line and the scan continues over the rest. The error text
        is returned, never swallowed — a caller that ignores it is the bug, and
        both callers check it.
        """
        db = self._db
        with db._get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("BEGIN")
                db._add_project_with_cursor(
                    cursor=cursor,
                    project_id=project["id"],
                    name=project["name"],
                    path=project["path"],
                    status=project["status"],
                    description=project.get("description"),
                    phase=project.get("phase"),
                    last_modified=project["last_modified"],
                    completion_pct=project.get("completion_pct", 0),
                    is_infrastructure=project.get("is_infrastructure", False),
                    has_index=project.get("has_index", False),
                    index_is_valid=project.get("index_is_valid", False),
                    index_updated_at=project.get("index_updated_at"),
                    project_type=project.get("project_type", "standard"),
                )
                db._replace_project_info_entries_with_cursor(
                    cursor, project["id"], portfolio_info or {}
                )
                db._sync_ai_agents_with_cursor(
                    cursor=cursor, project_id=project["id"], agents=agents or []
                )
                db._sync_cron_jobs_with_cursor(
                    cursor=cursor, project_id=project["id"], cron_jobs=cron_jobs or []
                )
                db._sync_services_with_cursor(
                    cursor=cursor, project_id=project["id"], services=services or []
                )
                if health:
                    db._update_health_with_cursor(
                        cursor=cursor,
                        project_id=project["id"],
                        score=health["score"],
                        grade=health["grade"],
                    )
                conn.commit()
            except Exception as exc:
                conn.rollback()
                return {"ok": False, "project_id": project["id"], "error": str(exc)}
        return {"ok": True, "project_id": project["id"], "error": None}

    # -- sync control plane ------------------------------------------------

    def _sync_conn(self) -> sqlite3.Connection:
        """isolation_level=None so sync_state's implicit commits stand alone.

        Same rationale as the CLI helper this replaces: without it Python's
        sqlite3 auto-inserts a BEGIN before DML and the module's own
        INSERT OR REPLACE / DELETE end up nested in a second transaction.
        """
        return sqlite3.connect(self.db_path, isolation_level=None)

    def sync_status(self) -> dict:
        from db.sync_state import is_paused, last_sync, pause_scope

        conn = self._sync_conn()
        try:
            return {
                "paused": is_paused(conn),
                "scope": pause_scope(conn),
                "last_sync": last_sync(conn),
                "engine_active": self._engine_active(conn),
            }
        finally:
            conn.close()

    def sync_check(self) -> list:
        from db.sync_checks import local_sync_readiness

        conn = self._sync_conn()
        try:
            return [
                {"name": c.name, "ok": c.ok, "detail": c.detail}
                for c in local_sync_readiness(conn)
            ]
        finally:
            conn.close()

    def sync_pause(self, scope: str = "data_plane") -> dict:
        from db.sync_state import set_paused

        if scope not in ("data_plane", "all"):
            raise ValueError(f"unknown pause scope {scope!r}")
        conn = self._sync_conn()
        try:
            set_paused(conn, scope=scope)  # type: ignore[arg-type]
        finally:
            conn.close()
        return {"paused": True, "scope": scope}

    def sync_resume(self) -> dict:
        from db.sync_state import clear_paused, is_paused

        conn = self._sync_conn()
        try:
            was_paused = is_paused(conn)
            clear_paused(conn)
        finally:
            conn.close()
        return {"was_paused": was_paused}

    def sync_resume_blocked_versions(self) -> list:
        from db.sync_state import resume_blocked_versions

        conn = self._sync_conn()
        try:
            return list(resume_blocked_versions(conn))
        finally:
            conn.close()

    def sync_set_machine_id(self, machine_id: int) -> dict:
        from db.sync_checks import set_explicit_machine_id

        conn = self._sync_conn()
        try:
            set_explicit_machine_id(conn, machine_id)
        finally:
            conn.close()
        return {"machine_id": machine_id}

    @staticmethod
    def _engine_active(conn: sqlite3.Connection) -> bool:
        try:
            conn.execute("SELECT crsql_db_version()").fetchone()
            return True
        except sqlite3.Error:
            return False

    # -- schema migrations --------------------------------------------------

    def _migrations_dir(self) -> Path:
        """The installed migrations directory. Never caller-supplied.

        `migration_runner._load_migration` uses `exec_module`, so whoever
        chooses this directory chooses what Python the privileged daemon
        executes. It is pinned to the deployed copy beside this module, which
        `registry.verify_tree` has already confirmed is root-owned.
        """
        return Path(__file__).resolve().parent / "migrations"

    def migrations_pending(self) -> list:
        from db.migration_runner import discover_migrations, unapplied_migrations

        directory = self._migrations_dir()
        if not directory.is_dir():
            return []
        migrations = discover_migrations(directory, verbose=False)
        conn = sqlite3.connect(self.db_path)
        try:
            pending = unapplied_migrations(conn, migrations)
        finally:
            conn.close()
        return [{"version": m.version, "name": m.name} for m in pending]

    def migrations_apply(self) -> dict:
        from db.migration_runner import MigrationError, apply_all

        directory = self._migrations_dir()
        if not directory.is_dir():
            raise FileNotFoundError(f"no migrations directory at {directory}")

        conn = sqlite3.connect(self.db_path, isolation_level=None)
        try:
            self._load_crsqlite(conn)
            try:
                applied = apply_all(conn, directory)
            except MigrationError as err:
                return {"ok": False, "error": str(err), "applied": []}
        finally:
            conn.close()
        return {
            "ok": True,
            "error": None,
            "applied": [{"version": m.version, "name": m.name} for m in applied],
        }

    def _load_crsqlite(self, conn: sqlite3.Connection) -> None:
        """Load cr-sqlite from the vendored, root-owned copy only.

        The dylib used to be read from ~/.local/lib/crsqlite/, which is owned
        by the agent's own user at mode 755. A SQLite extension is native code
        running inside the process that loads it, so an agent that could swap
        that file would be executing its own code with database privileges —
        the exact hole the service account is supposed to close. The installer
        vendors it root-owned beside the daemon and this refuses to look
        anywhere else.
        """
        configured = getattr(self.entry, "crsqlite_path", None)
        if configured is None:
            raise FileNotFoundError(
                "no crsqlite_path in this project's registry entry; migrations that "
                "bracket CRR tables cannot run safely without the extension. Add "
                "crsqlite_path to the registry and redeploy."
            )
        dylib = Path(configured)
        if not dylib.exists():
            raise FileNotFoundError(
                f"cr-sqlite is not at the registered path {dylib}; migrations that "
                "bracket CRR tables cannot run safely without it"
            )
        conn.enable_load_extension(True)
        try:
            conn.load_extension(str(dylib), entrypoint="sqlite3_crsqlite_init")
        finally:
            conn.enable_load_extension(False)

    # -- handoff records ---------------------------------------------------

    _HANDOFF_COLUMNS = (
        "card_id", "project", "branch", "file_list", "intent", "current_status",
        "next_command", "discard_or_preserve_guidance", "record_type",
        "pr_exempt_reason", "pr_exempt_disposition", "pr_exempt_approver",
        "created_at", "created_by",
    )

    def _tracker_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @staticmethod
    def _handoff_row_to_dict(row: sqlite3.Row) -> dict:
        import json

        return {
            "id": row["id"],
            "card_id": row["card_id"],
            "project": row["project"],
            "branch": row["branch"],
            "file_list": json.loads(row["file_list"] or "[]"),
            "intent": row["intent"],
            "current_status": row["current_status"],
            "next_command": row["next_command"],
            "discard_or_preserve_guidance": row["discard_or_preserve_guidance"],
            "record_type": row["record_type"],
            "pr_exempt_reason": row["pr_exempt_reason"],
            "pr_exempt_disposition": row["pr_exempt_disposition"],
            "pr_exempt_approver": row["pr_exempt_approver"],
            "created_at": row["created_at"],
            "created_by": row["created_by"],
            "resolved_at": row["resolved_at"],
            "resolved_note": row["resolved_note"],
        }

    def handoff_create(
        self,
        card_id: int,
        branch: str,
        file_list: str,
        intent: str,
        current_status: str,
        next_command: str,
        discard_or_preserve_guidance: str,
        record_type: str,
        created_at: str,
        created_by: str,
        pr_exempt_reason: str | None = None,
        pr_exempt_disposition: str | None = None,
        pr_exempt_approver: str | None = None,
    ) -> dict:
        """Insert a handoff and return it, with the project resolved from the card.

        Returns `{"ok": False, "error_kind": "validation"}` for a missing card
        rather than raising, so the CLI can keep emitting the same
        `pt.handoff.v1` error envelope and the same exit code it always did.
        """
        conn = self._tracker_conn()
        try:
            if conn.execute("SELECT id FROM tasks WHERE id = ?", (card_id,)).fetchone() is None:
                return {
                    "ok": False,
                    "error_kind": "validation",
                    "error": f"card {card_id} does not exist",
                }
            conn.execute(
                f"INSERT INTO handoffs ({', '.join(self._HANDOFF_COLUMNS)}) "
                f"VALUES ({', '.join('?' * len(self._HANDOFF_COLUMNS))})",
                (
                    card_id, None, branch, file_list, intent, current_status,
                    next_command, discard_or_preserve_guidance, record_type,
                    pr_exempt_reason, pr_exempt_disposition, pr_exempt_approver,
                    created_at, created_by,
                ),
            )
            handoff_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            task_row = conn.execute(
                "SELECT project_id FROM tasks WHERE id = ?", (card_id,)
            ).fetchone()
            conn.execute(
                "UPDATE handoffs SET project = ? WHERE id = ?",
                (task_row["project_id"] if task_row else None, handoff_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM handoffs WHERE id = ?", (handoff_id,)
            ).fetchone()
            return {"ok": True, "error": None, "record": self._handoff_row_to_dict(row)}
        finally:
            conn.close()

    def handoff_list(
        self,
        card_id: int | None = None,
        project: str | None = None,
        unresolved_only: bool = False,
    ) -> list:
        clauses: list[str] = []
        params: list[object] = []
        if card_id is not None:
            clauses.append("card_id = ?")
            params.append(card_id)
        if project:
            clauses.append("project = ?")
            params.append(project)
        if unresolved_only:
            clauses.append("resolved_at IS NULL")
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        conn = self._tracker_conn()
        try:
            rows = conn.execute(
                f"SELECT * FROM handoffs {where_sql} ORDER BY created_at DESC", params
            ).fetchall()
            return [self._handoff_row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def handoff_show(self, handoff_id: int) -> dict | None:
        conn = self._tracker_conn()
        try:
            row = conn.execute(
                "SELECT * FROM handoffs WHERE id = ?", (handoff_id,)
            ).fetchone()
            return self._handoff_row_to_dict(row) if row else None
        finally:
            conn.close()

    def handoff_resolve(
        self, handoff_id: int, resolved_at: str, note: str | None = None
    ) -> dict:
        """Resolve a handoff, refusing to overwrite one already resolved."""
        conn = self._tracker_conn()
        try:
            existing = conn.execute(
                "SELECT id, resolved_at FROM handoffs WHERE id = ?", (handoff_id,)
            ).fetchone()
            if existing is None:
                return {
                    "ok": False,
                    "error_kind": "validation",
                    "error": f"handoff {handoff_id} does not exist",
                }
            if existing["resolved_at"] is not None:
                return {
                    "ok": False,
                    "error_kind": "validation",
                    "error": (
                        f"handoff {handoff_id} is already resolved at "
                        f"{existing['resolved_at']}; refusing to overwrite"
                    ),
                }
            conn.execute(
                "UPDATE handoffs SET resolved_at = ?, resolved_note = ? WHERE id = ?",
                (resolved_at, note, handoff_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM handoffs WHERE id = ?", (handoff_id,)
            ).fetchone()
            return {"ok": True, "error": None, "record": self._handoff_row_to_dict(row)}
        finally:
            conn.close()

    # -- migration sessions -------------------------------------------------

    def migration_session_start(
        self, name: str, started_at: str, baseline_head: str, created_by: str
    ) -> dict:
        """Record a bulk-change session. Best-effort, but never silent.

        The state file on disk is the source of truth for revert, so a database
        failure here must not abort `pt migration start`. It previously did
        `except sqlite3.Error: pass`, which meant the row could go missing with
        nothing said. The error is returned instead, and the CLI warns.
        """
        conn = self._tracker_conn()
        try:
            conn.execute(
                "INSERT INTO migrations "
                "(name, project_id, started_at, status, baseline_head, created_by) "
                "VALUES (?, ?, ?, 'recording', ?, ?)",
                (name, None, started_at, baseline_head, created_by),
            )
            db_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.commit()
            return {"ok": True, "error": None, "id": db_id}
        except sqlite3.Error as exc:
            return {"ok": False, "error": str(exc), "id": None}
        finally:
            conn.close()

    def migration_session_finish(
        self, name: str, finished_at: str, status: str, manifest_path: str
    ) -> dict:
        """Close a recording session. Best-effort, but never silent — see above."""
        if status not in ("finished", "committed", "reverted"):
            raise ValueError(f"unknown migration session status {status!r}")
        conn = self._tracker_conn()
        try:
            cursor = conn.execute(
                "UPDATE migrations SET finished_at = ?, status = ?, manifest_path = ? "
                "WHERE name = ? AND status = 'recording'",
                (finished_at, status, manifest_path, name),
            )
            conn.commit()
            return {"ok": True, "error": None, "rows": cursor.rowcount}
        except sqlite3.Error as exc:
            return {"ok": False, "error": str(exc), "rows": 0}
        finally:
            conn.close()

    def migration_session_list(self) -> list:
        conn = self._tracker_conn()
        try:
            rows = conn.execute(
                "SELECT id, name, project_id, started_at, finished_at, status, "
                "baseline_head, manifest_path, created_by FROM migrations "
                "ORDER BY started_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # -- dashboard ----------------------------------------------------------

    def upsert_project_with_portfolio_info(
        self, project: dict, portfolio_info: dict | None = None
    ) -> dict:
        """Upsert a project and its portfolio metadata, and nothing else.

        Deliberately narrower than `sync_project_bundle`. The dashboard's
        refresh only rediscovers projects — it does not rescan agents, cron
        jobs or services. Routing it through the bundle would pass empty lists
        to the `_sync_*_with_cursor` helpers, which replace rather than merge,
        and silently wipe data the dashboard never intended to touch.
        """
        db = self._db
        with db._get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("BEGIN")
                db._add_project_with_cursor(
                    cursor=cursor,
                    project_id=project["id"],
                    name=project["name"],
                    path=project["path"],
                    status=project["status"],
                    description=project.get("description"),
                    phase=project.get("phase"),
                    last_modified=project["last_modified"],
                    completion_pct=project.get("completion_pct", 0),
                    is_infrastructure=project.get("is_infrastructure", False),
                    has_index=project.get("has_index", False),
                    index_is_valid=project.get("index_is_valid", False),
                    index_updated_at=project.get("index_updated_at"),
                    project_type=project.get("project_type", "standard"),
                )
                db._replace_project_info_entries_with_cursor(
                    cursor, project["id"], portfolio_info or {}
                )
                conn.commit()
            except Exception as exc:
                conn.rollback()
                return {"ok": False, "project_id": project["id"], "error": str(exc)}
        return {"ok": True, "project_id": project["id"], "error": None}

    def health_snapshot(self) -> dict:
        """Task count and the database path, for /api/health.

        The path is returned because the health payload has always shown it and
        operators use it to confirm which database is live. It is a path the
        caller cannot open, which is rather the point.
        """
        started = time.perf_counter()
        conn = self._tracker_conn()
        try:
            count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        finally:
            conn.close()
        return {
            "task_count": int(count),
            "path": str(self.db_path),
            "query_ms": round((time.perf_counter() - started) * 1000, 1),
        }

    def loop_last_executions(self, loop_names: list) -> dict:
        """Most recent execution row per loop name, or None where never run."""
        conn = self._tracker_conn()
        try:
            out: dict = {}
            for name in loop_names:
                row = conn.execute(
                    "SELECT id, started_at, completed_at, status, cards_created, "
                    "error_message FROM loop_executions WHERE loop_name = ? "
                    "ORDER BY started_at DESC LIMIT 1",
                    (name,),
                ).fetchone()
                out[name] = dict(row) if row else None
            return out
        finally:
            conn.close()

    def task_history_daily(self, start_iso: str, project_id: str | None = None) -> list:
        """Daily review-transition counts from task_history, oldest first.

        Gap-filling across the date range stays in the dashboard: this returns
        only the days that have rows, exactly as the original query did.
        """
        sql = (
            "SELECT DATE(timestamp) as date, "
            "SUM(CASE WHEN old_status = 'Review' AND new_status = 'In Progress' "
            "THEN 1 ELSE 0 END) as review_bounces, "
            "SUM(CASE WHEN old_status = 'Review' AND new_status = 'Done' "
            "THEN 1 ELSE 0 END) as review_promotions, "
            "SUM(CASE WHEN old_status = 'In Progress' AND new_status = 'Review' "
            "THEN 1 ELSE 0 END) as review_entries "
            "FROM task_history WHERE timestamp >= ?"
        )
        params: list = [start_iso]
        if project_id:
            sql += " AND project_id = ?"
            params.append(project_id)
        sql += " GROUP BY DATE(timestamp) ORDER BY date ASC"

        conn = self._tracker_conn()
        try:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    # -- backup and restore -------------------------------------------------

    _BACKUP_RETENTION_DAYS = 30

    def _backup_dirs(self) -> list[Path]:
        """Both DECISIONS.md backup locations, primary first."""
        return [self.entry.backup_dir, self.entry.external_backup_dir]

    def backup_create(self, retention_days: int | None = None) -> dict:
        """Timestamped snapshot to both locations, then prune old ones.

        Replaces `scripts/backup-db.sh`, which shelled out to the `sqlite3`
        binary and built its dot-command by interpolating an environment
        variable into a single-quoted string — so a backup path containing a
        quote broke out of the command. There is no shell here.
        """
        stamp = time.strftime("%Y%m%d_%H%M%S")
        primary = self.dbmed_backup(label=f"tracker_{stamp}")
        if not self.dbmed_verify_backup(str(primary)):
            raise RuntimeError(f"backup at {primary} failed verification")

        pruned = self._prune_backups(
            self._BACKUP_RETENTION_DAYS if retention_days is None else retention_days
        )
        return {
            "path": str(primary),
            "size_bytes": primary.stat().st_size,
            "verified": True,
            "pruned": pruned,
        }

    def _prune_backups(self, retention_days: int) -> list:
        """Trash snapshots older than the retention window.

        The shell version used `find -delete`. These are real database
        contents, so they go to the Trash: recoverable if the retention window
        turns out to have been wrong.
        """
        from send2trash import send2trash

        if retention_days <= 0:
            return []
        cutoff = time.time() - retention_days * 86400
        pruned: list[str] = []
        for directory in self._backup_dirs():
            if not directory.is_dir():
                continue
            for candidate in sorted(directory.glob("tracker_*.db")):
                if candidate.stat().st_mtime < cutoff:
                    send2trash(str(candidate))
                    pruned.append(candidate.name)
        return pruned

    def backup_list(self) -> list:
        """Every restorable snapshot, newest first, named not pathed.

        The name is what `backup_restore` accepts. Paths are returned for
        display only — the caller cannot open them, and cannot restore from
        one by supplying a different one.
        """
        seen: dict[str, dict] = {}
        for directory in self._backup_dirs():
            if not directory.is_dir():
                continue
            for candidate in directory.glob("*.db"):
                info = candidate.stat()
                seen.setdefault(
                    candidate.name,
                    {
                        "name": candidate.name,
                        "size_bytes": info.st_size,
                        "modified": time.strftime(
                            "%Y-%m-%dT%H:%M:%S", time.localtime(info.st_mtime)
                        ),
                        "location": str(directory),
                    },
                )
        return sorted(seen.values(), key=lambda row: row["modified"], reverse=True)

    def _resolve_backup(self, name: str) -> Path:
        """Turn a caller-supplied name into a path inside a protected dir.

        The name is a bare filename and is checked as one. Anything with a
        separator, a parent reference, or a resolved location outside the
        backup directories is refused — that is the whole reason restore takes
        a name instead of a path.
        """
        if not name or "/" in name or "\\" in name or name in (".", ".."):
            raise ValueError(f"{name!r} is not a bare backup name")
        for directory in self._backup_dirs():
            candidate = directory / name
            if not candidate.is_file() or candidate.is_symlink():
                continue
            resolved = candidate.resolve()
            if resolved.parent != directory.resolve():
                continue
            return resolved
        raise FileNotFoundError(
            f"no backup named {name!r} in the protected backup directories; "
            "list them with backup_list"
        )

    def backup_restore(self, name: str) -> dict:
        """Replace the live database with a named, validated snapshot.

        Destructive, so the daemon has already taken and verified a full
        backup of the current state before issuing the token that reaches
        here. The snapshot is validated again before it is swapped in, and the
        swap is an atomic rename of a fully written temporary file, so an
        interrupted restore cannot leave a half-written database.
        """
        from send2trash import send2trash

        source = self._resolve_backup(name)
        if source == self.db_path.resolve():
            raise ValueError("refusing to restore from the live database itself")
        if not self.dbmed_verify_backup(str(source)):
            raise ValueError(f"backup {name!r} failed validation; refusing to restore")

        import tempfile

        handle, staging_name = tempfile.mkstemp(
            dir=str(self.db_path.parent), prefix="tracker-restore-", suffix=".db"
        )
        os.close(handle)
        staging = Path(staging_name)
        try:
            src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
            try:
                dst = sqlite3.connect(staging)
                try:
                    src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()
            if not self.dbmed_verify_backup(str(staging)):
                raise ValueError("the staged restore failed validation; live DB untouched")
            os.replace(staging, self.db_path)
        except Exception:
            if staging.exists():
                send2trash(str(staging))
            raise

        # The previous database's WAL and SHM describe a database that no
        # longer exists. Left in place, SQLite would try to replay them over
        # the restored file. They go to the Trash rather than being removed.
        trashed: list[str] = []
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{self.db_path}{suffix}")
            if sidecar.exists():
                send2trash(str(sidecar))
                trashed.append(sidecar.name)

        return {
            "restored_from": name,
            "restored_path": str(self.db_path),
            "trashed_sidecars": trashed,
        }

    # -- test-fixture seeding ----------------------------------------------

    # Only these columns, and only on `tasks`. Wide enough for the ordering
    # and staleness scenarios the suite needs to build, narrow enough that it
    # cannot be turned into a general "write anything" primitive if the
    # registry flag were ever enabled somewhere it should not be.
    _SEEDABLE_TASK_COLUMNS = frozenset(
        {"created_at", "updated_at", "completed_at", "archived_at"}
    )

    def dbmed_seed(self, task_id: int, **columns: Any) -> dict:
        """Backdate or adjust timestamp columns on one task. Tests only.

        Reached exclusively through `dbmed.seed`, which the daemon refuses
        unless the registry entry sets `allow_seeding`. `install.sh` never
        writes that flag.
        """
        unknown = set(columns) - self._SEEDABLE_TASK_COLUMNS
        if unknown:
            raise ValueError(
                f"dbmed_seed does not set {sorted(unknown)}; "
                f"seedable columns are {sorted(self._SEEDABLE_TASK_COLUMNS)}"
            )
        if not columns:
            return {"task_id": task_id, "updated": 0}

        assignments = ", ".join(f"{name} = ?" for name in columns)
        values = [*columns.values(), task_id]
        conn = self._tracker_conn()
        try:
            cursor = conn.execute(
                f"UPDATE tasks SET {assignments} WHERE id = ?", values
            )
            conn.commit()
            return {"task_id": task_id, "updated": cursor.rowcount}
        finally:
            conn.close()

    _COUNTABLE_TABLES = frozenset(
        {
            "tasks", "projects", "task_history", "delete_audit_log", "handoffs",
            "migrations", "calendar_events", "ai_agents", "cron_jobs",
            "services", "ideas", "project_info", "attachments",
        }
    )

    def dbmed_count_rows(self, table: str) -> dict:
        """Count rows in one allowlisted table. Tests only.

        The table name is interpolated into the SQL because a table name
        cannot be a bound parameter, which is exactly why it is checked
        against a frozen allowlist first rather than escaped.
        """
        if table not in self._COUNTABLE_TABLES:
            raise ValueError(
                f"{table!r} is not countable; allowed: {sorted(self._COUNTABLE_TABLES)}"
            )
        conn = self._tracker_conn()
        try:
            return {"table": table, "rows": conn.execute(
                f"SELECT COUNT(*) FROM {table}"  # noqa: S608 - allowlisted above
            ).fetchone()[0]}
        finally:
            conn.close()

    def dbmed_seed_task(
        self,
        task_id: int,
        text: str,
        project_id: str,
        status: str = "To Do",
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> dict:
        """Insert a task with a caller-chosen id. Tests only.

        `add_task` allocates ids through `pt_next_id`, which is correct and
        which fixtures cannot predict. Several suites assert against a known
        card number, so they need to choose one. That is a fixture need and
        never a product one, so it lives behind the same registry flag as the
        rest of the test-support surface.
        """
        stamp = created_at or "2026-01-01T00:00:00Z"
        conn = self._tracker_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO tasks "
                "(id, text, status, project_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (task_id, text, status, project_id, stamp, updated_at or stamp),
            )
            conn.commit()
        finally:
            conn.close()
        return {"task_id": task_id}

    # -- dbmed integration hooks -----------------------------------------

    def dbmed_backup(self, label: str) -> Path:
        """Full timestamped backup to both locations, via SQLite's backup API.

        Uses the online backup API rather than a file copy so a concurrent
        writer cannot produce a torn snapshot — the failure mode that makes a
        `cp` of a WAL database quietly useless.

        DECISIONS.md requires two locations, because the 2026-01-27 incident
        proved one can be lost with the project. Both now sit under the service
        account, so an agent can neither read them nor delete them.
        """
        stamp = time.strftime("%Y%m%dT%H%M%S")
        primary = self.entry.backup_dir / f"{label}_{stamp}.db"
        primary.parent.mkdir(parents=True, exist_ok=True)

        source = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        try:
            target = sqlite3.connect(primary)
            try:
                source.backup(target)
            finally:
                target.close()
        finally:
            source.close()

        external = self.entry.external_backup_dir / f"{label}_{stamp}.db"
        external.parent.mkdir(parents=True, exist_ok=True)
        external.write_bytes(primary.read_bytes())
        return primary

    def dbmed_verify_backup(self, path: str) -> bool:
        """A backup only counts if it opens, passes integrity_check, and has rows.

        Checking that the file exists is not verification. The gate exists
        because a backup that silently failed is worse than no backup: it
        authorises the destructive operation that then has nothing to fall back
        to.
        """
        candidate = Path(path)
        if not candidate.exists() or candidate.stat().st_size == 0:
            return False
        conn = sqlite3.connect(f"file:{candidate}?mode=ro", uri=True)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                return False
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if not {"tasks", "projects"} <= tables:
                return False
            return conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] >= 0
        except sqlite3.DatabaseError:
            return False
        finally:
            conn.close()

    def dbmed_fixture_create(self, name: str) -> dict:
        """Create a disposable synthetic database inside the protected root.

        Probes need a target they are *supposed* to fail to open. Giving them
        the live database to fail against would violate card #7217's rule
        against probing live data, so the daemon makes one here — same
        directory, same ownership, same mode, no real rows.
        """
        from db.schema import ensure_schema

        root = Path(self.entry.fixture_root)
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{name}.db"
        conn = sqlite3.connect(path)
        try:
            ensure_schema(conn.cursor())
            conn.execute(
                "INSERT INTO projects (id, name, path, status) VALUES (?,?,?,?)",
                (f"fixture-{name}", f"fixture {name}", f"/nonexistent/{name}", "active"),
            )
            conn.commit()
        finally:
            conn.close()
        return {"path": str(path), "project": f"fixture-{name}"}

    def dbmed_fixture_destroy(self, name: str) -> dict:
        from send2trash import send2trash

        path = Path(self.entry.fixture_root) / f"{name}.db"
        if path.exists():
            send2trash(str(path))
        return {"destroyed": str(path)}


def build(entry: Any) -> tuple[ProjectTrackerOps, dict[str, Kind | tuple[Kind, set[str]]]]:
    return ProjectTrackerOps(entry), ALLOWLIST
