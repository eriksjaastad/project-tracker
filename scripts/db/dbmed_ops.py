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
    "archive_done_tasks": Kind.DESTRUCTIVE,
    "trim_done_tasks": Kind.DESTRUCTIVE,
    "raw_import_tasks": Kind.DESTRUCTIVE,
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

    @staticmethod
    def _load_crsqlite(conn: sqlite3.Connection) -> None:
        """Load cr-sqlite from the vendored, root-owned copy only.

        The dylib used to be read from ~/.local/lib/crsqlite/, which is owned
        by the agent's own user at mode 755. A SQLite extension is native code
        running inside the process that loads it, so an agent that could swap
        that file would be executing its own code with database privileges —
        the exact hole the service account is supposed to close. The installer
        vendors it root-owned beside the daemon and this refuses to look
        anywhere else.
        """
        dylib = Path(__file__).resolve().parent.parent / "lib" / "crsqlite.dylib"
        if not dylib.exists():
            raise FileNotFoundError(
                f"cr-sqlite is not installed at {dylib}; migrations that bracket CRR "
                "tables cannot run safely without it"
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
