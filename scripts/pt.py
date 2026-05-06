#!/usr/bin/env python3
"""
Project Tracker CLI - Track all your projects in one place.

How to Use:
-----------
1. Run with Launcher (easiest):
   ./pt [command]

2. Run with Python directly:
   python scripts/pt.py [command]

Common Commands:
- ./pt scan      # Scan for new projects and rebuild graph
- ./pt launch    # Start the web dashboard
- ./pt list      # List all projects in terminal
- ./pt help      # Show help
"""

import os
import shutil
import sqlite3
import sys
import webbrowser
import time
import json
from datetime import datetime
from pathlib import Path
from typing import NoReturn, Optional
import subprocess

import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from scripts.config import PROJECTS_BASE_DIR
from db.schema import init_db, get_db_path
from db.manager import DatabaseManager, _USE_TURSO
from discovery.project_scanner import (
    PORTFOLIO_ROOTS,
    discover_projects,
    extract_project_metadata,
    scan_health_parallel,
)
from discovery.external_resources_parser import parse_external_resources
from discovery.graph_builder import GraphBuilder
from discovery.backup_reader import get_backup_status
# update_directory_index removed — 00_Index generation killed (#5530)
from discovery.journal_specialist import JournalSpecialist
from utils.validation import BlockedTaskProjectError
from origin import resolve_created_by as _resolve_created_by
from restore_db import BackupRestoreError, restore_database
from skill_invocations_reader import (
    iter_invocations as _iter_skill_invocations,
    SkillInvocationsTableMissing as _SkillInvocationsTableMissing,
    TursoEnabledError as _SkillsTursoEnabledError,
)
from skills_registry import installed_skills as _installed_skills

console = Console()
PT_VERSION = "0.0.0"
PT_JSON_SCHEMA_VERSION = "pt.v1"
PT_MEMORY_SCHEMA_VERSION = "pt.memory.v1"
PT_CONFIG_SCHEMA_VERSION = "pt.config.v1"
PT_DOCTOR_SCHEMA_VERSION = "pt.doctor.v1"
PT_HYGIENE_SCHEMA_VERSION = "pt.hygiene.v1"

EXIT_VALIDATION = 2
EXIT_BACKEND_UNAVAILABLE = 3
EXIT_QUERY_FAILURE = 4
EXIT_AUTH = 5
EXIT_HYGIENE_FINDING = 6


def _sync_portfolio_project_info(db: DatabaseManager, cursor: sqlite3.Cursor, project: dict) -> None:
    """Persist tracker-owned portfolio metadata for scanned projects."""
    db._replace_project_info_entries_with_cursor(
        cursor,
        project["id"],
        {
            "portfolio_group": project.get("portfolio_group"),
            "portfolio_label": project.get("portfolio_label"),
            "portfolio_parent": project.get("portfolio_parent"),
        },
    )


def _resolve_project_directory(project_name: str) -> Optional[Path]:
    """Resolve a project directory from the main root or supported portfolio roots."""
    base_path = Path(PROJECTS_BASE_DIR)
    direct_path = base_path / project_name
    if direct_path.is_dir():
        return direct_path

    for root_name in PORTFOLIO_ROOTS:
        nested_path = base_path / root_name / project_name
        if nested_path.is_dir():
            return nested_path

    return None


def _resolve_dashboard_python(project_root: Path) -> str:
    """Resolve the Python interpreter used to launch the dashboard."""
    candidates = [
        project_root / ".venv" / "bin" / "python",
        project_root / "venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    console.print(
        f"[red]ERROR: No .venv or venv found under {project_root}. "
        "Create a virtual environment before launching the dashboard.[/red]"
    )
    sys.exit(1)



_PT_BANNER = """\
[bold cyan]  /^\\\\[/bold cyan]
[bold cyan] (   )[/bold cyan]  [bold white]pt[/bold white] [dim]· project tracker[/dim]
[bold cyan]  ) ([/bold cyan]
[bold cyan] (___)  [/bold cyan][dim]✦ plan · ship · repeat ✦[/dim]
"""

def _print_banner() -> None:
    """Print the pt banner — suppressed in non-interactive / CI environments."""
    import os, sys
    if not sys.stdout.isatty():
        return
    if os.environ.get("CI") or os.environ.get("PT_NO_BANNER"):
        return
    console.print(_PT_BANNER)


def _notify_inbox(card_id: int, project_id: str, card_status: str, description: str) -> None:
    """Write an inbox message after a task mutation (opt-in per project).

    Only fires if ~/.claude/inbox/<project>/ exists.
    Called from: tasks_create, tasks_update, tasks_move, tasks_done,
    tasks_start, tasks_review, tasks_cancel, tasks_delete, tasks_clear_done.
    """
    import os, logging
    _log = logging.getLogger(__name__)
    # Sanitize project_id to prevent path traversal
    safe_id = project_id.replace("/", "").replace("\\", "").replace("..", "")
    if not safe_id or safe_id != project_id:
        _log.warning(f"Skipping inbox notification: unsafe project_id '{project_id}'")
        return
    inbox_dir = Path(os.path.expanduser("~")) / ".claude" / "inbox" / safe_id
    if not inbox_dir.is_dir():
        return

    from datetime import timezone
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    filename_ts = now.strftime("%Y%m%dT%H%M%SZ")
    filepath = inbox_dir / f"{filename_ts}-kanban.md"

    # Determine action hint based on status
    action_hints = {
        "Backlog": "This task is in the backlog. No action needed yet.",
        "To Do": f"Start this task when ready. Use `pt tasks start {card_id}` to begin.",
        "In Progress": "This task is now in progress.",
        "Review": "This task is ready for review.",
        "Done": "This task has been completed.",
        "Cancelled": "This task has been cancelled.",
        "Deleted": "This task has been permanently deleted.",
    }
    action = action_hints.get(card_status, f"Status changed to {card_status}.")

    content = f"""---
from: kanban
to: {project_id}
timestamp: {timestamp}
priority: normal
type: card-notification
card_id: {card_id}
card_status: {card_status}
---

Card #{card_id} — {card_status}

**Description:** {description}

**Status:** {card_status}
**Action:** {action}
"""
    try:
        import tempfile
        # Atomic write: temp file then rename
        fd, tmp_path = tempfile.mkstemp(dir=str(inbox_dir), suffix=".tmp")
        with os.fdopen(fd, 'w') as f:
            f.write(content)
        os.rename(tmp_path, str(filepath))
    except Exception as e:
        _log.warning(f"Inbox notification failed for #{card_id}: {e}")


@click.group(invoke_without_command=True)
@click.version_option(PT_VERSION, "--version", prog_name="pt")
@click.pass_context
def cli(ctx):
    """Project Tracker - Manage and track all your projects

    Environment Variables:
    ----------------------
    PT_DB_PATH: Path to the database file (default: data/tracker.db)
    PROJECTS_ROOT: Path to your projects folder
    PT_EXTERNAL_BACKUP_DIR: Path for safety backups (use this in sandboxed environments)
    PT_ALLOW_FRESH_DB: Set to 1 to allow starting with an empty database
    SAFE_MODE: Set to 0 to enable permanent deletions (Erik only)
    PT_NO_BANNER: Set to 1 to suppress the startup banner
    """
    _print_banner()
    # Phase 2.1a step 5 — surface any unapplied migrations so the
    # operator knows to run `pt db migrate`. Skipped when the user is
    # already running `db migrate` (the fix) or when explicitly silenced.
    # Automation callers (cron/SSH) set PT_SUPPRESS_MIGRATION_WARNING=1
    # to silence; the warning otherwise goes to stderr and never pollutes
    # stdout JSON output.
    if ctx.invoked_subcommand not in ("db",) and not os.environ.get(
        "PT_SUPPRESS_MIGRATION_WARNING"
    ):
        _warn_unapplied_migrations()
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


def _warn_unapplied_migrations() -> None:
    """Print a stderr warning if the tracker DB has pending migrations.

    Never raises — a warning failure must not take `pt` down. Turso
    mode is skipped entirely: the migration runner operates on local
    SQLite and isn't meaningful against a Turso-backed DB.
    """
    if _USE_TURSO:
        return
    try:
        from db.migration_runner import discover_migrations, unapplied_migrations
        migrations_dir = Path(__file__).parent / "db" / "migrations"
        if not migrations_dir.is_dir():
            return
        db_path = get_db_path()
        if not db_path.exists():
            return
        migrations = discover_migrations(migrations_dir, verbose=False)
        conn = sqlite3.connect(db_path)
        try:
            pending = unapplied_migrations(conn, migrations)
        finally:
            conn.close()
        if not pending:
            return
        names = ", ".join(f"{m.version:03d}_{m.name}" for m in pending)
        click.echo(
            f"⚠ pending migration(s): {names}. Run `pt db migrate` to apply.",
            err=True,
        )
    except Exception as err:
        # A broken migration file or broken DB config shouldn't brick
        # the CLI, but it shouldn't be silent either — the operator
        # needs to see that something is wrong, not just a missing
        # warning. Log and continue.
        click.echo(
            f"⚠ could not check for pending migrations: {err!r}",
            err=True,
        )
        return


def rebuild_project_graph():
    console.print("[bold blue]Rebuilding project graph & analysis...[/bold blue]")
    try:
        root_path = Path(PROJECTS_BASE_DIR)
        output_path = Path(__file__).parent.parent / "data" / "graph.json"
        analysis_path = Path(__file__).parent.parent / "data" / "graph_analysis.md"
        builder = GraphBuilder(root_path)
        builder.scan()
        builder.save(output_path)
        analysis_text = builder.generate_analysis()
        analysis_path.write_text(analysis_text)
        console.print(f"  ✓ Project graph & analysis updated")
        console.print("[bold cyan]  → Running Journal Specialist (Enriching links)...[/bold cyan]")
        specialist = JournalSpecialist()
        specialist.scan()
    except Exception as e:
        console.print(f"  [red]✗ Error rebuilding project graph: {e}[/red]")


def _scan_impl(no_graph=False, dry_run=False, force=False):
    console.print(f"[bold blue]Scanning projects in {PROJECTS_BASE_DIR}...[/bold blue]")
    base_path = Path(PROJECTS_BASE_DIR)
    if not base_path.exists() or not base_path.is_dir():
        console.print("[red]PROJECTS_BASE_DIR is invalid or missing. Aborting scan.[/red]")
        return
    db_path = get_db_path()
    db_exists = db_path.exists()
    if not db_exists and not dry_run:
        console.print("[red]Database not initialized. Run './pt init' first.[/red]")
        return
    if not db_exists and dry_run:
        console.print("[yellow]Database not initialized. Dry-run will skip DB comparison.[/yellow]")
    db = DatabaseManager() if db_exists else None
    with Progress() as progress:
        task = progress.add_task("[cyan]Discovering projects...", total=None)
        projects = discover_projects(PROJECTS_BASE_DIR)
        progress.update(task, completed=True)
    console.print(f"\n[green]Found {len(projects)} projects[/green]\n")
    existing_projects = db.get_all_projects() if db_exists else []
    existing_count = len(existing_projects)
    if not force:
        if len(projects) == 0:
            subdir_count = len([p for p in base_path.iterdir() if p.is_dir() and not p.name.startswith(".")])
            console.print("[red]Scan found 0 projects. Aborting to prevent accidental data loss.[/red]")
            console.print(f"[yellow]Detected {subdir_count} subdirectories under PROJECTS_BASE_DIR.[/yellow]")
            console.print("[yellow]Re-run with --force if this is expected.[/yellow]")
            return
        if existing_count > 0 and len(projects) < max(1, int(existing_count * 0.5)):
            console.print("[red]Scan found far fewer projects than expected. Aborting to prevent data loss.[/red]")
            console.print(f"[yellow]Previous count: {existing_count}, New count: {len(projects)}[/yellow]")
            console.print("[yellow]Re-run with --force if this is expected.[/yellow]")
            return
    if dry_run:
        console.print("[dim]Dry-run: skipping health checks and database writes.[/dim]")
        return
    with Progress() as progress:
        task = progress.add_task("[cyan]Auditing project health...", total=len(projects))
        health_results = scan_health_parallel(projects)
        progress.update(task, advance=len(projects))
    existing_ids = {p["id"] for p in existing_projects}
    discovered_ids = {p["id"] for p in projects}
    stale_ids = existing_ids - discovered_ids
    if stale_ids:
        console.print(f"  [dim]ℹ {len(stale_ids)} projects not found in scan (preserved in DB)[/dim]")
    console.print(f"\n[bold blue]Loading services from EXTERNAL_RESOURCES.md...[/bold blue]")
    services_by_project = parse_external_resources()
    for project in projects:
        with db._get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("BEGIN")
                db._add_project_with_cursor(
                    cursor=cursor, project_id=project["id"], name=project["name"],
                    path=project["path"], status=project["status"],
                    description=project.get("description"), phase=project.get("phase"),
                    last_modified=project["last_modified"],
                    completion_pct=project.get("completion_pct", 0),
                    is_infrastructure=project.get("is_infrastructure", False),
                    has_index=project.get("has_index", False),
                    index_is_valid=project.get("index_is_valid", False),
                    index_updated_at=project.get("index_updated_at"),
                    project_type=project.get("project_type", "standard"),
                )
                _sync_portfolio_project_info(db, cursor, project)
                db._sync_ai_agents_with_cursor(cursor=cursor, project_id=project["id"], agents=project.get("ai_agents", []))
                db._sync_cron_jobs_with_cursor(cursor=cursor, project_id=project["id"], cron_jobs=project.get("cron_jobs", []))
                db._sync_services_with_cursor(cursor=cursor, project_id=project["id"], services=services_by_project.get(project["id"], []))
                health = health_results.get(project["id"])
                if health:
                    db._update_health_with_cursor(cursor=cursor, project_id=project["id"], score=health["score"], grade=health["grade"])
                conn.commit()
                console.print(f"  ✓ {project['name']}")
            except Exception as e:
                conn.rollback()
                console.print(f"  [red]✗ Failed to update {project['name']}: {e}[/red]")
                continue
    services_skipped = 0
    known_project_ids = {p["id"] for p in db.get_all_projects()}
    for project_id in services_by_project.keys():
        if project_id not in known_project_ids:
            services_skipped += 1
            console.print(f"  [yellow]! Skipping services for unknown project: {project_id}[/yellow]")
    if services_skipped > 0:
        console.print(f"  [yellow]! Skipped services for {services_skipped} unknown projects[/yellow]")
    if not no_graph:
        console.print("")
        rebuild_project_graph()
    console.print(f"\n[bold green]✅ Scan complete! {len(projects)} projects updated[/bold green]")


def _has_complete_prompt(prompt):
    if not prompt: return False
    prompt_lower = prompt.lower()
    return "## overview" in prompt_lower and "## execution" in prompt_lower and "## done criteria" in prompt_lower


def _display_tasks(task_list, project=None, json_output=False, db=None):
    import json as json_lib
    if json_output:
        backend = "turso" if _USE_TURSO else "local"
        print(json_lib.dumps({"tasks": task_list, "total": len(task_list), "backend": backend}, indent=2))
        return
    if not task_list:
        filter_msg = f" for project '{project}'" if project else ""
        print(f"No tasks found{filter_msg}.")
        return
    backend_tag = "turso" if _USE_TURSO else "local"
    title = f"Tasks - {project}" if project else "Tasks - all projects"
    print(f"{title} [{backend_tag}]\n")
    display_map = db.get_task_display_id_map([t["id"] for t in task_list]) if db else {}
    for task in task_list:
        priority = task.get("priority") or "-"
        status = task["status"]
        task_id = task["id"]
        task_text = task["text"]
        label = display_map.get(task_id, task_id)
        if _has_complete_prompt(task.get("prompt")): prompt_marker = ""
        elif task.get("prompt"): prompt_marker = "[~P] "
        else: prompt_marker = "[!P] "
        blocked_marker = ""
        if db and task.get("blocked_by"):
            is_blocked, blocking_ids = db.is_blocked(task_id)
            if is_blocked:
                blocked_marker = f"[B:{','.join(str(i) for i in blocking_ids)}] "
        if project:
            print(f"#{label} {prompt_marker}{blocked_marker}| {status} | {priority} | {task_text}")
        else:
            print(f"#{label} {prompt_marker}{blocked_marker}| {task['project_id']} | {status} | {priority} | {task_text}")
    status_counts = {}
    for task in task_list:
        status_counts[task["status"]] = status_counts.get(task["status"], 0) + 1
    summary_parts = [f"{s}: {status_counts[s]}" for s in ["Backlog", "To Do", "In Progress", "Review", "Done", "Cancelled"] if s in status_counts]
    print(f"\nTotal: {len(task_list)} tasks ({', '.join(summary_parts)})")


def _resolve_project_id(db, project):
    if not project: return None
    projects = db.get_all_projects()
    for p in projects:
        if p["name"].lower() == project.lower() or p["id"].lower() == project.lower():
            return p["id"]
    return None


def _resolve_task_id(db, token: int) -> int:
    """Resolve a display_id or Snowflake task_id to the canonical task PK.

    Returns the resolved task_id, or token unchanged if resolution fails
    (callers that pass a bad ID will get a "not found" from get_task anyway).
    """
    resolved = db.resolve_task_id(token)
    return resolved if resolved is not None else token


def _detect_project_from_cwd(db):
    import os
    cwd = os.environ.get("PT_CALLER_CWD", os.getcwd())
    dir_name = os.path.basename(cwd)
    return _resolve_project_id(db, dir_name)


# =============================================================================
# Top-level commands
# =============================================================================

@cli.command()
def init():
    """Initialize the project tracker database."""
    console.print("[bold green]Initializing project tracker...[/bold green]")
    db_path = init_db()
    console.print(f"✅ Database created at: {db_path}")


def scan(no_graph, dry_run, force):
    """Scan projects directory and update database."""
    _scan_impl(no_graph=no_graph, dry_run=dry_run, force=force)


@cli.command(name="scan")
@click.option("--no-graph", is_flag=True, help="Skip rebuilding the project graph")
@click.option("--dry-run", is_flag=True, help="Show what would change without writing")
@click.option("--force", is_flag=True, help="Proceed even if scan results look unsafe")
def scan_cli(no_graph, dry_run, force):
    """Scan projects directory and update database."""
    scan(no_graph=no_graph, dry_run=dry_run, force=force)


@cli.command(name="list")
def list_projects():
    """List all projects."""
    db = DatabaseManager()
    projects = db.get_all_projects()
    if not projects:
        print("No projects found. Run 'pt scan' first.")
        return
    print("Projects\n")
    for project in projects:
        idx = "✓" if project.get("has_index") and project.get("index_is_valid") else "!"
        phase = project.get("phase") or "-"
        pct = project.get("completion_pct", 0)
        print(f"{project['name']} | {project['status']} | {phase} | {pct}% | {idx}")
    print(f"\nTotal: {len(projects)} projects")


@cli.command()
@click.argument("name")
def status(name):
    """Show detailed status for a project."""
    db = DatabaseManager()
    projects = db.get_all_projects()
    project = None
    for p in projects:
        if p["name"].lower() == name.lower():
            project = p
            break
    if not project:
        console.print(f"[red]Project '{name}' not found[/red]")
        return
    console.print(f"\n[bold cyan]{project['name']}[/bold cyan]")
    console.print(f"Path: {project['path']}")
    console.print(f"Status: [green]{project['status']}[/green]")
    if project.get("phase"): console.print(f"Phase: {project['phase']}")
    console.print(f"Progress: {project.get('completion_pct', 0)}%")
    console.print(f"Last Modified: {project.get('last_modified', 'unknown')}")
    if project.get("description"): console.print(f"\n{project['description']}")
    agents = db.get_ai_agents(project["id"])
    if agents:
        console.print("\n[bold]AI Agents:[/bold]")
        for agent in agents:
            role = f" - {agent['role']}" if agent.get('role') else ""
            console.print(f"  • {agent['agent_name']}{role}")
    jobs = db.get_cron_jobs(project["id"])
    if jobs:
        console.print("\n[bold]Cron Jobs:[/bold]")
        for job in jobs:
            console.print(f"  • {job['schedule']}: {job['command']}")
    services = db.get_services(project["id"])
    if services:
        console.print("\n[bold]Services:[/bold]")
        for service in services:
            cost = f" (${service['cost_monthly']}/mo)" if service.get('cost_monthly') else ""
            console.print(f"  • {service['service_name']}{cost}")
    console.print()


@cli.command()
@click.option("-p", "--project", default=None, help="Filter by project name")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def orphans(project, json_output):
    """List all orphan files (files with no connections)."""
    import json
    graph_path = Path(__file__).parent.parent / "data" / "graph.json"
    if not graph_path.exists():
        console.print("[red]Graph data not found. Run './pt scan' first.[/red]")
        return
    with open(graph_path) as f:
        graph_data = json.load(f)
    orphan_nodes = [node for node in graph_data["nodes"] if node.get("is_orphan", False)]
    if project:
        orphan_nodes = [node for node in orphan_nodes if node["project"] == project]
    if not orphan_nodes:
        if project:
            console.print(f"[green]✓ No orphan files found in project '{project}'[/green]")
        else:
            console.print("[green]✓ No orphan files found in the ecosystem[/green]")
        return
    if json_output:
        output = {"total_orphans": len(orphan_nodes), "orphans": [{"path": n["id"], "name": n["name"], "project": n["project"], "type": n["type"]} for n in orphan_nodes]}
        print(json.dumps(output, indent=2))
        return
    orphans_by_project = {}
    for node in orphan_nodes:
        proj = node["project"]
        if proj not in orphans_by_project: orphans_by_project[proj] = []
        orphans_by_project[proj].append(node)
    console.print(f"\n[bold yellow]Found {len(orphan_nodes)} orphan files[/bold yellow]\n")
    for proj, nodes in sorted(orphans_by_project.items()):
        console.print(f"[cyan]{proj}[/cyan] ({len(nodes)} orphans):")
        for node in sorted(nodes, key=lambda n: n["id"]):
            console.print(f"  • {node['id']}")
        console.print()
    console.print(f"[dim]Total: {len(orphan_nodes)} orphans across {len(orphans_by_project)} projects[/dim]")
    console.print(f"[dim]Tip: Use '--project <name>' to filter by project[/dim]")


@cli.command()
@click.option("--no-graph", is_flag=True, help="Skip rebuilding the project graph")
def refresh(no_graph):
    """Refresh all project metadata."""
    console.print("[bold blue]Refreshing project data...[/bold blue]")
    _scan_impl(no_graph=no_graph)


@cli.command(name="sync-project")
@click.argument("project_name")
@click.option("--no-graph", is_flag=True, help="Skip rebuilding the project graph")
def sync_project(project_name, no_graph):
    """Sync one project to the database (fast alternative to full scan).

    PROJECT_NAME is the directory name under the projects root.
    This is distinct from ``pt sync``, which manages replication state.
    """
    base_path = Path(PROJECTS_BASE_DIR)
    project_dir = _resolve_project_directory(project_name)

    if not project_dir or not project_dir.exists() or not project_dir.is_dir():
        console.print(f"[red]Directory not found for project '{project_name}' under {base_path}[/red]")
        raise SystemExit(1)

    db_path = get_db_path()
    if not db_path.exists():
        console.print("[red]Database not initialized. Run './pt init' first.[/red]")
        raise SystemExit(1)

    console.print(f"[bold blue]Syncing project: {project_name}...[/bold blue]")

    # 1. Extract metadata (same as full scan)
    project = extract_project_metadata(project_dir)
    if not project:
        console.print(f"[red]Could not extract metadata from {project_dir}[/red]")
        raise SystemExit(1)

    # 2. Health check
    health_results = scan_health_parallel([project])

    # 3. Load external services for this project
    services_by_project = parse_external_resources()

    # 4. Upsert to database
    db = DatabaseManager()
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
            _sync_portfolio_project_info(db, cursor, project)
            db._sync_ai_agents_with_cursor(
                cursor=cursor, project_id=project["id"],
                agents=project.get("ai_agents", []),
            )
            db._sync_cron_jobs_with_cursor(
                cursor=cursor, project_id=project["id"],
                cron_jobs=project.get("cron_jobs", []),
            )
            db._sync_services_with_cursor(
                cursor=cursor, project_id=project["id"],
                services=services_by_project.get(project["id"], []),
            )
            health = health_results.get(project["id"])
            if health:
                db._update_health_with_cursor(
                    cursor=cursor, project_id=project["id"],
                    score=health["score"], grade=health["grade"],
                )
            conn.commit()
            console.print(f"  [green]✓ {project['name']}[/green]")
        except Exception as e:
            conn.rollback()
            console.print(f"  [red]✗ Failed to sync {project['name']}: {e}[/red]")
            raise SystemExit(1)

    # 5. Optionally rebuild project graph
    if not no_graph:
        rebuild_project_graph()

    console.print(f"\n[bold green]✅ Synced: {project['name']}[/bold green]")


@cli.command()
@click.option("--json", "json_output", is_flag=True, help="Output stable machine-readable JSON (schema: pt.hygiene.v1)")
@click.option("--project", "project_name", default=None, help="Inspect only one repo by name")
@click.option("--quiet", is_flag=True, help="Only show repos with at least one finding")
def hygiene(json_output: bool, project_name: Optional[str], quiet: bool) -> None:
    """Check portfolio-wide git hygiene state.

    Detects: dirty working tree, local-only branches, branches ahead of remote,
    stashes, open bot PRs older than 24h, and stale PROGRESS.md files.

    Exit 0 = all repos clean; exit 6 = at least one finding.
    """
    from datetime import timezone

    # Read at runtime so test harnesses can override via env var
    _projects_root_env = os.environ.get("PROJECTS_ROOT", "")
    projects_root = Path(_projects_root_env).resolve() if _projects_root_env.strip() else Path(PROJECTS_BASE_DIR)

    # Collect git repos to inspect
    if project_name:
        candidate = projects_root / project_name
        if not candidate.is_dir() or not (candidate / ".git").exists():
            err = PtJsonError(
                "validation",
                f"project '{project_name}' not found or not a git repo under {projects_root}",
                EXIT_VALIDATION,
            )
            if json_output:
                _emit_json_error(err, "hygiene")
            else:
                raise click.ClickException(err.message)
        repo_dirs = [candidate]
    else:
        repo_dirs = sorted(
            d for d in projects_root.iterdir() if d.is_dir() and (d / ".git").exists()
        )

    results = []
    for repo_dir in repo_dirs:
        try:
            repo_result = _hygiene_scan_repo(repo_dir, json_output)
        except Exception as exc:  # noqa: BLE001 — isolate per-repo failures
            repo_result = {
                "project": repo_dir.name,
                "path": str(repo_dir),
                "clean": False,
                "findings": {},
                "error": {
                    "class": exc.__class__.__name__,
                    "message": str(exc),
                },
            }
        results.append(repo_result)

    clean_count = sum(1 for r in results if r["clean"])
    findings_count = len(results) - clean_count
    has_findings = findings_count > 0

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if json_output:
        payload = {
            "schema_version": PT_HYGIENE_SCHEMA_VERSION,
            "ok": not has_findings,
            "command": "hygiene",
            "scanned_at": now_utc,
            "projects_root": str(projects_root),
            "summary": {
                "total_repos": len(results),
                "clean_repos": clean_count,
                "repos_with_findings": findings_count,
            },
            "results": results,
        }
        _emit_json(payload)
    else:
        for r in results:
            if quiet and r["clean"]:
                continue
            status = "clean" if r["clean"] else "FINDINGS"
            console.print(f"[bold]{r['project']}[/bold] ({r['path']}) — {status}")
            if not r["clean"]:
                if "error" in r:
                    err = r["error"]
                    console.print(f"  [red]scan error ({err['class']}):[/red] {err['message']}")
                    continue
                f = r["findings"]
                if f["dirty_tree"]["present"]:
                    files = ", ".join(f["dirty_tree"]["files"][:5])
                    console.print(f"  [yellow]dirty tree:[/yellow] {files}")
                if f["local_only_branches"]["present"]:
                    branches = ", ".join(f["local_only_branches"]["branches"])
                    console.print(f"  [yellow]local-only branches:[/yellow] {branches}")
                if f["branches_ahead_of_remote"]["present"]:
                    ahead = ", ".join(
                        f"{b['name']} (+{b['ahead']})"
                        for b in f["branches_ahead_of_remote"]["branches"]
                    )
                    console.print(f"  [yellow]branches ahead:[/yellow] {ahead}")
                if f["stashes"]["present"]:
                    console.print(f"  [yellow]stashes:[/yellow] {f['stashes']['count']}")
                if f["open_pr_drift"].get("present"):
                    for pr in f["open_pr_drift"]["prs"]:
                        console.print(
                            f"  [yellow]open bot PR #{pr['number']}[/yellow]: {pr['title']} "
                            f"({pr['age_hours']:.1f}h old)"
                        )
                if f["stale_progress_md"]["present"]:
                    console.print(
                        f"  [yellow]stale PROGRESS.md:[/yellow] {f['stale_progress_md']['age_days']} days old"
                    )

    if has_findings:
        raise SystemExit(EXIT_HYGIENE_FINDING)


def _hygiene_scan_repo(repo_dir: Path, json_mode: bool) -> dict:
    """Run all hygiene detections for a single git repo directory."""
    findings = {
        "dirty_tree": _hygiene_dirty_tree(repo_dir),
        "local_only_branches": _hygiene_local_only_branches(repo_dir),
        "branches_ahead_of_remote": _hygiene_branches_ahead(repo_dir),
        "stashes": _hygiene_stashes(repo_dir),
        "open_pr_drift": _hygiene_open_pr_drift(repo_dir),
        "stale_progress_md": _hygiene_stale_progress_md(repo_dir),
    }
    clean = not any(
        (v.get("present", False) if isinstance(v, dict) else False)
        for v in findings.values()
    )
    return {
        "project": repo_dir.name,
        "path": str(repo_dir),
        "clean": clean,
        "findings": findings,
    }


def _run_git(repo_dir: Path, args: list[str], timeout: int = 10) -> tuple[str, int]:
    """Run a git command in repo_dir. Returns (stdout, returncode)."""
    result = subprocess.run(
        ["git"] + args,
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.stdout, result.returncode


def _hygiene_non_progress_dirty_files(repo_dir: Path) -> list[str]:
    """Return dirty file paths from `git status --porcelain`, excluding PROGRESS.md.

    Shared by `_hygiene_dirty_tree` (for the finding) and
    `_hygiene_stale_progress_md` (to decide whether the repo has uncommitted
    work other than PROGRESS.md). Returns an empty list on git failures.
    """
    try:
        stdout, rc = _run_git(repo_dir, ["status", "--porcelain"])
    except (subprocess.TimeoutExpired, OSError):
        return []

    dirty_files: list[str] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        # porcelain format: XY filename (or "XY src -> dst" for renames).
        # columns 0-1 are status codes, column 2 is space, rest is filename.
        path_part = line[3:].strip()
        # For renames: "old -> new", take the new path
        if " -> " in path_part:
            path_part = path_part.split(" -> ", 1)[1]
        # Exclude PROGRESS.md (documented always-dirty file)
        if path_part == "PROGRESS.md" or path_part.endswith("/PROGRESS.md"):
            continue
        dirty_files.append(path_part)

    return dirty_files


def _hygiene_dirty_tree(repo_dir: Path) -> dict:
    """Detect dirty working tree, excluding PROGRESS.md."""
    dirty_files = _hygiene_non_progress_dirty_files(repo_dir)
    return {"present": bool(dirty_files), "files": dirty_files}


def _hygiene_local_only_branches(repo_dir: Path) -> dict:
    """Detect local branches with no upstream tracking remote."""
    try:
        stdout, rc = _run_git(
            repo_dir, ["branch", "--format=%(refname:short) %(upstream)"]
        )
    except (subprocess.TimeoutExpired, OSError):
        return {"present": False, "branches": []}

    local_only = []
    for line in stdout.splitlines():
        parts = line.strip().split(" ", 1)
        branch = parts[0]
        upstream = parts[1].strip() if len(parts) > 1 else ""
        # Skip main/master/trunk — they may not have upstreams in some setups
        if branch in ("main", "master", "trunk"):
            continue
        if not upstream:
            local_only.append(branch)

    return {"present": bool(local_only), "branches": local_only}


def _hygiene_branches_ahead(repo_dir: Path) -> dict:
    """Detect local branches with commits not yet on their upstream.

    Strategy: list branches with upstreams via for-each-ref, then for each
    one, count `git rev-list --count <upstream>..<branch>`. This works even
    when `origin/HEAD` is missing (common in fresh clones / test fixtures)
    and avoids relying on the for-each-ref %(ahead-behind:...) atom which
    requires a concrete ref argument.
    """
    try:
        stdout, rc = _run_git(
            repo_dir,
            ["for-each-ref", "--format=%(refname:short)|%(upstream:short)", "refs/heads"],
        )
    except (subprocess.TimeoutExpired, OSError):
        return {"present": False, "branches": []}

    ahead_branches = []
    for line in stdout.splitlines():
        if "|" not in line:
            continue
        branch, upstream = line.split("|", 1)
        branch = branch.strip()
        upstream = upstream.strip()
        if not upstream:
            # No upstream -> handled by local_only_branches finding instead
            continue
        try:
            count_out, count_rc = _run_git(
                repo_dir, ["rev-list", "--count", f"{upstream}..{branch}"]
            )
        except (subprocess.TimeoutExpired, OSError):
            continue
        if count_rc != 0:
            continue
        try:
            ahead = int(count_out.strip())
        except ValueError:
            continue
        if ahead > 0:
            ahead_branches.append({"name": branch, "ahead": ahead})

    return {"present": bool(ahead_branches), "branches": ahead_branches}


def _hygiene_stashes(repo_dir: Path) -> dict:
    """Detect stashes (count > 0)."""
    try:
        stdout, rc = _run_git(repo_dir, ["stash", "list"])
    except (subprocess.TimeoutExpired, OSError):
        return {"present": False, "count": 0}

    count = len([line for line in stdout.splitlines() if line.strip()])
    return {"present": count > 0, "count": count}


def _hygiene_open_pr_drift(repo_dir: Path) -> dict:
    """Detect open PRs older than 24h authored by *[bot] identities.

    Uses gh CLI. If gh is unavailable or auth fails, returns available=False.
    """
    gh_bin = shutil.which("gh")
    if not gh_bin:
        return {"available": False, "present": False, "prs": [], "reason": "gh not found"}

    try:
        # Try to get the remote URL to determine owner/repo
        remote_stdout, rc = _run_git(repo_dir, ["remote", "get-url", "origin"])
        if rc != 0 or not remote_stdout.strip():
            return {"available": False, "present": False, "prs": [], "reason": "no git remote origin"}
        remote_url = remote_stdout.strip()
        # Parse owner/repo from remote URL (https or ssh)
        import re
        m = re.search(r"[:/]([^/]+/[^/.]+?)(?:\.git)?$", remote_url)
        if not m:
            return {"available": False, "present": False, "prs": [], "reason": f"cannot parse remote: {remote_url}"}
        repo_slug = m.group(1)

        result = subprocess.run(
            [
                gh_bin, "pr", "list",
                "--repo", repo_slug,
                "--state", "open",
                "--json", "number,title,author,createdAt",
                "--limit", "50",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            reason = result.stderr.strip() or "gh returned non-zero"
            return {"available": False, "present": False, "prs": [], "reason": reason}

        prs_raw = json.loads(result.stdout)
        from datetime import timezone
        now = datetime.now(timezone.utc)
        bot_old_prs = []
        for pr in prs_raw:
            author = pr.get("author", {}).get("login", "")
            if not author.endswith("[bot]"):
                continue
            created_at_str = pr.get("createdAt", "")
            try:
                created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                age_hours = (now - created_at).total_seconds() / 3600
            except (ValueError, TypeError):
                age_hours = 0
            if age_hours > 24:
                bot_old_prs.append({
                    "number": pr["number"],
                    "title": pr["title"],
                    "age_hours": round(age_hours, 1),
                    "author": author,
                })

        return {"available": True, "present": bool(bot_old_prs), "prs": bot_old_prs}

    except subprocess.TimeoutExpired:
        return {"available": False, "present": False, "prs": [], "reason": "gh timed out"}
    except (OSError, json.JSONDecodeError) as exc:
        return {"available": False, "present": False, "prs": [], "reason": str(exc)}


def _hygiene_stale_progress_md(repo_dir: Path) -> dict:
    """Detect a PROGRESS.md that is older than 7 days AND the repo has uncommitted work."""
    from datetime import timezone
    progress_path = repo_dir / "PROGRESS.md"
    if not progress_path.exists():
        return {"present": False, "age_days": None}

    # Check age
    mtime = progress_path.stat().st_mtime
    now_ts = datetime.now(timezone.utc).timestamp()
    age_days = (now_ts - mtime) / 86400
    if age_days <= 7:
        return {"present": False, "age_days": round(age_days, 1)}

    # Check if repo has uncommitted work OTHER THAN PROGRESS.md itself.
    # PROGRESS.md is the documented always-dirty file (see project-tracker
    # CLAUDE.md), so a repo whose only dirty path is PROGRESS.md is not
    # "claiming progress without backing" — it has no claim either way.
    non_progress_dirty = _hygiene_non_progress_dirty_files(repo_dir)
    if not non_progress_dirty:
        return {"present": False, "age_days": round(age_days, 1)}

    return {"present": True, "age_days": round(age_days, 1)}


@cli.command()
@click.option("--port", default=8000, type=int, show_default=True, help="Port to run on")
@click.option("--no-scan", is_flag=True, help="Skip the initial project scan on launch")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
def launch(port, no_scan, reload):
    """Launch the web dashboard."""
    console.print("[bold green]Launching Project Tracker Dashboard...[/bold green]\n")
    init_db()
    if not no_scan:
        console.print("[dim]Running quick scan (graph rebuild deferred to background)...[/dim]")
        _scan_impl(no_graph=True)
    else:
        console.print("[yellow]Skipping initial scan. Using existing data.[/yellow]")
    dashboard_path = Path(__file__).parent.parent / "dashboard" / "app.py"
    if not dashboard_path.exists():
        console.print("[red]Error: Dashboard not found. Check installation.[/red]")
        return
    url = f"http://localhost:{port}"
    console.print(f"\n[bold green]✅ Dashboard starting at {url}[/bold green]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")
    import threading
    def open_browser():
        time.sleep(2)
        webbrowser.open(url)
    threading.Thread(target=open_browser, daemon=True).start()
    project_root = Path(__file__).parent.parent
    venv_python = _resolve_dashboard_python(project_root)
    bind_host = os.getenv("PT_DASHBOARD_HOST", "127.0.0.1")
    uvicorn_cmd = [str(venv_python), "-m", "uvicorn", "dashboard.app:app", "--host", bind_host, "--port", str(port)]
    if reload: uvicorn_cmd.append("--reload")
    # Secrets injected via doppler run (doppler.yaml in project root)
    doppler_bin = shutil.which("doppler")
    if not doppler_bin:
        console.print("[red]Error: doppler CLI not found. Install with: brew install doppler[/red]")
        raise SystemExit(1)
    cmd = [doppler_bin, "run", "--"] + uvicorn_cmd
    try:
        subprocess.run(cmd, cwd=project_root)
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Dashboard stopped[/yellow]")


@cli.command(name="add-agent")
@click.argument("project")
@click.argument("agent_name")
@click.argument("role", default="")
def add_agent(project, agent_name, role):
    """Add an AI agent to a project."""
    db = DatabaseManager()
    projects = db.get_all_projects()
    project_id = None
    for p in projects:
        if p["name"].lower() == project.lower(): project_id = p["id"]; break
    if not project_id:
        console.print(f"[red]Project '{project}' not found[/red]"); return
    db.add_ai_agent(project_id, agent_name, role)
    console.print(f"[green]✅ Added AI agent '{agent_name}' to {project}[/green]")


@cli.command(name="add-cron")
@click.argument("project")
@click.argument("schedule")
@click.argument("command")
@click.argument("description", default="")
def add_cron(project, schedule, command, description):
    """Add a cron job to a project."""
    db = DatabaseManager()
    projects = db.get_all_projects()
    project_id = None
    for p in projects:
        if p["name"].lower() == project.lower(): project_id = p["id"]; break
    if not project_id:
        console.print(f"[red]Project '{project}' not found[/red]"); return
    db.add_cron_job(project_id, schedule, command, description)
    console.print(f"[green]✅ Added cron job to {project}[/green]")


@cli.command(name="add-service")
@click.argument("project")
@click.argument("service_name")
@click.option("--cost", default=0.0, type=float, help="Monthly cost")
@click.option("--purpose", default="", help="Purpose of the service")
def add_service(project, service_name, cost, purpose):
    """Add a service dependency to a project."""
    db = DatabaseManager()
    projects = db.get_all_projects()
    project_id = None
    for p in projects:
        if p["name"].lower() == project.lower(): project_id = p["id"]; break
    if not project_id:
        console.print(f"[red]Project '{project}' not found[/red]"); return
    db.add_service(project_id, service_name, purpose, cost)
    console.print(f"[green]✅ Added service '{service_name}' to {project}[/green]")


@cli.command(name="export-projects")
@click.option("-o", "--output", default="data/projects_export.json", help="Output file path")
def export_projects(output):
    """Export all projects to JSON file for backup."""
    import json as json_lib
    from datetime import datetime, timezone
    db = DatabaseManager()
    projects = db.get_all_projects()
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        projects_dict = [dict(p) for p in projects]
        export_data = {"exported_at": datetime.now(timezone.utc).isoformat(), "total_count": len(projects), "projects": projects_dict}
        with open(output_path, 'w') as f:
            json_lib.dump(export_data, f, indent=2)
        console.print(f"[green]✅ Exported {len(projects)} projects to {output}[/green]")
    except Exception as e:
        console.print(f"[red]Failed to export projects: {e}[/red]")


@cli.command(name="remove-project")
@click.argument("project")
def remove_project(project):
    """Remove a single project from the database (not from disk).

    ⚠️  REQUIRES DIRECT CONSENT FROM ERIK.
    Do not run this command without explicit approval from Erik Sjaastad.
    This removes the project entry and all associated data (tasks, cron jobs,
    agents, services) from the tracker database. It does NOT delete any files
    from disk.
    """
    db = DatabaseManager()
    projects = db.get_all_projects()
    target = None
    for p in projects:
        if p["name"].lower() == project.lower():
            target = p
            break
    if not target:
        console.print(f"[red]Project '{project}' not found in database.[/red]")
        return

    # Show what will be deleted
    project_id = target["id"]
    tasks = db.get_tasks(project_id=project_id)
    cron_jobs = db.get_cron_jobs(project_id)
    agents = db.get_ai_agents(project_id)

    console.print(f"\n[bold red]⚠️  DESTRUCTIVE OPERATION[/bold red]")
    console.print(f"[bold]Project:[/bold] {target['name']}")
    console.print(f"[bold]Path:[/bold] {target.get('path', 'unknown')}")
    console.print(f"[bold]Tasks:[/bold] {len(tasks)}")
    console.print(f"[bold]Cron jobs:[/bold] {len(cron_jobs)}")
    console.print(f"[bold]AI agents:[/bold] {len(agents)}")
    console.print(f"\nThis will remove the project and ALL associated data from the database.")
    console.print(f"[dim]No files on disk will be affected. A backup is created automatically.[/dim]\n")

    confirm = click.prompt(
        "Type the project name to confirm deletion",
        default="",
        show_default=False,
    )
    if confirm.lower() != target["name"].lower():
        console.print("[yellow]Cancelled. Project name did not match.[/yellow]")
        return

    db.delete_project(project_id)
    console.print(f"[green]✅ Removed '{target['name']}' from the database.[/green]")


@cli.group(name="project")
def project_group():
    """Manage manually tracked project records."""
    pass


@project_group.command(name="add")
@click.argument("project_id")
@click.option("--name", default=None, help="Display name. Defaults to PROJECT_ID.")
@click.option("--path", "project_path", default=None, help="Existing project directory for non-virtual projects.")
@click.option("--virtual", is_flag=True, help="Create a board-only project with no filesystem directory.")
@click.option("--description", default=None, help="Project description.")
@click.option("--status", default="active", help="Project status.")
def project_add(project_id, name, project_path, virtual, description, status):
    """Add a project record without running a filesystem scan.

    Virtual projects are board-only records. They intentionally use a
    virtual:// path and do not create a directory under PROJECTS_ROOT.
    """
    cleaned_id = project_id.strip()
    allowed_slug_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    if not cleaned_id or any(ch not in allowed_slug_chars for ch in cleaned_id):
        raise click.ClickException("Project ID must be a simple slug, e.g. openclaw")

    if virtual and project_path:
        raise click.ClickException("Use either --virtual or --path, not both")

    if not virtual and not project_path:
        raise click.ClickException("Provide --virtual for board-only projects or --path for real directories")

    if virtual:
        resolved_path = f"virtual://{cleaned_id}"
        project_type = "virtual"
    else:
        path_obj = Path(project_path).expanduser().resolve()
        if not path_obj.is_dir():
            raise click.ClickException(f"Project path does not exist or is not a directory: {path_obj}")
        resolved_path = str(path_obj)
        project_type = "standard"

    db = DatabaseManager()
    if db.get_project(cleaned_id):
        raise click.ClickException(f"Project '{cleaned_id}' already exists")

    display_name = name.strip() if name and name.strip() else cleaned_id
    now = datetime.now().isoformat()
    db.add_project(
        project_id=cleaned_id,
        name=display_name,
        path=resolved_path,
        status=status,
        description=description,
        last_modified=now,
        project_type=project_type,
    )

    console.print(
        f"[green]✅ Added {'virtual ' if virtual else ''}project '{display_name}' "
        f"({cleaned_id})[/green]"
    )
    console.print(f"[dim]Path: {resolved_path}[/dim]")


def _scan_portfolio_for_references(project_id: str, project_name: str, projects_root: Path) -> tuple[list[tuple[Path, int, str]], list[tuple[Path, str]]]:
    """Scan portfolio markdown/yaml/json for stale references to a project.

    Returns (hits, scan_errors) where:
      - hits: list of (path, line_number, matched_line) tuples
      - scan_errors: list of (path, error_message) for paths the scan couldn't read

    Read-only — never mutates files. Used by retire-project to print a
    manual-cleanup report for the human.
    """
    import logging
    _log = logging.getLogger(__name__)
    hits: list[tuple[Path, int, str]] = []
    scan_errors: list[tuple[Path, str]] = []
    needles = {project_id.lower()}
    if project_name and project_name.lower() != project_id.lower():
        needles.add(project_name.lower())
    exts = {".md", ".yaml", ".yml", ".json"}
    skip_dirs = {".git", "node_modules", "venv", ".venv", "__pycache__", "data", "backups", "_archive"}
    for root, dirs, files in os.walk(projects_root):
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
        root_path = Path(root)
        # Skip the project being retired itself
        try:
            if root_path.resolve().is_relative_to((projects_root / project_id).resolve()):
                continue
        except (ValueError, OSError) as e:
            _log.warning(f"retire-project: could not resolve path {root_path} for skip check: {e}")
            scan_errors.append((root_path, f"resolve: {e}"))
        for f in files:
            if Path(f).suffix.lower() not in exts:
                continue
            fp = root_path / f
            try:
                with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                    for lineno, line in enumerate(fh, 1):
                        lowered = line.lower()
                        if any(n in lowered for n in needles):
                            hits.append((fp, lineno, line.rstrip()))
                            if sum(1 for h in hits if h[0] == fp) >= 10:
                                break
            except (OSError, UnicodeDecodeError) as e:
                _log.warning(f"retire-project: could not scan {fp}: {e}")
                scan_errors.append((fp, str(e)))
                continue
    return hits, scan_errors


@cli.command(name="retire-project")
@click.argument("project")
@click.option("--execute", is_flag=True, help="Actually retire. Without this, runs in dry-run mode.")
@click.option("--keep-files", is_flag=True, help="Skip sending the project directory to Trash.")
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt.")
def retire_project(project, execute, keep_files, yes):
    """Retire a project: trash the directory, cascade-delete DB rows, and audit stale refs.

    DRY-RUN BY DEFAULT. Prints the plan and the stale-reference audit without
    touching anything. Pass --execute to actually perform the retirement.

    What retire does:
      1. Sends the project directory to Trash (via send2trash; never rm)
      2. Deletes the project row and cascade-deletes tasks, cron jobs, agents,
         and service dependencies via db.delete_project()
      3. Prints a report of stale references to this project found in other
         projects' markdown/yaml/json (for manual review — retire never
         auto-edits files outside the retired project).

    Use --keep-files to retire from the DB only, leaving the directory intact.
    """
    from send2trash import send2trash

    db = DatabaseManager()
    projects = db.get_all_projects()
    target = None
    for p in projects:
        if p["id"].lower() == project.lower() or p["name"].lower() == project.lower():
            target = p
            break
    if not target:
        console.print(f"[red]Project '{project}' not found in database.[/red]")
        sys.exit(1)

    project_id = target["id"]
    project_name = target["name"]
    project_path = Path(target.get("path") or "")

    tasks = db.get_tasks(project_id=project_id)
    cron_jobs = db.get_cron_jobs(project_id)
    agents = db.get_ai_agents(project_id)

    mode = "[bold yellow]DRY RUN[/bold yellow]" if not execute else "[bold red]EXECUTE[/bold red]"
    console.print(f"\n{mode} [bold]retire-project[/bold] — {project_name} ({project_id})")
    console.print(f"[bold]Path:[/bold]     {project_path}")
    path_ok = project_path.exists() if str(project_path) else False
    console.print(f"[bold]On disk:[/bold]  {'yes' if path_ok else 'no'}")
    console.print(f"[bold]Tasks:[/bold]    {len(tasks)} (cascade-delete)")
    console.print(f"[bold]Crons:[/bold]    {len(cron_jobs)} (cascade-delete)")
    console.print(f"[bold]Agents:[/bold]   {len(agents)} (cascade-delete)")
    if keep_files:
        console.print(f"[bold]Files:[/bold]    [yellow]--keep-files set; directory will remain on disk[/yellow]")
    else:
        console.print(f"[bold]Files:[/bold]    directory → Trash via send2trash")

    console.print("\n[bold]Stale reference audit[/bold] (read-only scan of portfolio):")
    refs, scan_errors = _scan_portfolio_for_references(project_id, project_name, PROJECTS_BASE_DIR)
    if scan_errors:
        console.print(f"  [yellow]⚠ {len(scan_errors)} path(s) could not be scanned (see log for details):[/yellow]")
        for err_path, err_msg in scan_errors[:5]:
            rel = err_path.relative_to(PROJECTS_BASE_DIR) if err_path.is_relative_to(PROJECTS_BASE_DIR) else err_path
            console.print(f"    [yellow]{rel}: {err_msg}[/yellow]")
        if len(scan_errors) > 5:
            console.print(f"    [dim]... and {len(scan_errors) - 5} more[/dim]")
    if not refs:
        console.print("  [green]no references found[/green]" + (" [dim](plus unreadable paths above)[/dim]" if scan_errors else ""))
    else:
        by_file: dict[Path, list[tuple[int, str]]] = {}
        for fp, lineno, line in refs:
            by_file.setdefault(fp, []).append((lineno, line))
        for fp, lines in sorted(by_file.items()):
            rel = fp.relative_to(PROJECTS_BASE_DIR) if fp.is_relative_to(PROJECTS_BASE_DIR) else fp
            console.print(f"  [cyan]{rel}[/cyan] ({len(lines)} hit{'s' if len(lines) != 1 else ''})")
            for lineno, line in lines[:3]:
                console.print(f"    [dim]{lineno}:[/dim] {line[:100]}")
            if len(lines) > 3:
                console.print(f"    [dim]... and {len(lines) - 3} more[/dim]")
        console.print("[yellow]Review the above manually after retire — retire does not edit other projects' files.[/yellow]")

    if not execute:
        console.print("\n[dim]Dry run complete. Re-run with --execute to retire for real.[/dim]")
        return

    if not yes:
        console.print(f"\n[bold red]⚠️  DESTRUCTIVE OPERATION[/bold red]")
        confirm = click.prompt(
            f"Type the project name '{project_name}' to confirm retirement",
            default="",
            show_default=False,
        )
        if confirm.lower() != project_name.lower():
            console.print("[yellow]Cancelled. Project name did not match.[/yellow]")
            sys.exit(1)

    # 1. Send directory to Trash (unless --keep-files)
    if not keep_files and path_ok:
        try:
            send2trash(str(project_path))
            console.print(f"[green]✓[/green] sent {project_path} to Trash")
        except Exception as e:
            console.print(f"[red]Failed to trash {project_path}: {e}[/red]")
            console.print("[yellow]Aborting before DB delete — directory is still on disk.[/yellow]")
            sys.exit(1)
    elif not keep_files and not path_ok:
        console.print(f"[dim]✓ directory already missing, nothing to trash[/dim]")

    # 2. Cascade-delete DB rows
    db.delete_project(project_id)
    console.print(f"[green]✓[/green] deleted project '{project_name}' and cascaded rows from the database")

    console.print(f"\n[bold green]✅ Retired '{project_name}'.[/bold green]")
    if refs:
        console.print(f"[yellow]Remember: {len(refs)} stale reference(s) in {len({r[0] for r in refs})} file(s) still need manual review.[/yellow]")


@cli.command()
@click.pass_context
def help(ctx):
    """Show this help message."""
    click.echo(ctx.parent.get_help())


# =============================================================================
# Backup group
# =============================================================================

@click.group(name="backup", invoke_without_command=True)
@click.pass_context
def backup_group(ctx):
    """Inspect backup health and restore from full database snapshots."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@backup_group.command(name="status")
@click.option("--json", "json_output", is_flag=True, help="Output status as JSON")
def backup_status(json_output: bool):
    """Show local and off-machine backup health for project-tracker."""
    status = get_backup_status()
    if json_output:
        click.echo(json.dumps(status, indent=2))
        return

    color = status.get("status_color", "blue")
    console.print(f"[bold]Backup Status:[/bold] [{color}]{status['status']}[/]")
    click.echo(status["message"])

    local = status["local_full"]
    click.echo(
        "Local full backup: "
        f"{local['message']} "
        f"(count: {local['count']}, path: {local['path'] or 'none'})"
    )

    safety = status["safety"]
    click.echo(
        "Task safety backup: "
        f"{safety['message']} "
        f"(count: {safety['count']}, path: {safety['path'] or 'none'})"
    )

    cloud = status["cloud"]
    cloud_suffix = f" target: {cloud['configured_dest']}" if cloud["configured_dest"] else ""
    click.echo(f"Off-machine copy: {cloud['message']}{cloud_suffix}")

    launch_agent = status["launch_agent"]
    if launch_agent["present"]:
        schedule = launch_agent.get("schedule") or "configured"
        click.echo(f"LaunchAgent: installed ({schedule}) at {launch_agent['path']}")
    else:
        click.echo(f"LaunchAgent: not found at {launch_agent['path']}")

    log = status["log"]
    if log["exists"]:
        click.echo(
            "Backup log: "
            f"last local success {log['last_local_success_age_human'] or 'unknown'} "
            f"({log['path']})"
        )
        if log["last_cloud_failure_at"] and log["last_cloud_failure_at"] != log["last_cloud_success_at"]:
            click.echo(
                "Last cloud-copy failure: "
                f"{log['last_cloud_failure_at']}"
                + (f" ({log['last_cloud_failure_detail']})" if log["last_cloud_failure_detail"] else "")
            )
    else:
        click.echo(f"Backup log: missing ({log['path']})")

    if status["remotes"]:
        click.echo(f"Rclone remotes: {', '.join(status['remotes'])}")


@backup_group.command(name="restore")
@click.argument("backup_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation")
def backup_restore(backup_file: Path, yes: bool):
    """Restore tracker.db from a full backup snapshot."""
    if not yes:
        confirm = click.confirm(
            f"Restore tracker database from '{backup_file}'? This replaces the live DB.",
            default=False,
        )
        if not confirm:
            click.echo("Cancelled")
            return

    try:
        result = restore_database(backup_file)
    except BackupRestoreError as err:
        console.print(f"[red]{err}[/red]")
        raise SystemExit(2)

    console.print(f"[green]Restored database from {result['source_backup']}[/green]")
    if result["pre_restore_backup"]:
        click.echo(f"Pre-restore backup: {result['pre_restore_backup']}")
    if result["removed_sidecars"]:
        click.echo("Removed stale sidecars:")
        for sidecar in result["removed_sidecars"]:
            click.echo(f"  - {sidecar}")


# =============================================================================
# Tasks group
# =============================================================================

@click.group(name="tasks", invoke_without_command=True)
@click.pass_context
@click.option("-p", "--project", default=None, help="Filter by project name or ID")
@click.option("-s", "--status", default=None, help="Filter by status (Backlog, To Do, In Progress, Review, Done)")
@click.option("-a", "--all", "show_all", is_flag=True, help="Include completed tasks")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.option("--needs-prompt", is_flag=True, help="Show only tasks without prompts")
@click.option("--ready", is_flag=True, help="Show To Do tasks with complete prompts (ready to start)")
@click.option("--proposals", is_flag=True, help="Show only proposal tasks")
def tasks_group(ctx, project, status, show_all, json_output, needs_prompt, ready, proposals):
    """Manage Kanban board tasks.

    \b
    Examples:
        ./pt tasks                       # Show open tasks (all projects)
        ./pt tasks -p project-tracker    # Tasks for a specific project
        ./pt tasks -s "In Progress"      # Filter by status
        ./pt tasks --all                 # Include completed tasks
        ./pt tasks --proposals           # Show only proposals
        ./pt tasks create "Fix bug" -p myproject

    """
    if ctx.invoked_subcommand is not None: return
    db = DatabaseManager()
    if project:
        project_id = _resolve_project_id(db, project)
        project_label = project
        if not project_id:
            console.print(f"[red]Project '{project}' not found[/red]"); return
    else:
        project_id = _detect_project_from_cwd(db)
        project_label = None
        if project_id:
            detected = db.get_project(project_id)
            project_label = detected["name"] if detected else None
    task_list = db.get_tasks(project_id=project_id, status=status)
    if proposals:
        task_list = [t for t in task_list if t.get("task_type") == "proposal"]
    else:
        # Hide proposals from default listing unless --all is used
        if not show_all:
            task_list = [t for t in task_list if t.get("task_type") != "proposal"]
        if not show_all and not status:
            task_list = [t for t in task_list if t["status"] not in ("Done", "Cancelled")]
    if needs_prompt:
        task_list = [t for t in task_list if not t.get("prompt")]
    if ready:
        task_list = [t for t in task_list if t["status"] == "To Do" and _has_complete_prompt(t.get("prompt"))]
    _display_tasks(task_list, project_label, json_output=json_output, db=db)


@tasks_group.command(name="list")
@click.option("-p", "--project", default=None, help="Filter by project name or ID")
@click.option("-s", "--status", default=None, help="Filter by status")
@click.option("-a", "--all", "show_all", is_flag=True, help="Include completed tasks")
@click.option("--board", is_flag=True, help="Show columnar Kanban board view")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.option("--needs-prompt", is_flag=True, help="Show only tasks without prompts")
@click.option("--ready", is_flag=True, help="Show To Do tasks with complete prompts")
@click.option("--proposals", is_flag=True, help="Show only proposal tasks")
def tasks_list(project, status, show_all, board, json_output, needs_prompt, ready, proposals):
    """List tasks from the Kanban board."""
    db = DatabaseManager()
    if project:
        project_id = _resolve_project_id(db, project)
        project_label = project
        if not project_id:
            console.print(f"[red]Project '{project}' not found[/red]"); return
    else:
        project_id = _detect_project_from_cwd(db)
        project_label = None
        if project_id:
            detected = db.get_project(project_id)
            project_label = detected["name"] if detected else None
    task_list = db.get_tasks(project_id=project_id, status=status)
    if proposals:
        task_list = [t for t in task_list if t.get("task_type") == "proposal"]
    else:
        if not show_all:
            task_list = [t for t in task_list if t.get("task_type") != "proposal"]
        if not show_all and not status:
            task_list = [t for t in task_list if t["status"] not in ("Done", "Cancelled")]
    if needs_prompt:
        task_list = [t for t in task_list if not t.get("prompt")]
    if ready:
        task_list = [t for t in task_list if t["status"] == "To Do" and _has_complete_prompt(t.get("prompt"))]
    if board and not json_output:
        statuses = ["Backlog", "To Do", "In Progress", "Review", "Done"]
        table = Table(show_header=True, header_style="bold")
        for col in statuses: table.add_column(col, width=20)
        def format_task(task):
            text = task["text"]
            if len(text) > 18: text = text[:17] + "..."
            label = f"#{task['id']} {text}"
            priority = task.get("priority")
            color = {"Critical": "red", "High": "red", "Medium": "yellow", "Low": "green"}.get(priority)
            return f"[{color}]{label}[/]" if color else label
        by_status = {s: [] for s in statuses}
        for task in task_list: by_status.get(task["status"], []).append(task)
        max_rows = max((len(by_status[s]) for s in statuses), default=0)
        max_rows = min(max_rows, 10)
        for i in range(max_rows):
            row = []
            for status_name in statuses:
                tasks = by_status[status_name]
                row.append(format_task(tasks[i]) if i < len(tasks) else "")
            table.add_row(*row)
        console.print(table)
        return
    _display_tasks(task_list, project_label, json_output=json_output, db=db)


@tasks_group.command(name="create")
@click.argument("text")
@click.option("-p", "--project", default=None, help="Project ID or name (auto-detects from cwd)")
@click.option("-s", "--status", default="Backlog", help="Initial status")
@click.option("--priority", default=None, help="Priority: Critical, High, Medium, Low")
@click.option("--prompt", default=None, help="Agent prompt (execution instructions for AI)")
@click.option("--category", default=None, help="Task category label (defaults from project portfolio metadata)")
@click.option("-d", "--description", default=None, help="Rich description / acceptance criteria (stored in notes field)")
@click.option("--parent", type=int, default=None, help="Parent task ID (creates subtask)")
@click.option("--blocked-by", default=None, help="Comma-separated task IDs that block this task")
@click.option("--proposal", is_flag=True, help="Create as a proposal (hidden from default listing until approved)")
@click.option("--created-by", "created_by", default=None, help="Origin label (defaults to cwd-derived: 'architect', project name, or 'unknown')")
def tasks_create(text, project, status, priority, prompt, category, description, parent, blocked_by, proposal, created_by):
    """Create a new task.

    Auto-detects project from current directory.
    """
    import json
    db = DatabaseManager()
    if project: project_id = _resolve_project_id(db, project)
    else: project_id = _detect_project_from_cwd(db)
    if not project_id:
        if project: console.print(f"[red]Project '{project}' not found[/red]")
        else: console.print("[red]Could not auto-detect project from current directory. Use -p to specify.[/red]")
        return
    valid_statuses = ["Backlog", "To Do", "In Progress", "Review", "Done", "Cancelled"]
    if status not in valid_statuses:
        console.print(f"[red]Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}[/red]"); return
    if priority and priority not in ["Critical", "High", "Medium", "Low"]:
        console.print(f"[red]Invalid priority '{priority}'. Must be one of: Critical, High, Medium, Low[/red]"); return
    blocked_by_json = None
    if blocked_by:
        try:
            ids = [int(tid.strip()) for tid in blocked_by.split(",")]
            blocked_by_json = json.dumps(ids)
        except ValueError:
            console.print("[red]Error: blocked-by must be comma-separated task IDs (e.g., '4645,4646')[/red]"); return
    WORKFLOW_FOOTER = "\n---\n\n## Workflow Protocol\n- [ ] Start: `./pt tasks start <id>`\n- [ ] Complete work\n- [ ] Report: \"Work complete. Awaiting Conductor sign-off.\"\n- [ ] FORBIDDEN: `./pt tasks done` (Conductor only)"
    try:
        final_prompt = prompt
        if prompt: final_prompt = prompt.rstrip() + WORKFLOW_FOOTER
        task_type = "proposal" if proposal else None
        resolved_created_by = created_by if created_by else _resolve_created_by()
        task = db.add_task(text=text, project_id=project_id, status=status, priority=priority, prompt=final_prompt, task_type=task_type, category=category, parent_id=parent, blocked_by=blocked_by_json, notes=description, created_by=resolved_created_by)
        msg = f"[green]Created {'proposal' if proposal else 'task'} #{task['id']}: {text[:50]}{'...' if len(text) > 50 else ''}[/green]"
        if description: msg += f" [dim](+ description)[/dim]"
        if parent: msg += f" [dim](subtask of #{parent})[/dim]"
        if blocked_by: msg += f" [dim](blocked by {blocked_by})[/dim]"
        console.print(msg)
        _notify_inbox(task["id"], project_id, status, text)
    except BlockedTaskProjectError:
        console.print(
            f"[yellow]Failed to create task: task creation is blocked for '{project_id}'.[/yellow]"
        )
        return
    except Exception as e:
        console.print(f"[red]Failed to create task: {e}[/red]")


@tasks_group.command(name="update")
@click.argument("task_id", type=int)
@click.option("-s", "--status", default=None, help="New status")
@click.option("-t", "--text", default=None, help="New task text")
@click.option("--priority", default=None, help="New priority")
@click.option("--prompt", default=None, help="Agent prompt (execution instructions for AI)")
@click.option("--review-comment", default=None, help="Reviewer feedback")
@click.option("--notes", default=None, help="Internal notes/comments")
@click.option("--blocked-by", default=None, help="Comma-separated task IDs (empty string clears)")
def tasks_update(task_id, status, text, priority, prompt, review_comment, notes, blocked_by):
    """Update an existing task."""
    import json as json_lib
    db = DatabaseManager()
    updates = {}
    if status:
        valid_statuses = ["Backlog", "To Do", "In Progress", "Review", "Done", "Cancelled"]
        if status not in valid_statuses:
            console.print(f"[red]Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}[/red]"); return
        updates["status"] = status
    if text is not None: updates["text"] = text
    if priority:
        if priority not in ["Critical", "High", "Medium", "Low"]:
            console.print(f"[red]Invalid priority '{priority}'[/red]"); return
        updates["priority"] = priority
    if prompt is not None: updates["prompt"] = prompt
    if review_comment is not None: updates["review_comment"] = review_comment
    if notes is not None: updates["notes"] = notes
    if blocked_by is not None:
        if blocked_by == "": updates["blocked_by"] = None
        else:
            try:
                ids = [int(tid.strip()) for tid in blocked_by.split(",")]
                updates["blocked_by"] = json_lib.dumps(ids)
            except ValueError:
                console.print("[red]Error: blocked-by must be comma-separated task IDs[/red]"); return
    if not updates:
        console.print("[yellow]No updates specified. Use -s, -t, --priority, --prompt, --notes, or --blocked-by.[/yellow]"); return
    task_id = _resolve_task_id(db, task_id)
    if not db.get_task(task_id):
        console.print(f"[red]Task #{task_id} not found[/red]"); return
    try:
        db.update_task(task_id, **updates)
        console.print(f"[green]Updated task #{task_id}[/green]")
        for key, value in updates.items():
            console.print(f"  {key}: {value}")
        if "status" in updates:
            task = db.get_task(task_id)
            if task:
                _notify_inbox(task_id, task["project_id"], updates["status"], task["text"])
    except Exception as e:
        console.print(f"[red]Failed to update task #{task_id}: {e}[/red]")


@tasks_group.command(name="move")
@click.argument("project", type=str)
@click.argument("task_ids", type=int, nargs=-1, required=True)
def tasks_move(project, task_ids):
    """Reassign one or more tasks to a different project."""
    db = DatabaseManager()
    target_project_id = _resolve_project_id(db, project)
    if not target_project_id:
        console.print(f"[red]Project '{project}' not found[/red]"); return
    target_project = db.get_project(target_project_id)
    target_name = target_project["name"] if target_project else target_project_id
    success_count = 0
    for task_id in task_ids:
        try:
            task_id = _resolve_task_id(db, task_id)
            task = db.get_task(task_id)
            if not task: print(f"Task #{task_id} not found"); continue
            old_project = task["project_id"]
            if old_project == target_project_id: print(f"Task #{task_id} already in project '{target_name}'"); continue
            db.update_task(task_id, project_id=target_project_id)
            print(f"Moved: #{task_id} from '{old_project}' to '{target_name}'")
            _notify_inbox(task_id, target_project_id, task.get("status", "Backlog"), task["text"])
            success_count += 1
        except Exception as e:
            print(f"Failed to move task #{task_id}: {e}")
    if len(task_ids) > 1: print(f"\nMoved {success_count}/{len(task_ids)} tasks to '{target_name}'")


@tasks_group.command(name="done")
@click.argument("task_ids", type=int, nargs=-1, required=True)
def tasks_done(task_ids):
    """Mark one or more tasks as Done."""
    db = DatabaseManager()
    success_count = 0
    for task_id in task_ids:
        try:
            task_id = _resolve_task_id(db, task_id)
            task = db.get_task(task_id)
            if not task: print(f"Task #{task_id} not found"); continue
            db.update_task(task_id, status="Done")
            print(f"Done: #{task_id} - {task['text'][:50]}")
            _notify_inbox(task_id, task["project_id"], "Done", task["text"])
            success_count += 1
        except Exception as e:
            print(f"Failed to complete task #{task_id}: {e}")
    if len(task_ids) > 1: print(f"\nCompleted {success_count}/{len(task_ids)} tasks")
    if success_count > 0:
        # Trim Done column to keep it manageable
        trimmed = db.trim_done_tasks(keep=75)
        if trimmed > 0:
            print(f"Trimmed {trimmed} oldest Done task(s) (keeping 75 most recent)")
        print("💡 Tip: Run /compound in Claude Code to journal what you learned")


@tasks_group.command(name="start")
@click.argument("task_ids", type=int, nargs=-1, required=True)
def tasks_start(task_ids):
    """Move one or more tasks to In Progress."""
    db = DatabaseManager()
    success_count = 0
    for task_id in task_ids:
        try:
            task_id = _resolve_task_id(db, task_id)
            task = db.get_task(task_id)
            if not task: print(f"Task #{task_id} not found"); continue
            if task.get("task_type") == "agent" and not task.get("prompt"):
                console.print(f"[yellow]Starting agent task #{task_id} without a prompt[/yellow]")
            is_blocked, blocking_ids = db.is_blocked(task_id)
            if is_blocked:
                blocking_str = ", ".join([f"#{bid}" for bid in blocking_ids])
                console.print(f"[red]Cannot start #{task_id} - blocked by: {blocking_str}[/red]")
                continue
            db.update_task(task_id, status="In Progress")
            print(f"Started: #{task_id} - {task['text'][:50]}")
            _notify_inbox(task_id, task["project_id"], "In Progress", task["text"])
            success_count += 1
        except Exception as e:
            print(f"Failed to start task #{task_id}: {e}")
    if len(task_ids) > 1: print(f"\nStarted {success_count}/{len(task_ids)} tasks")


@tasks_group.command(name="review")
@click.argument("task_ids", type=int, nargs=-1, required=True)
def tasks_review(task_ids):
    """Move one or more tasks to Review."""
    db = DatabaseManager()
    success_count = 0
    for task_id in task_ids:
        try:
            task_id = _resolve_task_id(db, task_id)
            task = db.get_task(task_id)
            if not task: print(f"Task #{task_id} not found"); continue
            db.update_task(task_id, status="Review")
            print(f"Review: #{task_id} - {task['text'][:50]}")
            _notify_inbox(task_id, task["project_id"], "Review", task["text"])
            success_count += 1
        except Exception as e:
            print(f"Failed to review task #{task_id}: {e}")
    if len(task_ids) > 1: print(f"\nReviewed {success_count}/{len(task_ids)} tasks")


@tasks_group.command(name="cancel")
@click.argument("task_ids", type=int, nargs=-1, required=True)
def tasks_cancel(task_ids):
    """Cancel one or more tasks (soft delete - keeps history)."""
    db = DatabaseManager()
    success_count = 0
    for task_id in task_ids:
        try:
            task_id = _resolve_task_id(db, task_id)
            task = db.get_task(task_id)
            if not task: print(f"Task #{task_id} not found"); continue
            db.update_task(task_id, status="Cancelled")
            print(f"Cancelled: #{task_id} - {task['text'][:50]}")
            _notify_inbox(task_id, task["project_id"], "Cancelled", task["text"])
            success_count += 1
        except Exception as e:
            print(f"Failed to cancel task #{task_id}: {e}")
    if len(task_ids) > 1: print(f"\nCancelled {success_count}/{len(task_ids)} tasks")


@tasks_group.command(name="approve")
@click.argument("task_ids", type=int, nargs=-1, required=True)
def tasks_approve(task_ids):
    """Approve one or more proposals, converting them to regular backlog tasks."""
    db = DatabaseManager()
    success_count = 0
    for task_id in task_ids:
        try:
            task_id = _resolve_task_id(db, task_id)
            task = db.get_task(task_id)
            if not task:
                print(f"Task #{task_id} not found"); continue
            if task.get("task_type") != "proposal":
                print(f"Task #{task_id} is not a proposal (type: {task.get('task_type', 'unknown')})"); continue
            db.update_task(task_id, task_type="manual")
            print(f"Approved: #{task_id} - {task['text'][:50]}")
            _notify_inbox(task_id, task["project_id"], task["status"], task["text"])
            success_count += 1
        except Exception as e:
            print(f"Failed to approve task #{task_id}: {e}")
    if len(task_ids) > 1:
        print(f"\nApproved {success_count}/{len(task_ids)} proposals")


@tasks_group.command(name="reject")
@click.argument("task_ids", type=int, nargs=-1, required=True)
def tasks_reject(task_ids):
    """Reject one or more proposals (cancels them)."""
    db = DatabaseManager()
    success_count = 0
    for task_id in task_ids:
        try:
            task_id = _resolve_task_id(db, task_id)
            task = db.get_task(task_id)
            if not task:
                print(f"Task #{task_id} not found"); continue
            if task.get("task_type") != "proposal":
                print(f"Task #{task_id} is not a proposal (type: {task.get('task_type', 'unknown')})"); continue
            db.update_task(task_id, status="Cancelled")
            print(f"Rejected: #{task_id} - {task['text'][:50]}")
            _notify_inbox(task_id, task["project_id"], "Cancelled", task["text"])
            success_count += 1
        except Exception as e:
            print(f"Failed to reject task #{task_id}: {e}")
    if len(task_ids) > 1:
        print(f"\nRejected {success_count}/{len(task_ids)} proposals")


@tasks_group.command(name="delete")
@click.argument("task_id", type=int)
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation")
def tasks_delete(task_id, yes):
    """Permanently delete a single task (one at a time for safety)."""
    db = DatabaseManager()
    task_id = _resolve_task_id(db, task_id)
    task = db.get_task(task_id)
    if not task: print(f"Task #{task_id} not found"); return
    print(f"  #{task['id']} | {task['status']} | {task['text'][:60]}")
    if not yes:
        confirm = click.confirm(f"\nPermanently delete task #{task_id}?", default=False)
        if not confirm: print("Cancelled"); return
    try:
        db.delete_task(task_id)
        print(f"Deleted: #{task_id}")
        _notify_inbox(task_id, task.get("project_id", "unknown"), "Deleted", task["text"])
    except Exception as e:
        print(f"Failed to delete task #{task_id}: {e}")


@tasks_group.command(name="show")
@click.argument("task_ids", type=int, nargs=-1, required=True)
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def tasks_show(task_ids, json_output):
    """Show full details of one or more tasks including prompt."""
    db = DatabaseManager()
    tasks = []
    for i, task_id in enumerate(task_ids):
        try:
            task_id = _resolve_task_id(db, task_id)
            task = db.get_task(task_id)
            if not task:
                if not json_output: console.print(f"[red]Task #{task_id} not found[/red]")
                continue
            display_id = db.get_task_display_id(task_id) or task_id
            if json_output:
                tasks.append(task)
            else:
                if i > 0: print("\n" + "-" * 40 + "\n")
                print(f"Task #{display_id} (pk: {task['id']})")
                print(f"Project: {task['project_id']}")
                print(f"Status: {task['status']}")
                print(f"Priority: {task.get('priority') or 'None'}")
                is_blocked, blocking_ids = db.is_blocked(task['id'])
                if is_blocked: print(f"Blocked by: {', '.join(f'#{tid}' for tid in blocking_ids)} (incomplete)")
                elif task.get('blocked_by'): print(f"Blocked by: (all resolved)")
                print(f"Created: {task['created_at']}")
                if task.get('created_by'): print(f"Created by: {task['created_by']}")
                print(f"Updated: {task['updated_at']}")
                if task.get('completed_at'): print(f"Completed: {task['completed_at']}")
                print()
                print("Description:")
                print(task['text'])
                if task.get('notes'): print(); print("Notes:"); print(task['notes'])
                if task.get('prompt'): print(); print("Agent Prompt:"); print(task['prompt'])
                if task.get('review_comment'): print(); print("Review Comment:"); print(task['review_comment'])
        except Exception as e:
            if not json_output: console.print(f"[red]Failed to get task #{task_id}: {e}[/red]")
    if json_output:
        import json as json_lib
        if len(tasks) == 1: print(json_lib.dumps(tasks[0], indent=2))
        else: print(json_lib.dumps(tasks, indent=2))


@tasks_group.command(name="prompt-validate")
@click.argument("task_id", type=int)
def tasks_prompt_validate(task_id):
    """Check task prompt for required sections."""
    db = DatabaseManager()
    task = db.get_task(task_id)
    if not task: print(f"Task #{task_id} not found"); sys.exit(1)
    prompt = (task.get("prompt") or "").strip()
    prompt_lower = prompt.lower()
    has_overview = "## overview" in prompt_lower
    has_execution = "## execution" in prompt_lower
    has_done = "## done criteria" in prompt_lower or "## acceptance criteria" in prompt_lower
    print(f"Task #{task_id} prompt validation:")
    print(f"{'✓' if has_overview else '✗'} Overview section {'found' if has_overview else 'MISSING'}")
    print(f"{'✓' if has_execution else '✗'} Execution section {'found' if has_execution else 'MISSING'}")
    print(f"{'✓' if has_done else '✗'} Done Criteria section {'found' if has_done else 'MISSING'}")
    missing = sum([not has_overview, not has_execution, not has_done])
    if missing: print(f"\nStatus: INCOMPLETE ({missing} section{'s' if missing != 1 else ''} missing)"); sys.exit(1)
    print("\nStatus: COMPLETE"); sys.exit(0)


@tasks_group.command(name="next")
@click.option("-p", "--project", default=None, help="Filter by project (auto-detects from cwd)")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def tasks_next(project, json_output):
    """Get the next task to work on (highest priority, In Progress first)."""
    db = DatabaseManager()
    if project:
        project_id = _resolve_project_id(db, project)
        if not project_id: print(f"Project '{project}' not found"); sys.exit(1)
    else:
        project_id = _detect_project_from_cwd(db)
    all_tasks = db.get_tasks(project_id=project_id)
    actionable = [t for t in all_tasks if t["status"] in ("In Progress", "To Do")]
    if not actionable: print("No tasks available"); sys.exit(1)
    priority_rank = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, None: 4}
    status_rank = {"In Progress": 0, "To Do": 1}
    actionable.sort(key=lambda t: (status_rank.get(t["status"], 99), priority_rank.get(t.get("priority"), 4)))
    task = actionable[0]
    if json_output:
        import json as json_lib
        print(json_lib.dumps(task, indent=2))
    else:
        priority = task.get("priority") or "-"
        print(f"#{task['id']} | {task['project_id']} | {task['status']} | {priority} | {task['text']}")
    sys.exit(0)


@tasks_group.command(name="tree")
@click.argument("task_id", type=int)
def tasks_tree(task_id):
    """Show dependency tree for a parent task."""
    db = DatabaseManager()
    task = db.get_task(task_id)
    if not task: console.print(f"[red]Task #{task_id} not found[/red]"); return
    subtasks = db.get_subtasks(task_id)
    if not subtasks: console.print(f"Task #{task_id} has no subtasks"); return
    progress = db.get_subtask_progress(task_id)
    print(f"\nExecution Tree for #{task_id}: {task['text']}\n")
    print(f"Progress: {progress['done']}/{progress['total']} complete ({progress['percent']}%)\n")
    status_emoji = {"Done": "✅", "In Progress": "●", "To Do": "○", "Backlog": "○"}
    for i, subtask in enumerate(subtasks):
        is_last = (i == len(subtasks) - 1)
        prefix = "└─" if is_last else "├─"
        emoji = status_emoji.get(subtask["status"], "?")
        is_blocked, blocking_ids = db.is_blocked(subtask["id"])
        block_str = ""
        if is_blocked: block_str = f" 🔒 (blocked by {', '.join([f'#{bid}' for bid in blocking_ids])})"
        elif subtask["status"] not in ["Done", "In Progress"]: block_str = " ← READY NOW"
        print(f"{prefix} {emoji} #{subtask['id']} | {subtask['status']:12} | {subtask['text']}{block_str}")
    print("\nUse 'pt tasks next' to see what you can start immediately\n")


@tasks_group.command(name="export")
@click.option("-o", "--output", default="data/tasks_export.json", help="Output file path")
def tasks_export(output):
    """Export all tasks to JSON file for backup."""
    import json as json_lib
    from datetime import datetime, timezone
    db = DatabaseManager()
    all_tasks = db.get_tasks()
    export_data = {"exported_at": datetime.now(timezone.utc).isoformat(), "total_count": len(all_tasks), "tasks": all_tasks}
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(output_path, 'w') as f:
            json_lib.dump(export_data, f, indent=2)
        console.print(f"[green]✅ Exported {len(all_tasks)} tasks to {output}[/green]")
    except Exception as e:
        console.print(f"[red]Failed to export tasks: {e}[/red]")


@tasks_group.command(name="import")
@click.argument("file", type=click.Path(exists=True))
def tasks_import(file):
    """Import tasks from JSON backup."""
    import json as json_lib
    db = DatabaseManager()
    try:
        with open(file, 'r') as f:
            data = json_lib.load(f)
        tasks = data.get("tasks", [])
        if not tasks: console.print("[yellow]No tasks found in import file[/yellow]"); return
        console.print(f"Importing {len(tasks)} tasks...")
        success_count = db.raw_import_tasks(tasks)
        console.print(f"[green]✅ Successfully imported {success_count}/{len(tasks)} tasks[/green]")
    except Exception as e:
        console.print(f"[red]Failed to import tasks: {e}[/red]")


@tasks_group.command(name="clear-done")
@click.option("-p", "--project", default=None, help="Filter by project")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation")
def tasks_clear_done(project, yes):
    """Delete all tasks in Done status."""
    db = DatabaseManager()
    project_id = _resolve_project_id(db, project) if project else None
    if project and not project_id:
        console.print(f"[red]Project '{project}' not found[/red]"); return
    done_tasks = db.get_tasks(project_id=project_id, status="Done")
    count = len(done_tasks)
    if count == 0: console.print("[dim]No Done tasks to delete[/dim]"); return
    if not yes:
        scope_label = f"project {project}" if project else "all projects"
        console.print(f"[dim]Scope: {scope_label}[/dim]")
        confirm = click.confirm(f"Delete {count} Done task(s)?", default=False)
        if not confirm: console.print("[dim]Cancelled[/dim]"); return
    try:
        # Capture task info before deletion for notifications
        for t in done_tasks:
            _notify_inbox(t["id"], t.get("project_id", "unknown"), "Deleted", t["text"])
        deleted_count = db.delete_done_tasks(project_id=project_id)
        console.print(f"[green]Deleted {deleted_count} Done task(s)[/green]")
    except Exception as e:
        console.print(f"[red]Failed to delete tasks: {e}[/red]")


# =============================================================================
# Inbox group
# =============================================================================

INBOX_FILE = Path(__file__).parent.parent / "data" / "inbox.json"

def _load_inbox():
    if not INBOX_FILE.exists(): return {"notes": [], "next_id": 1}
    import json
    with open(INBOX_FILE, "r") as f: return json.load(f)

def _save_inbox(data):
    import json
    INBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(INBOX_FILE, "w") as f: json.dump(data, f, indent=2)


@click.group(name="inbox", invoke_without_command=True)
@click.pass_context
def inbox_group(ctx):
    """Quick capture notes not attached to any project."""
    if ctx.invoked_subcommand is not None: return
    ctx.invoke(inbox_list, as_json=False)


@inbox_group.command(name="list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def inbox_list(as_json):
    """List all inbox notes."""
    import json as json_mod
    data = _load_inbox()
    notes = data.get("notes", [])
    if as_json:
        print(json_mod.dumps(notes, indent=2, default=str)); return
    if not notes: print("Inbox is empty"); return
    print(f"Inbox ({len(notes)} notes)\n")
    for note in notes:
        print(f"  #{note['id']} {note['text']}")


@inbox_group.command(name="add")
@click.argument("text")
def inbox_add(text):
    """Add a note to the inbox."""
    from datetime import datetime, timezone
    data = _load_inbox()
    note_id = data.get("next_id", 1)
    note = {"id": note_id, "text": text, "created_at": datetime.now(timezone.utc).isoformat()}
    data["notes"].append(note)
    data["next_id"] = note_id + 1
    _save_inbox(data)
    console.print(f"[green]Added note #{note_id}:[/green] {text}")


@inbox_group.command(name="remove")
@click.argument("note_id", type=int)
def inbox_remove(note_id):
    """Remove a note by ID."""
    data = _load_inbox()
    original_count = len(data["notes"])
    data["notes"] = [n for n in data["notes"] if n["id"] != note_id]
    if len(data["notes"]) == original_count:
        console.print(f"[red]Note #{note_id} not found[/red]"); return
    _save_inbox(data)
    console.print(f"[green]Removed note #{note_id}[/green]")


@inbox_group.command(name="clear")
@click.confirmation_option(prompt="Clear all inbox notes?")
def inbox_clear():
    """Clear all inbox notes."""
    _save_inbox({"notes": [], "next_id": 1})
    console.print("[green]Inbox cleared[/green]")


# =============================================================================
# Calendar group
# =============================================================================

def _get_calendar_manager():
    from db.calendar_manager import CalendarManager
    cm = CalendarManager()
    cm.ensure_tables()
    return cm


def _display_events(events, json_output=False, cron_jobs=None):
    import json as json_lib
    if json_output:
        out = {"events": events, "total": len(events)}
        if cron_jobs is not None:
            out["cron_jobs"] = cron_jobs
        print(json_lib.dumps(out, indent=2))
        return
    if not events and not cron_jobs:
        print("No events found.")
        return
    if events:
        for ev in events:
            time_str = f" {ev['event_time']}" if ev.get("event_time") else ""
            project_str = f" | {ev['project_id']}" if ev.get("project_id") else ""
            prompt_marker = " [prompt]" if ev.get("prompt") else ""
            print(f"#{ev['id']} | {ev['event_date']}{time_str} | {ev['event_type']} | {ev['status']}{project_str}{prompt_marker} | {ev['title']}")
        print(f"\nEvents: {len(events)}")
    if cron_jobs:
        print(f"\n── Cron Jobs ──")
        for cj in cron_jobs:
            desc_str = f" | {cj['description']}" if cj.get("description") else ""
            print(f"  cron/{cj['id']} | {cj['schedule']} | {cj['project_id']}{desc_str} | {cj['command']}")
        print(f"\nCron jobs: {len(cron_jobs)}")


@click.group(name="calendar", invoke_without_command=True)
@click.pass_context
@click.option("--days", default=7, type=int, help="Days ahead to show (default: 7)")
@click.option("-p", "--project", default=None, help="Filter by project")
@click.option("-t", "--type", "event_type", default=None, help="Filter by type: reminder, deadline, milestone, meeting")
@click.option("--all", "show_all", is_flag=True, help="Show all events (no date window)")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def calendar_group(ctx, days, project, event_type, show_all, json_output):
    """Manage the AI-first calendar.

    \b
    Examples:
        ./pt calendar                        # Upcoming 7 days
        ./pt calendar --days 30              # Next 30 days
        ./pt calendar -p ai-memory-replay    # Filter by project
        ./pt calendar add "Sprint review" --date 2026-03-28
        ./pt calendar show 1
        ./pt calendar remind --json          # For cron agent polling
    """
    if ctx.invoked_subcommand is not None:
        return
    db = DatabaseManager()
    project_id = _resolve_project_id(db, project) if project else None
    cm = _get_calendar_manager()
    events = cm.get_events(
        days=days,
        project_id=project_id,
        event_type=event_type,
        include_all=show_all,
    )
    cron_jobs = cm.get_cron_jobs(project_id=project_id)
    _display_events(events, json_output=json_output, cron_jobs=cron_jobs)


@calendar_group.command(name="list")
@click.option("--days", default=7, type=int, help="Days ahead to show (default: 7)")
@click.option("-p", "--project", default=None, help="Filter by project")
@click.option("-t", "--type", "event_type", default=None, help="Filter by event type")
@click.option("--all", "show_all", is_flag=True, help="Show all events ignoring date window")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def calendar_list(days, project, event_type, show_all, json_output):
    """List upcoming calendar events and active cron jobs."""
    db = DatabaseManager()
    project_id = _resolve_project_id(db, project) if project else None
    cm = _get_calendar_manager()
    events = cm.get_events(
        days=days, project_id=project_id,
        event_type=event_type, include_all=show_all,
    )
    cron_jobs = cm.get_cron_jobs(project_id=project_id)
    _display_events(events, json_output=json_output, cron_jobs=cron_jobs)


@calendar_group.command(name="crons")
@click.option("-p", "--project", default=None, help="Filter by project")
@click.option("--all", "show_all", is_flag=True, help="Include inactive cron jobs")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def calendar_crons(project, show_all, json_output):
    """List all cron jobs.

    \b
    Examples:
        ./pt calendar crons
        ./pt calendar crons -p project-tracker --json
    """
    import json as json_lib
    db = DatabaseManager()
    project_id = _resolve_project_id(db, project) if project else None
    cm = _get_calendar_manager()
    cron_jobs = cm.get_cron_jobs(
        project_id=project_id, active_only=not show_all
    )
    if json_output:
        print(json_lib.dumps({"cron_jobs": cron_jobs, "total": len(cron_jobs)}, indent=2))
        return
    if not cron_jobs:
        print("No cron jobs found.")
        return
    print("Cron Jobs\n")
    for cj in cron_jobs:
        desc_str = f" | {cj['description']}" if cj.get("description") else ""
        active_str = "" if cj.get("is_active", 1) else " [inactive]"
        print(f"  cron/{cj['id']} | {cj['schedule']} | {cj['project_id']}{desc_str}{active_str}")
        print(f"    {cj['command']}")
    print(f"\nTotal: {len(cron_jobs)} cron job(s)")


@calendar_group.command(name="add-cron")
@click.argument("project")
@click.argument("schedule")
@click.argument("command")
@click.option("--description", default="", help="What this cron job does")
def calendar_add_cron(project, schedule, command, description):
    """Add a cron job from the calendar.

    \b
    Examples:
        ./pt calendar add-cron project-tracker "*/15 * * * *" "./pt calendar remind --json" \\
            --description "Agent reminder poller"
        ./pt calendar add-cron ai-memory-replay "0 9 * * 1" "bash scripts/render_replay.sh" \\
            --description "Weekly brain replay render"
    """
    db = DatabaseManager()
    project_id = _resolve_project_id(db, project)
    if not project_id:
        console.print(f"[red]Project '{project}' not found[/red]"); return

    cm = _get_calendar_manager()
    new_id = cm.add_cron_job(project_id, schedule, command, description or None)

    console.print(f"[green]✅ Added cron job #{new_id} to {project}[/green]")
    console.print(f"   Schedule: {schedule}")
    console.print(f"   Command:  {command}")


@calendar_group.command(name="add")
@click.argument("title")
@click.option("--date", "event_date", required=True, help="Date: YYYY-MM-DD")
@click.option("--time", "event_time", default=None, help="Time: HH:MM (optional)")
@click.option("-t", "--type", "event_type", default="reminder",
              type=click.Choice(["reminder", "deadline", "milestone", "meeting", "recurring"]),
              help="Event type (default: reminder)")
@click.option("-p", "--project", default=None, help="Project name or ID")
@click.option("--prompt", default=None, help="Agent instructions when event fires")
@click.option("--description", default=None, help="Human-readable description")
@click.option("--notify", "notify_before_minutes", default=60, type=int,
              help="Minutes before to notify (default: 60)")
@click.option("--recurrence", default=None,
              type=click.Choice(["daily", "weekly", "monthly"]),
              help="Recurrence pattern")
@click.option("--json", "json_output", is_flag=True, help="Output new event as JSON")
def calendar_add(title, event_date, event_time, event_type, project,
                 prompt, description, notify_before_minutes, recurrence, json_output):
    """Add a calendar event.

    \b
    Examples:
        ./pt calendar add "Ship v2" --date 2026-03-28 --type milestone
        ./pt calendar add "Weekly review" --date 2026-03-25 --time 10:00 --recurrence weekly
        ./pt calendar add "Check cards" --date 2026-03-24 --prompt "Review all In Progress cards"
    """
    import json as json_lib
    db = DatabaseManager()
    project_id = _resolve_project_id(db, project) if project else None
    if project and not project_id:
        console.print(f"[red]Project '{project}' not found[/red]"); return

    cm = _get_calendar_manager()
    try:
        event_id = cm.add_event(
            title=title,
            event_date=event_date,
            event_time=event_time,
            event_type=event_type,
            project_id=project_id,
            prompt=prompt,
            description=description,
            notify_before_minutes=notify_before_minutes,
            recurrence=recurrence,
            created_by="human",
        )
        if json_output:
            print(json_lib.dumps({"id": event_id, "title": title, "event_date": event_date}))
        else:
            console.print(f"[green]✅ Created event #{event_id}: {title} on {event_date}[/green]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")


@calendar_group.command(name="show")
@click.argument("event_id", type=int)
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def calendar_show(event_id, json_output):
    """Show full details of a calendar event."""
    import json as json_lib
    cm = _get_calendar_manager()
    event = cm.get_event(event_id)
    if not event:
        console.print(f"[red]Event #{event_id} not found[/red]"); return
    if json_output:
        print(json_lib.dumps(event, indent=2)); return

    console.print(f"\n[bold cyan]#{event['id']} — {event['title']}[/bold cyan]")
    console.print(f"Date:    {event['event_date']}" + (f" {event['event_time']}" if event.get("event_time") else ""))
    console.print(f"Type:    {event['event_type']}")
    console.print(f"Status:  {event['status']}")
    if event.get("project_id"):    console.print(f"Project: {event['project_id']}")
    if event.get("recurrence"):    console.print(f"Recurs:  {event['recurrence']}")
    if event.get("description"):   console.print(f"\n{event['description']}")
    if event.get("prompt"):        console.print(f"\n[dim]Agent prompt:[/dim]\n{event['prompt']}")

    linked = event.get("linked_tasks", [])
    if linked:
        console.print(f"\n[bold]Linked tasks:[/bold]")
        for t in linked:
            console.print(f"  #{t['id']} [{t['status']}] {t['text']} ({t['link_type']})")
    console.print()


@calendar_group.command(name="link")
@click.argument("event_id", type=int)
@click.argument("task_id", type=int)
@click.option("--type", "link_type", default="related",
              type=click.Choice(["related", "deadline-for", "blocks"]),
              help="Link type (default: related)")
def calendar_link(event_id, task_id, link_type):
    """Link a task to a calendar event."""
    cm = _get_calendar_manager()
    if not cm.get_event(event_id):
        console.print(f"[red]Event #{event_id} not found[/red]"); return
    cm.link_task(event_id, task_id, link_type)
    console.print(f"[green]Linked task #{task_id} to event #{event_id} ({link_type})[/green]")


@calendar_group.command(name="unlink")
@click.argument("event_id", type=int)
@click.argument("task_id", type=int)
def calendar_unlink(event_id, task_id):
    """Remove a task-event link."""
    cm = _get_calendar_manager()
    cm.unlink_task(event_id, task_id)
    console.print(f"[green]Unlinked task #{task_id} from event #{event_id}[/green]")


@calendar_group.command(name="done")
@click.argument("event_id", type=int)
def calendar_done(event_id):
    """Mark an event as done."""
    cm = _get_calendar_manager()
    if cm.mark_done(event_id):
        console.print(f"[green]✅ Event #{event_id} marked as done[/green]")
    else:
        console.print(f"[red]Event #{event_id} not found[/red]")


@calendar_group.command(name="cancel")
@click.argument("event_id", type=int)
def calendar_cancel(event_id):
    """Cancel an event."""
    cm = _get_calendar_manager()
    if cm.cancel_event(event_id):
        console.print(f"[yellow]Event #{event_id} cancelled[/yellow]")
    else:
        console.print(f"[red]Event #{event_id} not found[/red]")


@calendar_group.command(name="update")
@click.argument("event_id", type=int)
@click.option("--title", default=None)
@click.option("--date", "event_date", default=None)
@click.option("--time", "event_time", default=None)
@click.option("-t", "--type", "event_type", default=None)
@click.option("-p", "--project", default=None)
@click.option("--prompt", default=None)
@click.option("--description", default=None)
@click.option("--notify", "notify_before_minutes", default=None, type=int)
def calendar_update(event_id, title, event_date, event_time, event_type, project,
                    prompt, description, notify_before_minutes):
    """Update any fields on a calendar event."""
    db = DatabaseManager()
    cm = _get_calendar_manager()
    updates = {}
    if title is not None:                 updates["title"] = title
    if event_date is not None:            updates["event_date"] = event_date
    if event_time is not None:            updates["event_time"] = event_time
    if event_type is not None:            updates["event_type"] = event_type
    if prompt is not None:                updates["prompt"] = prompt
    if description is not None:           updates["description"] = description
    if notify_before_minutes is not None: updates["notify_before_minutes"] = notify_before_minutes
    if project is not None:
        pid = _resolve_project_id(db, project)
        if not pid:
            console.print(f"[red]Project '{project}' not found[/red]"); return
        updates["project_id"] = pid

    if not updates:
        console.print("[yellow]No updates provided[/yellow]"); return
    try:
        if cm.update_event(event_id, **updates):
            console.print(f"[green]Updated event #{event_id}[/green]")
        else:
            console.print(f"[red]Event #{event_id} not found[/red]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")


@calendar_group.command(name="remind")
@click.option("--within", "within_minutes", default=60, type=int,
              help="Alert window in minutes (default: 60)")
@click.option("--dry-run", is_flag=True, help="Print what would fire without marking as notified")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON (for cron/agent polling)")
def calendar_remind(within_minutes, dry_run, json_output):
    """Show events firing soon — designed for cron/agent polling.

    \b
    Run every 15 min:
        */15 * * * * cd ~/projects/project-tracker && \\
          doppler run -- ./pt calendar remind --json
    """
    import json as json_lib
    cm = _get_calendar_manager()
    events = cm.get_upcoming_reminders(within_minutes=within_minutes)
    if json_output:
        print(json_lib.dumps({"events": events, "total": len(events), "within_minutes": within_minutes}, indent=2))
    else:
        if not events:
            print(f"No events firing in next {within_minutes} minutes.")
        else:
            print(f"🔔 {len(events)} event(s) firing soon:\n")
            _display_events(events)
    if not dry_run:
        for ev in events:
            cm.mark_notified(ev["id"])


@calendar_group.command(name="export")
@click.option("-o", "--output", default=None, help="Output file path (default: stdout)")
@click.option("-p", "--project", default=None, help="Filter by project")
@click.option("--json", "as_json", is_flag=True, help="Export as JSON")
def calendar_export(output, project, as_json):
    """Export calendar events as iCal (.ics) format.

    \b
    Examples:
        pt calendar export -o ~/Desktop/pt-calendar.ics
        pt calendar export --json
    """
    db = DatabaseManager()
    project_id = _resolve_project_id(db, project) if project else None
    cm = _get_calendar_manager()

    if as_json:
        import json as json_mod
        events = cm.get_events(project_id=project_id, include_all=True)
        content = json_mod.dumps(events, indent=2, default=str)
    else:
        content = cm.export_ical(project_id=project_id, include_all=True)

    if output:
        Path(output).write_text(content)
        console.print(f"[green]Exported to {output}[/green]")
    else:
        print(content)




@calendar_group.command(name="poll")
@click.option("--within", "within_minutes", default=60, type=int,
              help="Notify events firing within this many minutes (default: 60)")
@click.option("--dry-run", is_flag=True, help="Show what would fire without marking as notified or writing to brain")
@click.option("--quiet", is_flag=True, help="Suppress human-readable output")
@click.option("--json", "as_json", is_flag=True, help="Output results as JSON")
def calendar_poll(within_minutes, dry_run, quiet, as_json):
    """Run one calendar poll cycle — fire events, write to brain, run agent prompts.

    \b
    Designed to be run every 5-15 minutes via cron. Use install-poll-cron to
    set that up automatically.

    \b
    Examples:
        ./pt calendar poll                          # 60 min window
        ./pt calendar poll --within 15 --dry-run    # preview without side effects
        ./pt calendar poll --json                   # structured output for agents
    """
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.hooks.calendar_poller import poll as _poll
    results = _poll(
        within_minutes=within_minutes,
        dry_run=dry_run,
        quiet=quiet,
        as_json=as_json,
    )
    if results.get("errors"):
        raise SystemExit(1)


@calendar_group.command(name="install-poll-cron")
@click.option("--interval", default=10, type=int, help="Run every N minutes (default: 10)")
@click.option("--within", "within_minutes", default=60, type=int,
              help="Notify events firing within N minutes (default: 60)")
@click.option("--remove", is_flag=True, help="Remove the poller cron job instead of installing")
@click.option("--dry-run", is_flag=True, help="Print the crontab line without installing it")
def calendar_install_poll_cron(interval, within_minutes, remove, dry_run):
    """Install (or remove) the calendar_poller cron job in the current user's crontab.

    \b
    Installs a sentinel-tagged crontab line that runs the calendar poller every
    N minutes using uv run. Output appended to data/logs/poller.log.

    \b
    Examples:
        ./pt calendar install-poll-cron                          # every 10 min
        ./pt calendar install-poll-cron --interval 5 --within 15
        ./pt calendar install-poll-cron --remove                 # uninstall
        ./pt calendar install-poll-cron --dry-run                # preview
    """
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.hooks.cron_installer import install as _install

    result = _install(
        interval=interval,
        within=within_minutes,
        dry_run=dry_run,
        remove=remove,
    )

    if remove:
        removed = result["previous_lines_removed"]
        if dry_run:
            console.print(f"[yellow]Dry run - would remove {removed} line(s)[/yellow]")
        else:
            console.print(f"[green]Removed {removed} poller line(s) from crontab[/green]")
        return

    if dry_run:
        console.print("[yellow]Dry run - crontab line would be:[/yellow]")
        console.print(f"  [blue]{result['line']}[/blue]")
        return

    console.print(f"[green]Calendar poller installed[/green]")
    console.print(f"   Interval : every {result['interval_minutes']} min")
    console.print(f"   Window   : {result['within_minutes']} min lookahead")
    console.print(f"   Log      : {result['log_path']}")
    if result["previous_lines_removed"]:
        console.print(f"   Replaced : {result['previous_lines_removed']} old poller line(s)")
    console.print(f"\n   Crontab entry:")
    console.print(f"   [dim]{result['line']}[/dim]")

# =============================================================================
# Memory group — wraps ai-memory/brain.py for cross-agent semantic memory
# =============================================================================

BRAIN_PY_PATH = PROJECTS_BASE_DIR / "ai-memory" / "brain.py"
AI_MEMORY_DB_PATH = PROJECTS_BASE_DIR / "ai-memory" / "brain.db"


class PtJsonError(Exception):
    """Structured CLI error for JSON automation surfaces."""

    def __init__(self, error_class: str, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.error_class = error_class
        self.message = message
        self.exit_code = exit_code


def _json_dumps(payload: dict) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _emit_json(payload: dict) -> None:
    click.echo(_json_dumps(payload))


def _emit_json_error(error: PtJsonError, command: str, *, err: bool = False) -> NoReturn:
    """Emit a structured JSON error and exit. Never returns.

    `err=True` routes the JSON to stderr instead of stdout — required for
    NDJSON streams (e.g. `memory export`) so a mid-stream error doesn't
    pollute the data channel.
    """
    payload = {
        "schema_version": PT_JSON_SCHEMA_VERSION,
        "ok": False,
        "command": command,
        "error": {
            "class": error.error_class,
            "message": error.message,
        },
    }
    click.echo(_json_dumps(payload), err=err)
    raise SystemExit(error.exit_code)


def _parse_since_until(value: str | None, option_name: str) -> str | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    import re
    from datetime import timedelta, timezone

    match = re.fullmatch(r"(\d+)([dhw])", raw)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        delta = {
            "d": timedelta(days=amount),
            "h": timedelta(hours=amount),
            "w": timedelta(weeks=amount),
        }[unit]
        return (datetime.now(timezone.utc) - delta).strftime("%Y-%m-%d %H:%M:%S")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PtJsonError(
            "validation",
            f"{option_name} must be ISO datetime/date or relative duration like 7d, 12h, 2w",
            EXIT_VALIDATION,
        ) from exc
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def _memory_db_path() -> Path:
    return Path(os.environ.get("PT_MEMORY_DB_PATH", AI_MEMORY_DB_PATH)).expanduser()


def _open_memory_db_readonly() -> sqlite3.Connection:
    db_path = _memory_db_path()
    if not db_path.exists():
        raise PtJsonError(
            "backend_unavailable",
            f"memory database not found at {db_path}",
            EXIT_BACKEND_UNAVAILABLE,
        )
    try:
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON")
        return conn
    except sqlite3.Error as exc:
        raise PtJsonError(
            "backend_unavailable",
            f"could not open memory database read-only: {exc}",
            EXIT_BACKEND_UNAVAILABLE,
        ) from exc


def _metadata_dict(row: sqlite3.Row) -> dict:
    raw = row["metadata"]
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _memory_row_to_dict(row: sqlite3.Row) -> dict:
    metadata = _metadata_dict(row)
    return {
        "id": row["id"],
        "uuid": row["uuid"],
        "content": row["content"],
        "created_at": row["created_at"],
        "source_machine": row["source_machine"] or "",
        "scope": row["scope"] or "",
        "agent_family": row["agent_family"] or metadata.get("agent_family", ""),
        "source_agent": metadata.get("source_agent", ""),
        "project": metadata.get("project", ""),
        "type": metadata.get("type", "observation"),
        "content_type": metadata.get("content_type", ""),
        "metadata": metadata,
    }


def _memory_where_clauses(
    since: str | None,
    until: str | None,
    source: str | None,
    project: str | None,
    query: str | None = None,
) -> tuple[list[str], list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if query:
        clauses.append("(content LIKE ? OR metadata LIKE ?)")
        like = f"%{query}%"
        params.extend([like, like])
    if since:
        clauses.append("created_at >= ?")
        params.append(since)
    if until:
        clauses.append("created_at <= ?")
        params.append(until)
    if source:
        clauses.append("(source_machine = ? OR json_extract(metadata, '$.source_agent') = ?)")
        params.extend([source, source])
    if project:
        clauses.append("json_extract(metadata, '$.project') = ?")
        params.append(project)
    return clauses, params


def _memory_query_rows(
    *,
    query: str | None = None,
    since: str | None = None,
    until: str | None = None,
    source: str | None = None,
    project: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int, str]:
    if limit < 1 or limit > 500:
        raise PtJsonError("validation", "--limit must be between 1 and 500", EXIT_VALIDATION)
    if offset < 0:
        raise PtJsonError("validation", "--offset must be >= 0", EXIT_VALIDATION)
    since_sql = _parse_since_until(since, "--since")
    until_sql = _parse_since_until(until, "--until")
    clauses, params = _memory_where_clauses(since_sql, until_sql, source, project, query)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = (
        "SELECT id, uuid, content, metadata, scope, agent_family, created_at, source_machine "
        f"FROM thoughts {where_sql} "
        "ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?"
    )
    count_sql = f"SELECT COUNT(*) FROM thoughts {where_sql}"
    try:
        with _open_memory_db_readonly() as conn:
            total = int(conn.execute(count_sql, params).fetchone()[0])
            rows = conn.execute(sql, [*params, limit, offset]).fetchall()
    except PtJsonError:
        raise
    except sqlite3.Error as exc:
        raise PtJsonError("query_failure", f"memory query failed: {exc}", EXIT_QUERY_FAILURE) from exc
    return [_memory_row_to_dict(row) for row in rows], total, _memory_db_path().as_posix()


def _memory_payload(command: str, rows: list[dict], total: int, db_path: str,
                    limit: int, offset: int, filters: dict) -> dict:
    return {
        "schema_version": PT_MEMORY_SCHEMA_VERSION,
        "ok": True,
        "command": command,
        "read_only": True,
        "backend": {
            "type": "sqlite",
            "path": db_path,
        },
        "filters": filters,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "returned": len(rows),
            "total": total,
        },
        "results": rows,
    }


def _run_brain(*args: str) -> None:
    """Call brain.py via doppler + uv run, ensuring Turso credentials are available.

    Uses ``doppler run --project ai-memory --config dev`` so that
    TURSO_BRAIN_URL / TURSO_BRAIN_TOKEN are always injected.
    """
    if not BRAIN_PY_PATH.exists():
        raise click.ClickException(
            f"brain.py not found at {BRAIN_PY_PATH}. "
            "Is PROJECTS_ROOT set correctly and is ai-memory cloned?"
        )
    if not shutil.which("doppler"):
        raise click.ClickException("doppler CLI not found. Install with: brew install doppler")
    uv_cmd = ["uv", "run", str(BRAIN_PY_PATH), *args]
    cmd = [
        "doppler", "run",
        "--project", "ai-memory",
        "--config", "dev",
        "--",
        *uv_cmd,
    ]
    subprocess.run(cmd, check=False, cwd=str(BRAIN_PY_PATH.parent))


@click.group(name="memory", invoke_without_command=True)
@click.pass_context
def memory_group(ctx: click.Context) -> None:
    """Search and write to the shared agent brain (Open Brain).

    A thin wrapper around ai-memory/brain.py so every agent can access
    cross-agent memory without knowing the full path or needing MCP approval.

    \b
    Quick start:
      pt memory search "what did we decide about Turso?"
      pt memory write "Decision: use Haiku for routine tasks" --type decision
      pt memory stats
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@memory_group.command(name="search")
@click.argument("query_arg", required=False)
@click.option("--query", "query_opt", default=None, help="Search text for JSON/non-interactive mode")
@click.option("--top", "-n", default=5, type=int, help="Number of results (default: 5)")
@click.option("--agent-family", "-a", default="",
              help="Filter to agent family: claude | gemini | codex | antigravity | qwen")
@click.option("--namespace", default="", help="Filter by project prefix (e.g. loop/sales)")
@click.option("--goal-id", default="", help="Filter to loop_state entries for a specific goal ID")
@click.option("--since", default=None, help="Only include rows at/after ISO time or duration like 7d")
@click.option("--until", default=None, help="Only include rows at/before ISO time or duration like 7d")
@click.option("--source", default=None, help="Filter by source_machine or metadata.source_agent")
@click.option("--project", default=None, help="Filter by metadata.project")
@click.option("--limit", default=None, type=int, help="Maximum rows for JSON/non-interactive mode")
@click.option("--offset", default=0, type=int, help="Pagination offset for JSON/non-interactive mode")
@click.option("--json", "json_output", is_flag=True, help="Output stable machine-readable JSON")
def memory_search(query_arg: str | None, query_opt: str | None, top: int, agent_family: str,
                  namespace: str, goal_id: str, since: str | None, until: str | None,
                  source: str | None, project: str | None, limit: int | None,
                  offset: int, json_output: bool) -> None:
    """Search the shared brain by semantic similarity.

    \b
    Examples:
      pt memory search "what was the Turso decision?"
      pt memory search "MCP firewall" --top 10
      pt memory search "calendar" --agent-family claude
    """
    query = query_opt or query_arg
    if not query:
        if json_output:
            _emit_json_error(
                PtJsonError("validation", "memory search requires QUERY or --query", EXIT_VALIDATION),
                "memory.search",
            )
        raise click.UsageError("memory search requires QUERY or --query")
    effective_limit = limit if limit is not None else top
    direct_mode = json_output or any([since, until, source, project, limit is not None, offset])
    if direct_mode:
        try:
            rows, total, db_path = _memory_query_rows(
                query=query,
                since=since,
                until=until,
                source=source,
                project=project,
                limit=effective_limit,
                offset=offset,
            )
        except PtJsonError as exc:
            if json_output:
                _emit_json_error(exc, "memory.search")
            raise click.ClickException(exc.message) from exc
        payload = _memory_payload(
            "memory.search",
            rows,
            total,
            db_path,
            effective_limit,
            offset,
            {
                "query": query,
                "since": since,
                "until": until,
                "source": source,
                "project": project,
            },
        )
        if json_output:
            _emit_json(payload)
            return
        for row in rows:
            click.echo(f"#{row['id']} | {row['created_at']} | {row['project']} | {row['type']} | {row['content'][:160]}")
        click.echo(f"\nReturned {len(rows)} of {total}")
        return

    args = ["search", query, "--top", str(top)]
    if agent_family:
        args += ["--agent-family", agent_family]
    if namespace:
        args += ["--namespace", namespace]
    if goal_id:
        args += ["--goal-id", goal_id]
    _run_brain(*args)


@memory_group.command(name="write")
@click.argument("content")
@click.option("--type", "-t", "entry_type", default="observation",
              help="Type: observation | decision | question | insight | error (default: observation)")
@click.option("--project", "-p", default="", help="Project name to tag this entry")
@click.option("--agent-family", "-a", default="",
              help="Agent family: claude | gemini | codex | antigravity | qwen")
@click.option("--scope", "-s", default="",
              help="Scope: shared | agent-scoped (auto-classified if omitted)")
def memory_write(content: str, entry_type: str, project: str, agent_family: str, scope: str) -> None:
    """Write a new entry to the shared brain.

    \b
    Examples:
      pt memory write "Decision: use Haiku for all routine tasks" --type decision
      pt memory write "Bug: pt scan hangs without Discord timeout" --type error --project project-tracker
      pt memory write "Trust layer is the right thesis" --type insight --project data-vault-factory
    """
    # Auto-detect project from cwd when not explicitly provided
    if not project:
        import os
        cwd = os.environ.get("PT_CALLER_CWD", os.getcwd())
        project = os.path.basename(cwd)
    args = ["write", content, "--type", entry_type]
    args += ["--project", project]
    if agent_family:
        args += ["--agent-family", agent_family]
    if scope:
        args += ["--scope", scope]
    _run_brain(*args)


@memory_group.command(name="recent")
@click.option("--since", default=None, help="Only include rows at/after ISO time or duration like 7d")
@click.option("--until", default=None, help="Only include rows at/before ISO time or duration like 7d")
@click.option("--source", default=None, help="Filter by source_machine or metadata.source_agent")
@click.option("--project", default=None, help="Filter by metadata.project")
@click.option("--limit", default=50, type=int, help="Maximum rows")
@click.option("--offset", default=0, type=int, help="Pagination offset")
@click.option("--json", "json_output", is_flag=True, help="Output stable machine-readable JSON")
def memory_recent(since, until, source, project, limit, offset, json_output) -> None:
    """List recent memory entries through a read-only DB connection."""
    try:
        rows, total, db_path = _memory_query_rows(
            since=since,
            until=until,
            source=source,
            project=project,
            limit=limit,
            offset=offset,
        )
    except PtJsonError as exc:
        if json_output:
            _emit_json_error(exc, "memory.recent")
        raise click.ClickException(exc.message) from exc
    payload = _memory_payload(
        "memory.recent",
        rows,
        total,
        db_path,
        limit,
        offset,
        {"since": since, "until": until, "source": source, "project": project},
    )
    if json_output:
        _emit_json(payload)
        return
    for row in rows:
        click.echo(f"#{row['id']} | {row['created_at']} | {row['project']} | {row['type']} | {row['content'][:160]}")
    click.echo(f"\nReturned {len(rows)} of {total}")


@memory_group.command(name="stats")
@click.option("--json", "json_output", is_flag=True, help="Output stable machine-readable JSON")
def memory_stats(json_output) -> None:
    """Show brain database statistics and per-agent search efficiency."""
    if json_output:
        try:
            with _open_memory_db_readonly() as conn:
                total = int(conn.execute("SELECT COUNT(*) FROM thoughts").fetchone()[0])
                by_project = [
                    {"project": row[0] or "", "count": row[1]}
                    for row in conn.execute(
                        "SELECT json_extract(metadata, '$.project') AS project, COUNT(*) "
                        "FROM thoughts GROUP BY project ORDER BY COUNT(*) DESC LIMIT 50"
                    ).fetchall()
                ]
                by_source = [
                    {"source": row[0] or "", "count": row[1]}
                    for row in conn.execute(
                        "SELECT COALESCE(json_extract(metadata, '$.source_agent'), source_machine, '') AS source, COUNT(*) "
                        "FROM thoughts GROUP BY source ORDER BY COUNT(*) DESC LIMIT 50"
                    ).fetchall()
                ]
                bounds = conn.execute("SELECT MIN(created_at), MAX(created_at) FROM thoughts").fetchone()
        except PtJsonError as exc:
            _emit_json_error(exc, "memory.stats")
        except sqlite3.Error as exc:
            _emit_json_error(
                PtJsonError("query_failure", f"memory stats failed: {exc}", EXIT_QUERY_FAILURE),
                "memory.stats",
            )
        _emit_json({
            "schema_version": PT_MEMORY_SCHEMA_VERSION,
            "ok": True,
            "command": "memory.stats",
            "read_only": True,
            "backend": {"type": "sqlite", "path": _memory_db_path().as_posix()},
            "stats": {
                "total": total,
                "oldest_created_at": bounds[0],
                "newest_created_at": bounds[1],
                "by_project": by_project,
                "by_source": by_source,
            },
        })
        return
    _run_brain("stats")


@memory_group.command(name="export")
@click.option("--format", "export_format", type=click.Choice(["ndjson"]), default="ndjson")
@click.option("--since", default=None, help="Only include rows at/after ISO time or duration like 7d")
@click.option("--until", default=None, help="Only include rows at/before ISO time or duration like 7d")
@click.option("--source", default=None, help="Filter by source_machine or metadata.source_agent")
@click.option("--project", default=None, help="Filter by metadata.project")
@click.option("--limit", default=500, type=int, help="Maximum rows")
@click.option("--offset", default=0, type=int, help="Pagination offset")
def memory_export(export_format, since, until, source, project, limit, offset) -> None:
    """Export memory rows as newline-delimited JSON for downstream analysis."""
    try:
        rows, _, _ = _memory_query_rows(
            since=since,
            until=until,
            source=source,
            project=project,
            limit=limit,
            offset=offset,
        )
    except PtJsonError as exc:
        _emit_json_error(exc, "memory.export", err=True)
    for row in rows:
        click.echo(json.dumps(row, sort_keys=True))


# =============================================================================
# Open Brain Graph (wraps brain.py graph subcommands)
# =============================================================================


@click.group(name="graph", invoke_without_command=True)
@click.pass_context
def graph_group(ctx: click.Context) -> None:
    """Query and manage the Open Brain graph.

    Open Brain extracts structured nodes (projects, people, artifacts,
    concepts, tasks, decisions) and edges (co_mentioned, belongs_to, relates_to)
    from all memories in brain.db.

    \b
    Node types:  project, person, artifact, concept, task, decision, tag
    Edge types:  co_mentioned, belongs_to, involved_in, tracked_in, relates_to

    \b
    Quick start:
      pt graph stats                          # Node/edge/confidence counts
      pt graph query project-tracker          # What's connected to a project
      pt graph find "Turso migration"         # Semantic search over nodes
      pt graph path ai-memory project-tracker # Shortest path between nodes
      pt graph communities                    # Leiden community detection
      pt graph wiki ai-memory                 # On-demand wiki article
      pt graph build                          # Rebuild from all memories
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@graph_group.command(name="stats")
def graph_stats() -> None:
    """Show Open Brain graph statistics — node/edge counts by type.

    \b
    Example output:
      Nodes: 1,498 (971 artifacts, 228 tasks, 193 concepts, ...)
      Edges: 11,225 (co_mentioned, belongs_to, relates_to, ...)
    """
    _run_brain("graph", "stats")


@graph_group.command(name="query")
@click.argument("project", required=False, default="")
@click.option("--hops", "-h", default=1, type=int,
              help="Degrees of separation from project node (default: 1)")
@click.option("--limit", "-n", default=20, type=int,
              help="Max nodes to return (default: 20)")
@click.option("--types", "-t", default="",
              help="Comma-separated node types to filter (e.g. decision,person)")
@click.option("--since", "-s", default="",
              help="Only nodes updated on/after this date (e.g. 2026-04-04)")
@click.option("--json", "as_json", is_flag=True,
              help="Output as JSON for agent consumption")
def graph_query(project: str, hops: int, limit: int, types: str, since: str, as_json: bool) -> None:
    """Query nodes connected to a project.

    Returns people, files, decisions, concepts, and tasks linked to the
    given project within N hops. Project auto-detected from cwd if omitted.
    Nodes ranked by freshness (mention count * temporal decay, 14-day half-life).

    \b
    Examples:
      pt graph query                              # Auto-detect from cwd
      pt graph query project-tracker              # Direct connections
      pt graph query ai-memory --hops 2           # Two degrees out
      pt graph query flo-fi --types decision,person  # Filter by type
      pt graph query ai-memory --since 2026-04-04    # What's new?
      pt graph query ai-memory --json             # JSON for agents
    """
    if not project:
        project = os.path.basename(os.getcwd())
    args = ["graph", "query", project, "--hops", str(hops), "--limit", str(limit)]
    if types:
        args.extend(["--types", types])
    if since:
        args.extend(["--since", since])
    if as_json:
        args.append("--json")
    _run_brain(*args)


@graph_group.command(name="find")
@click.argument("query")
@click.option("--top", "-k", default=10, type=int,
              help="Number of top matches (default: 10)")
@click.option("--hops", "-h", default=1, type=int,
              help="Expand to N-hop neighbors (0 = exact matches only)")
@click.option("--json", "as_json", is_flag=True,
              help="Output as JSON for agent consumption")
def graph_find(query: str, top: int, hops: int, as_json: bool) -> None:
    """Semantic search over graph nodes.

    Finds the graph nodes most similar to your query using embeddings,
    then expands to their neighbors. The 'what does the graph know about X?' query.

    \b
    Examples:
      pt graph find "authentication"              # What's related to auth?
      pt graph find "Turso migration" --top 5     # Focused search
      pt graph find "LoRA training" --hops 0      # Exact matches only
      pt graph find "deployment" --json            # JSON for agents
    """
    args = ["graph", "find", query, "--top", str(top), "--hops", str(hops)]
    if as_json:
        args.append("--json")
    _run_brain(*args)


@graph_group.command(name="path")
@click.argument("source")
@click.argument("target")
@click.option("--max-depth", "-d", default=5, type=int,
              help="Max BFS depth (default: 5)")
@click.option("--json", "as_json", is_flag=True,
              help="Output as JSON for agent consumption")
def graph_path(source: str, target: str, max_depth: int, as_json: bool) -> None:
    """Find shortest path between two nodes.

    BFS traversal from source to target. Shows the chain of nodes and
    edge types connecting them. Useful for understanding how projects relate.

    \b
    Examples:
      pt graph path flo-fi project-tracker        # How are they connected?
      pt graph path ai-memory antigravity-ide     # Cross-project links
      pt graph path Erik Turso --json             # JSON for agents
    """
    args = ["graph", "path", source, target, "--max-depth", str(max_depth)]
    if as_json:
        args.append("--json")
    _run_brain(*args)


@graph_group.command(name="export")
def graph_export() -> None:
    """Export full Open Brain graph as JSON (nodes + edges).

    Outputs to stdout. Pipe to a file or tool:

    \b
    Examples:
      pt graph export                    # Print to terminal
      pt graph export > graph.json       # Save to file
      pt graph export | jq '.nodes | length'  # Count nodes
    """
    _run_brain("graph", "export")


@graph_group.command(name="build")
@click.option("--force", is_flag=True, help="Truncate existing graph before rebuild")
def graph_build(force: bool) -> None:
    """Rebuild the Open Brain graph from all memories.

    Scans every entry in brain.db, extracts entities (projects, people,
    files, concepts, tasks, decisions), builds edges from co-mentions
    and semantic similarity, and writes to graph_nodes/graph_edges tables.

    \b
    Examples:
      pt graph build           # Incremental update
      pt graph build --force   # Full rebuild from scratch
    """
    args = ["graph", "build"]
    if force:
        args.append("--force")
    _run_brain(*args)


@graph_group.command(name="extract-upgrade")
@click.option("--dry-run", is_flag=True, help="Preview without modifying the graph")
@click.option("--full", is_flag=True, help="Re-scan all thoughts (default: only unprocessed)")
def graph_extract_upgrade(dry_run: bool, full: bool) -> None:
    """Re-extract entities from thought content using text-based extractors.

    By default, only processes new thoughts not yet text-extracted (incremental).
    Use --full to re-scan everything.

    \b
    Examples:
      pt graph extract-upgrade --dry-run   # Preview what would be added
      pt graph extract-upgrade             # Incremental (new thoughts only)
      pt graph extract-upgrade --full      # Re-scan everything
    """
    args = ["graph", "extract-upgrade"]
    if dry_run:
        args.append("--dry-run")
    if full:
        args.append("--full")
    _run_brain(*args)


@graph_group.command(name="wiki")
@click.argument("project", required=False, default="")
def graph_wiki(project: str) -> None:
    """Generate a Wikipedia-style article for a project's graph community.

    Synthesizes nodes and edges into a readable summary using Haiku.
    Generated on-demand — never stored. Project auto-detected from cwd.

    \b
    Examples:
      pt graph wiki                    # Auto-detect from cwd
      pt graph wiki ai-memory          # Specific project
      pt graph wiki project-tracker    # Another project
    """
    if not project:
        project = os.path.basename(os.getcwd())
    _run_brain("graph", "wiki", project)


@graph_group.command(name="communities")
@click.option("--resolution", "-r", default=1.0, type=float,
              help="Leiden resolution (default: 1.0, lower = fewer/larger communities)")
@click.option("--json", "as_json", is_flag=True,
              help="Output as JSON")
def graph_communities(resolution: float, as_json: bool) -> None:
    """Run Leiden community detection on the knowledge graph.

    Groups related nodes into communities automatically. Writes community_id
    to each node. Higher resolution = more/smaller communities.

    \b
    Examples:
      pt graph communities                    # Default resolution
      pt graph communities --resolution 0.5   # Fewer, larger communities
      pt graph communities --json             # JSON output
    """
    args = ["graph", "communities", "--resolution", str(resolution)]
    if as_json:
        args.append("--json")
    _run_brain(*args)


# =============================================================================
# Worktrees management
# =============================================================================

@click.group(name="worktrees", invoke_without_command=True)
@click.pass_context
def worktrees_group(ctx):
    """Manage .claude/worktrees/ created by sub-agents."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(worktrees_list)


@worktrees_group.command(name="list")
def worktrees_list():
    """List all worktrees in .claude/worktrees/."""
    repo_root = _find_repo_root()
    if repo_root is None:
        console.print("[red]Not inside a git repository[/red]")
        return
    wt_dir = repo_root / ".claude" / "worktrees"
    if not wt_dir.exists():
        console.print("[dim]No .claude/worktrees/ directory found[/dim]")
        return
    entries = sorted(p for p in wt_dir.iterdir() if p.is_dir())
    if not entries:
        console.print("[dim]No worktrees found[/dim]")
        return
    # Get merged branches
    merged = _get_merged_branches(repo_root)
    console.print(f"\n[bold]Worktrees ({len(entries)})[/bold]\n")
    for entry in entries:
        branch = _worktree_branch(repo_root, entry)
        status = "[green]merged[/green]" if branch and branch in merged else "[yellow]active[/yellow]"
        branch_label = branch or "[dim]detached[/dim]"
        console.print(f"  {entry.name}  {branch_label}  {status}")
    console.print()


@worktrees_group.command(name="clean")
@click.option("--dry-run", is_flag=True, help="Show what would be removed without removing")
@click.option("--force", is_flag=True, help="Also remove worktrees with uncommitted changes")
def worktrees_clean(dry_run, force):
    """Remove worktrees whose branches are merged to main or orphaned."""
    repo_root = _find_repo_root()
    if repo_root is None:
        console.print("[red]Not inside a git repository[/red]")
        return
    wt_dir = repo_root / ".claude" / "worktrees"
    if not wt_dir.exists():
        console.print("[dim]No .claude/worktrees/ directory found[/dim]")
        return
    entries = sorted(p for p in wt_dir.iterdir() if p.is_dir())
    if not entries:
        console.print("[dim]No worktrees to clean[/dim]")
        return

    merged = _get_merged_branches(repo_root)
    removed = []
    kept = []

    for entry in entries:
        branch = _worktree_branch(repo_root, entry)
        is_merged = branch and branch in merged
        is_orphaned = branch is None  # no branch ref found

        if is_merged or is_orphaned:
            reason = "merged" if is_merged else "orphaned"
            if dry_run:
                console.print(f"  [yellow]would remove[/yellow] {entry.name} ({reason}, branch: {branch or 'none'})")
                removed.append(entry.name)
            else:
                ok = _remove_worktree(repo_root, entry, force=force)
                if ok:
                    console.print(f"  [green]removed[/green] {entry.name} ({reason})")
                    removed.append(entry.name)
                    # Clean up the branch if it was a worktree-specific branch
                    if branch and branch.startswith("worktree-"):
                        _delete_local_branch(repo_root, branch)
                else:
                    console.print(f"  [red]failed to remove[/red] {entry.name} (use --force?)")
                    kept.append(entry.name)
        else:
            console.print(f"  [cyan]keeping[/cyan] {entry.name} (branch: {branch}, not merged)")
            kept.append(entry.name)

    prefix = "[bold yellow]Dry run:[/bold yellow] " if dry_run else ""
    console.print(f"\n{prefix}Removed {len(removed)}, kept {len(kept)}")


def _find_repo_root() -> Optional[Path]:
    """Find the git repo root from cwd or the project-tracker directory."""
    # Try project-tracker's own root first
    pt_root = Path(__file__).resolve().parent.parent
    if (pt_root / ".git").exists():
        return pt_root
    # Fallback: walk up from cwd
    cwd = Path.cwd()
    while cwd != cwd.parent:
        if (cwd / ".git").exists():
            return cwd
        cwd = cwd.parent
    return None


def _get_merged_branches(repo_root: Path) -> set:
    """Return set of branch names that are merged into main."""
    try:
        result = subprocess.run(
            ["git", "branch", "--merged", "main"],
            cwd=str(repo_root),
            capture_output=True, text=True, timeout=10,
            check=True,
        )
        branches = set()
        for line in result.stdout.splitlines():
            name = line.strip().lstrip("* ").lstrip("+ ")
            if name and name != "main":
                branches.add(name)
        return branches
    except subprocess.CalledProcessError as e:
        console.print(f"[yellow]Warning: Failed to check merged branches: {e.stderr.strip()}[/yellow]")
        return set()
    except subprocess.TimeoutExpired:
        console.print("[yellow]Warning: Timed out checking merged branches[/yellow]")
        return set()


def _worktree_branch(repo_root: Path, wt_path: Path) -> Optional[str]:
    """Get the branch name for a worktree, or None if detached/missing."""
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=str(repo_root),
            capture_output=True, text=True, timeout=10,
            check=True,
        )
        # Parse porcelain output: blocks separated by blank lines
        current_path = None
        for line in result.stdout.splitlines():
            if line.startswith("worktree "):
                current_path = line[len("worktree "):]
            elif line.startswith("branch ") and current_path:
                if Path(current_path).resolve() == wt_path.resolve():
                    # branch refs/heads/foo -> foo
                    ref = line[len("branch "):]
                    return ref.replace("refs/heads/", "")
        return None
    except subprocess.CalledProcessError as e:
        console.print(f"[yellow]Warning: Failed to determine branch for {wt_path.name}: {e.stderr.strip()}[/yellow]")
        return None
    except subprocess.TimeoutExpired:
        console.print(f"[yellow]Warning: Timed out determining branch for {wt_path.name}[/yellow]")
        return None


def _remove_worktree(repo_root: Path, wt_path: Path, force: bool = False) -> bool:
    """Remove a worktree using git worktree remove."""
    cmd = ["git", "worktree", "remove", str(wt_path)]
    if force:
        cmd.append("--force")
    try:
        result = subprocess.run(
            cmd, cwd=str(repo_root),
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            console.print(f"[yellow]Warning: git worktree remove failed for {wt_path.name}: {result.stderr.strip()}[/yellow]")
            return False
        return True
    except subprocess.TimeoutExpired:
        console.print(f"[yellow]Warning: Timed out removing worktree {wt_path.name}[/yellow]")
        return False


def _delete_local_branch(repo_root: Path, branch: str) -> None:
    """Delete a local branch (merged only, safe -d flag)."""
    try:
        result = subprocess.run(
            ["git", "branch", "-d", branch],
            cwd=str(repo_root),
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            console.print(f"[yellow]Warning: Failed to delete branch {branch}: {result.stderr.strip()}[/yellow]")
    except subprocess.TimeoutExpired:
        console.print(f"[yellow]Warning: Timed out deleting branch {branch}[/yellow]")


# =============================================================================
# Project Info — centralized key-value reference store
# =============================================================================

@click.group(name="info", invoke_without_command=True)
@click.option("-p", "--project", default=None, help="Show info for a specific project")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.pass_context
def info_group(ctx, project, json_output):
    """Centralized project and infrastructure reference.

    \b
    Quick start:
      pt info                              # Show global info
      pt info -p project-tracker           # Show project-specific info
      pt info set domain example.com       # Set global field
      pt info set tech_stack Python -p X   # Set project field
      pt info get domain                   # Get single global field
      pt info delete domain                # Delete global field
      pt info list                         # Show all entries

    \b
    Global keys (pt info):
      semantic_search      grep/rg setup (grepai config, ollama model)
      projects_root        Path to ~/projects
      db_backend           Database backend (local SQLite or Turso)
      default_doppler_config  Default doppler config (dev)
      mac_mini_ssh         SSH connection string for Mac Mini

    \b
    Per-project keys (pt info -p <project>):
      tech_stack           Languages, frameworks, key dependencies
      deploy_target        Where it runs (Vercel, Railway, Docker, local)
      doppler              Doppler project/config (e.g. project-tracker/dev)
      infrastructure       Databases, services, cron jobs, external deps

    \b
    Repopulate after DB rebuild:
      uv run scripts/populate_info.py          # Auto-detect and set all
      uv run scripts/populate_info.py --dry-run  # Preview first
    """
    if ctx.invoked_subcommand is not None:
        return
    db = DatabaseManager()
    if project:
        entries = db.get_info(project_id=project)
        label = f"{project} Info"
    else:
        entries = db.get_info(project_id=None)
        label = "Global Info"
    if json_output:
        import json as json_mod
        click.echo(json_mod.dumps(entries, indent=2))
        return
    if not entries:
        click.echo(f"{label}: (empty)")
        return
    click.echo(f"{label}:")
    for e in entries:
        click.echo(f"  {e['key']}: {e['value']}")


@info_group.command(name="set")
@click.argument("key")
@click.argument("value")
@click.option("-p", "--project", default=None, help="Project to scope this entry to")
def info_set(key, value, project):
    """Set a key-value info entry.

    \b
    Examples:
      pt info set domain synthinsightlabs.com
      pt info set tech_stack "Python, Flask, Turso" -p project-tracker
    """
    db = DatabaseManager()
    db.set_info(key, value, project_id=project)
    scope = f" (project: {project})" if project else " (global)"
    click.echo(f"Set {key} = {value}{scope}")


@info_group.command(name="get")
@click.argument("key")
@click.option("-p", "--project", default=None, help="Project scope")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def info_get(key, project, json_output):
    """Get a single info entry by key.

    \b
    Examples:
      pt info get domain
      pt info get tech_stack -p project-tracker
    """
    import json as json_mod
    db = DatabaseManager()
    entries = db.get_info(project_id=project, key=key)
    if not entries:
        scope = f" for project '{project}'" if project else " (global)"
        click.echo(f"No entry found for '{key}'{scope}")
        return
    if json_output:
        click.echo(json_mod.dumps(entries[0], indent=2))
    else:
        click.echo(entries[0]["value"])


@info_group.command(name="delete")
@click.argument("key")
@click.option("-p", "--project", default=None, help="Project scope")
def info_delete(key, project):
    """Delete an info entry.

    \b
    Examples:
      pt info delete domain
      pt info delete tech_stack -p project-tracker
    """
    db = DatabaseManager()
    deleted = db.delete_info(key, project_id=project)
    if deleted:
        scope = f" from project '{project}'" if project else " (global)"
        click.echo(f"Deleted '{key}'{scope}")
    else:
        click.echo(f"No entry found for '{key}'")


@info_group.command(name="list")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def info_list(json_output):
    """List all info entries across all projects.

    \b
    Examples:
      pt info list
      pt info list --json
    """
    import json as json_mod
    db = DatabaseManager()
    entries = db.get_info(project_id="__all__")
    if json_output:
        click.echo(json_mod.dumps(entries, indent=2))
        return
    if not entries:
        click.echo("No info entries found.")
        return
    # Group by project
    global_entries = [e for e in entries if e["project_id"] is None]
    project_entries = {}
    for e in entries:
        if e["project_id"] is not None:
            project_entries.setdefault(e["project_id"], []).append(e)
    if global_entries:
        click.echo("Global:")
        for e in global_entries:
            click.echo(f"  {e['key']}: {e['value']}")
    for pid in sorted(project_entries.keys()):
        click.echo(f"\n{pid}:")
        for e in project_entries[pid]:
            click.echo(f"  {e['key']}: {e['value']}")


# =============================================================================
# Config / Doctor — non-interactive automation diagnostics
# =============================================================================

def _effective_config_payload() -> dict:
    return {
        "schema_version": PT_CONFIG_SCHEMA_VERSION,
        "ok": True,
        "project_root": str(Path(__file__).resolve().parent.parent),
        "projects_root": str(PROJECTS_BASE_DIR),
        "tracker_db_path": str(get_db_path()),
        "memory_db_path": str(_memory_db_path()),
        "backend": "turso" if _USE_TURSO else "local",
        "env": {
            "PT_DB_PATH": os.environ.get("PT_DB_PATH"),
            "PT_MEMORY_DB_PATH": os.environ.get("PT_MEMORY_DB_PATH"),
            "PROJECTS_ROOT": os.environ.get("PROJECTS_ROOT"),
            "PT_SKIP_DOPPLER": os.environ.get("PT_SKIP_DOPPLER"),
            "PT_NO_BANNER": os.environ.get("PT_NO_BANNER"),
        },
    }


@click.group(name="config", invoke_without_command=True)
@click.pass_context
def config_group(ctx: click.Context) -> None:
    """Show effective pt runtime configuration."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@config_group.command(name="show")
@click.option("--effective", is_flag=True, help="Show resolved runtime configuration")
@click.option("--json", "json_output", is_flag=True, help="Output stable machine-readable JSON")
def config_show(effective: bool, json_output: bool) -> None:
    """Show effective configuration for cron/SSH debugging."""
    if not effective:
        raise click.UsageError("only --effective is currently supported")
    payload = _effective_config_payload()
    if json_output:
        _emit_json(payload)
        return
    for key, value in payload.items():
        if key == "env":
            click.echo("env:")
            for env_key, env_value in value.items():
                click.echo(f"  {env_key}: {env_value}")
        else:
            click.echo(f"{key}: {value}")


@cli.command(name="doctor")
@click.option("--json", "json_output", is_flag=True, help="Output stable machine-readable JSON")
def doctor(json_output: bool) -> None:
    """Check non-interactive PT readiness."""
    checks = []
    project_root = Path(__file__).resolve().parent.parent
    checks.append({
        "name": "pt_version",
        "ok": True,
        "detail": PT_VERSION,
    })
    checks.append({
        "name": "project_root",
        "ok": project_root.exists(),
        "detail": str(project_root),
    })
    checks.append({
        "name": "tracker_db",
        "ok": get_db_path().exists(),
        "detail": str(get_db_path()),
    })
    memory_ok = False
    memory_detail = str(_memory_db_path())
    try:
        with _open_memory_db_readonly() as conn:
            conn.execute("SELECT COUNT(*) FROM thoughts").fetchone()
        memory_ok = True
    except PtJsonError as exc:
        memory_detail = exc.message
    checks.append({
        "name": "memory_readonly",
        "ok": memory_ok,
        "detail": memory_detail,
    })
    checks.append({
        "name": "non_interactive_json",
        "ok": True,
        "detail": "memory search/recent/stats/export support read-only JSON/NDJSON without Doppler",
    })
    ok = all(check["ok"] for check in checks)
    payload = {
        "schema_version": PT_DOCTOR_SCHEMA_VERSION,
        "ok": ok,
        "version": PT_VERSION,
        "checks": checks,
        "cron_setup": {
            "recommended_path": f"{project_root / 'pt'}",
            "example": f"cd {project_root} && PT_SKIP_DOPPLER=1 ./pt memory recent --since 7d --json",
        },
    }
    if json_output:
        _emit_json(payload)
    else:
        for check in checks:
            status = "ok" if check["ok"] else "fail"
            click.echo(f"{status} {check['name']}: {check['detail']}")
    if not ok:
        raise SystemExit(EXIT_BACKEND_UNAVAILABLE)


# =============================================================================
# Message group (Agent Chat)
# =============================================================================

def _load_chat_config() -> dict:
    """Load Agent Chat config from ~/.claude/agent-chat.env or environment."""
    import os
    config = {
        "url": os.environ.get("AGENT_CHAT_URL", ""),
        "key": os.environ.get("AGENT_CHAT_API_KEY", ""),
        "sender": os.environ.get("AGENT_CHAT_SENDER", ""),
    }
    env_file = Path.home() / ".claude" / "agent-chat.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()
                if k == "AGENT_CHAT_URL":
                    config["url"] = v
                elif k == "AGENT_CHAT_API_KEY":
                    config["key"] = v
                elif k == "AGENT_CHAT_SENDER":
                    config["sender"] = v
    if not config["url"] or not config["key"]:
        raise click.ClickException(
            "Agent Chat not configured. Set AGENT_CHAT_URL and AGENT_CHAT_API_KEY "
            "in ~/.claude/agent-chat.env"
        )
    return config


def _chat_api_request(method: str, path: str, config: dict,
                      data: dict | None = None, params: dict | None = None) -> dict:
    """Make an HTTP request to the Agent Chat API. Returns parsed JSON."""
    from urllib.request import Request, urlopen
    from urllib.error import URLError, HTTPError
    from urllib.parse import urlencode
    import json as json_mod

    url = config["url"].rstrip("/") + path
    if params:
        filtered = {k: v for k, v in params.items() if v is not None}
        if filtered:
            url += "?" + urlencode(filtered)

    payload = json_mod.dumps(data).encode("utf-8") if data else None
    headers = {"X-API-Key": config["key"]}
    if data:
        headers["Content-Type"] = "application/json"

    req = Request(url, data=payload, headers=headers, method=method)
    try:
        resp = urlopen(req, timeout=15)
        return json_mod.loads(resp.read())
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise click.ClickException(f"Agent Chat API error {e.code}: {body}")
    except (URLError, OSError, TimeoutError) as e:
        raise click.ClickException(f"Agent Chat API unreachable: {e}")


def _format_message_line(m: dict) -> str:
    """Format a single message as a pipe-delimited line."""
    sender = m.get("sender", "?")
    recipient = m.get("recipient")
    arrow = f"{sender} -> {recipient}" if recipient else sender
    priority = m.get("priority", "normal")
    body_preview = (m.get("body") or "").replace("\n", " ")[:80]
    ts = m.get("ts", "")
    msg_id = m.get("id", "?")
    reply = f" (reply to #{m['reply_to']})" if m.get("reply_to") else ""
    return f"#{msg_id} | {ts} | {arrow}{reply} | {priority} | {body_preview}"


@click.group(name="message", invoke_without_command=True)
@click.pass_context
def message_group(ctx):
    """Agent Chat — send and read messages between agents.

    \b
    Quick start:
      pt message                           # Recent messages
      pt message send "Deploy looks good"  # Send to chat
      pt message list --limit 10           # List with filters
      pt message list --sender mini-claude # Filter by sender
      pt message send "Check status" --to mini-claude  # Direct message
    """
    if ctx.invoked_subcommand is not None:
        return
    ctx.invoke(message_list)


@message_group.command(name="send")
@click.argument("text")
@click.option("--to", "recipient", default=None, help="Direct message to a specific agent")
@click.option("--priority", type=click.Choice(["low", "normal", "high", "urgent"]),
              default="normal", help="Message priority")
@click.option("--reply-to", "reply_to", type=int, default=None,
              help="Message ID to reply to")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def message_send(text, recipient, priority, reply_to, json_output):
    """Send a message to Agent Chat.

    \b
    Examples:
      pt message send "SIW launch prep complete"
      pt message send "Check your inbox" --to mini-claude
      pt message send "Acknowledged" --reply-to 19 --priority high
    """
    import json as json_mod
    config = _load_chat_config()
    payload = {
        "sender": config["sender"],
        "body": text,
        "priority": priority,
    }
    if recipient:
        payload["to"] = recipient
    if reply_to:
        payload["reply_to"] = reply_to

    result = _chat_api_request("POST", "/send", config, data=payload)

    if json_output:
        print(json_mod.dumps(result, indent=2))
    else:
        click.echo(f"Sent #{result.get('id', '?')} as {config['sender']}")


@message_group.command(name="list")
@click.option("--limit", "-n", default=20, type=int, help="Number of messages (default: 20)")
@click.option("--since", default=None, help="Show messages after this ISO timestamp")
@click.option("--sender", default=None, help="Filter by sender")
@click.option("--for", "for_recipient", default=None,
              help="Show messages visible to this agent (broadcasts + DMs)")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def message_list(limit, since, sender, for_recipient, json_output):
    """List messages from Agent Chat.

    \b
    Examples:
      pt message list                        # Recent 20 messages
      pt message list --limit 5              # Last 5
      pt message list --sender mini-claude   # From mini-claude
      pt message list --for claude-architect # Visible to architect
      pt message list --since 2026-04-03T00:00:00Z
    """
    import json as json_mod
    config = _load_chat_config()
    params = {"limit": str(limit)}
    if since:
        params["since"] = since
    if sender:
        params["sender"] = sender
    if for_recipient:
        params["for"] = for_recipient

    result = _chat_api_request("GET", "/messages", config, params=params)
    messages = result.get("messages", [])

    if json_output:
        print(json_mod.dumps(result, indent=2))
        return
    if not messages:
        click.echo("No messages found.")
        return
    for m in messages:
        click.echo(_format_message_line(m))
    click.echo(f"\nMessages: {len(messages)}")


# =============================================================================
# pt skills — skill-invocation leaderboards (#5913)
# =============================================================================

@click.group(name="skills", invoke_without_command=True)
@click.pass_context
def skills_group(ctx):
    """Skill usage leaderboards backed by ai-memory's skill_invocations table."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


def _collect_invocations(**filters):
    """Read-through helper that turns reader errors into click.UsageError."""
    from datetime import datetime, timedelta, timezone

    days = filters.pop("days", 30)
    since = None
    if days and days > 0:
        since = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        rows = list(_iter_skill_invocations(since=since, **filters))
    except _SkillsTursoEnabledError as exc:
        raise click.ClickException(str(exc)) from exc
    except _SkillInvocationsTableMissing as exc:
        raise click.ClickException(str(exc)) from exc
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    return rows, days


def _fmt_last_used(dt):
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


_UNKNOWN_AGENT_LABEL = "unknown"


def _agent_display(caller_type: str) -> str:
    """Render empty caller_type as 'unknown' for humans; everything else raw."""
    return caller_type or _UNKNOWN_AGENT_LABEL


def _agent_query_value(flag_value: str) -> str:
    """Translate the ``--agent`` CLI value into the raw caller_type string.

    Invariant (per ai-memory #6026 v2): caller_type is never the literal
    string 'unknown' in the DB — it's either a real attribution ('main',
    'subagent', …) or empty. So mapping the human-friendly 'unknown' token
    to '' is safe and round-trip-unambiguous. Revisit this translation if
    the producer hook ever starts writing 'unknown' as an explicit value.
    """
    return "" if flag_value == _UNKNOWN_AGENT_LABEL else flag_value


@skills_group.command(name="stats")
@click.option("--days", type=int, default=30,
              help="Look-back window in days. 0 = all time.")
@click.option("--skill", "skill_filter", default=None,
              help="Only show rows for one skill name.")
@click.option("--agent", "agent_filter", default=None,
              help="Only show rows for one caller_type. Use 'unknown' to match empty.")
@click.option("--project", "project_filter", default=None,
              help="Only show rows whose cwd resolves to this project label.")
@click.option("--never-used", is_flag=True,
              help="Installed skills with zero invocations in the window.")
@click.option("--by-project", is_flag=True,
              help="Group the leaderboard by project.")
@click.option("--by-agent", is_flag=True,
              help="Group the leaderboard by caller_type (agent identity).")
@click.option("--json", "json_output", is_flag=True,
              help="Emit machine-readable JSON instead of a Rich table.")
def skills_stats(days, skill_filter, agent_filter, project_filter,
                 never_used, by_project, by_agent, json_output):
    """Leaderboard of skill invocations over a time window."""
    import json as json_mod
    from collections import Counter, defaultdict

    render_modes = [m for m, on in (
        ("--never-used", never_used),
        ("--by-project", by_project),
        ("--by-agent", by_agent),
    ) if on]
    if len(render_modes) > 1:
        raise click.UsageError(
            f"{' and '.join(render_modes)} are mutually exclusive — pick one."
        )

    rows, window_days = _collect_invocations(
        skill=skill_filter,
        agent=_agent_query_value(agent_filter) if agent_filter is not None else None,
        project=project_filter,
        days=days,
    )

    if never_used:
        used = {r.skill_name for r in rows}
        installed = _installed_skills()
        missing = sorted(set(installed) - used)
        if json_output:
            print(json_mod.dumps({
                "window_days": window_days,
                "installed_count": len(installed),
                "used_count": len(used),
                "never_used": missing,
            }, indent=2))
            return
        table = Table(title=f"Installed skills never invoked in last {window_days} day(s)",
                      show_header=True, header_style="bold")
        table.add_column("Skill")
        table.add_column("SKILL.md", style="dim")
        for name in missing:
            table.add_row(name, str(installed[name]))
        console.print(table)
        console.print(f"[dim]{len(missing)} never-used of {len(installed)} installed[/dim]")
        return

    if by_project:
        per_project: dict[str, Counter] = defaultdict(Counter)
        for r in rows:
            per_project[r.project][r.skill_name] += 1
        if json_output:
            print(json_mod.dumps({
                "window_days": window_days,
                "projects": {p: dict(c) for p, c in per_project.items()},
            }, indent=2))
            return
        for project, counter in sorted(per_project.items()):
            table = Table(title=f"Project: {project}",
                          show_header=True, header_style="bold")
            table.add_column("Skill")
            table.add_column("Calls", justify="right")
            for name, count in counter.most_common():
                table.add_row(name, str(count))
            console.print(table)
        return

    if by_agent:
        per_agent: dict[str, Counter] = defaultdict(Counter)
        for r in rows:
            per_agent[_agent_display(r.caller_type)][r.skill_name] += 1
        if json_output:
            print(json_mod.dumps({
                "window_days": window_days,
                "agents": {a: dict(c) for a, c in per_agent.items()},
            }, indent=2))
            return
        for agent, counter in sorted(per_agent.items()):
            table = Table(title=f"Agent: {agent}",
                          show_header=True, header_style="bold")
            table.add_column("Skill")
            table.add_column("Calls", justify="right")
            for name, count in counter.most_common():
                table.add_row(name, str(count))
            console.print(table)
        return

    counter: Counter = Counter()
    last_seen: dict[str, "datetime"] = {}
    for r in rows:
        counter[r.skill_name] += 1
        if r.skill_name not in last_seen or r.invoked_at > last_seen[r.skill_name]:
            last_seen[r.skill_name] = r.invoked_at

    if json_output:
        payload = {
            "window_days": window_days,
            "total_invocations": len(rows),
            "skills": [
                {
                    "skill": name,
                    "calls": count,
                    "last_used": last_seen[name].isoformat(timespec="seconds"),
                }
                for name, count in counter.most_common()
            ],
        }
        print(json_mod.dumps(payload, indent=2))
        return

    window_label = "all time" if window_days == 0 else f"last {window_days} day(s)"
    table = Table(title=f"Skill usage — {window_label}",
                  show_header=True, header_style="bold")
    table.add_column("Skill")
    table.add_column("Calls", justify="right")
    table.add_column("Last used", style="dim")
    for name, count in counter.most_common():
        table.add_row(name, str(count), _fmt_last_used(last_seen[name]))
    console.print(table)
    console.print(f"[dim]{len(rows)} invocation(s) across {len(counter)} skill(s)[/dim]")


# =============================================================================
# pt db — schema migration runner (Phase 2.1a step 2 / §2.2 wrapper)
# =============================================================================


@click.group(name="db", invoke_without_command=True)
@click.pass_context
def db_group(ctx):
    """Database schema migrations.

    The migration runner applies any pending migrations from
    `scripts/db/migrations/` to the local tracker.db. Each migration
    runs inside a transaction; CRR-table alters are bracketed with
    `crsql_begin_alter` / `crsql_commit_alter` when cr-sqlite is loaded
    (skipped otherwise). See MAC_MINI_SYNC_PLAN.md §2.1a and §2.2.
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@db_group.command(name="migrate")
def db_migrate():
    """Apply every pending migration in order.

    Refuses to run against Turso — the runner targets local SQLite
    only. Future work (PR #3b) will refuse if data-plane sync is
    currently running. Today sync isn't on, so that check is a no-op.
    """
    if _USE_TURSO:
        console.print(
            "[red]pt db migrate: Turso backend is active — this runner "
            "targets local SQLite only.[/red]"
        )
        console.print(
            "[dim]Disable Turso in ~/projects/.turso-config.json to use "
            "the local runner.[/dim]"
        )
        sys.exit(2)

    from db.migration_runner import apply_all

    db_path = get_db_path()
    migrations_dir = Path(__file__).parent / "db" / "migrations"
    if not migrations_dir.is_dir():
        console.print(f"[red]no migrations directory at {migrations_dir}[/red]")
        sys.exit(2)

    # isolation_level=None puts the driver into manual-commit mode, so
    # the runner's explicit BEGIN/COMMIT/ROLLBACK statements are the
    # only transaction boundaries. Without this, Python's sqlite3
    # auto-inserts a BEGIN before DML and we'd have nested transactions.
    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        applied = apply_all(conn, migrations_dir)
    finally:
        conn.close()

    if not applied:
        console.print("[green]✓ no pending migrations[/green]")
        return

    console.print(
        f"[green]✓ applied {len(applied)} migration(s):[/green]"
    )
    for m in applied:
        console.print(f"  • {m.version:03d}_{m.name}")


# =============================================================================
# pt sync — data-plane pause/resume + status (Phase 2.1b)
# =============================================================================
#
# The underlying sync daemon (cr-sqlite replication over Tailscale) isn't
# built yet — this CLI is the operator-facing surface the migration
# policy (§2.3 `pt db migrate`) depends on. Today `pt sync status`
# reports "sync engine disabled" because cr-sqlite isn't loaded; pause
# and resume still work (they persist intent to _metadata) so when the
# daemon lands in PR #3c it reads the same state.


@click.group(name="sync", invoke_without_command=True)
@click.pass_context
def sync_group(ctx):
    """Data-plane sync control (cr-sqlite replication, Phase 2).

    \b
    Commands:
        pt sync status     — show pause state + last sync + engine state
        pt sync check      — verify local sync readiness before broader rollout
        pt sync pause      — halt data-plane replication (control plane keeps running)
        pt sync pause --all — halt everything (rare; stops migration announcements too)
        pt sync resume     — resume data-plane replication
        pt sync set-machine-id <id> — persist _metadata['pt.machine_id']
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


def _sync_conn() -> sqlite3.Connection:
    """Open a sqlite connection to the tracker DB for sync-state reads/writes.

    ``isolation_level=None`` so the sync_state module's implicit
    commits (``INSERT OR REPLACE`` / ``DELETE``) take effect without
    a second transaction wrapping them.

    A ``sqlite3.Error`` here (corrupt file, permissions, stale path)
    is translated into a ``click.UsageError`` by the callers so the
    operator gets "pt sync status: <reason>" instead of a raw Python
    traceback. Keeps error output consistent with the rest of pt.
    """
    return sqlite3.connect(get_db_path(), isolation_level=None)


def _handle_sync_db_error(cmd: str, err: Exception) -> None:
    """Print a uniform error and exit 2 for sync DB failures.

    Called by sync_status / sync_pause / sync_resume so a broken DB
    path produces a clean message, not a traceback.
    """
    console.print(f"[red]pt sync {cmd}: {err}[/red]")
    sys.exit(2)


def _sync_engine_active(conn: sqlite3.Connection) -> bool:
    """True when cr-sqlite is loaded — shipping sync is gated on this."""
    try:
        conn.execute("SELECT crsql_db_version()")
        return True
    except sqlite3.OperationalError:
        return False


@sync_group.command(name="status")
def sync_status():
    """Show pause state, last successful sync, and engine availability."""
    if _USE_TURSO:
        console.print("[yellow]sync engine: Turso (replication handled upstream)[/yellow]")
        return
    from db.sync_state import is_paused, pause_scope, last_sync
    try:
        conn = _sync_conn()
    except sqlite3.Error as err:
        _handle_sync_db_error("status", err)
        return  # pragma: no cover — _handle_sync_db_error raises SystemExit
    try:
        paused = is_paused(conn)
        scope = pause_scope(conn)
        last = last_sync(conn)
        engine_on = _sync_engine_active(conn)
    finally:
        conn.close()

    engine_line = (
        "[green]engine: cr-sqlite loaded[/green]"
        if engine_on
        else "[dim]engine: cr-sqlite NOT loaded (sync not yet active)[/dim]"
    )
    if paused:
        state = f"[yellow]paused ({scope})[/yellow]"
    else:
        state = "[green]running[/green]" if engine_on else "[dim]idle[/dim]"
    last_line = last or "[dim]never[/dim]"

    console.print(f"state:         {state}")
    console.print(f"last sync:     {last_line}")
    console.print(engine_line)


@sync_group.command(name="check")
def sync_check():
    """Verify local sync-readiness prerequisites against the live DB."""
    if _USE_TURSO:
        console.print("[yellow]pt sync check: Turso mode — local SQLite readiness does not apply.[/yellow]")
        return
    from db.sync_checks import local_sync_readiness

    try:
        conn = _sync_conn()
    except sqlite3.Error as err:
        _handle_sync_db_error("check", err)
        return  # pragma: no cover
    try:
        checks = local_sync_readiness(conn)
    except sqlite3.Error as err:
        _handle_sync_db_error("check", err)
        return  # pragma: no cover
    finally:
        conn.close()

    all_ok = True
    for check in checks:
        label = "[green]ok[/green]" if check.ok else "[red]fail[/red]"
        if not check.ok:
            all_ok = False
        console.print(f"{label} {check.name}: {check.detail}")

    if not all_ok:
        sys.exit(3)


@sync_group.command(name="set-machine-id")
@click.argument("machine_id", type=int)
def sync_set_machine_id(machine_id: int):
    """Persist _metadata['pt.machine_id'] for this machine."""
    if _USE_TURSO:
        console.print("[red]pt sync set-machine-id: Turso mode — local SQLite metadata is not active.[/red]")
        sys.exit(2)

    from db.sync_checks import set_explicit_machine_id

    try:
        conn = _sync_conn()
    except sqlite3.Error as err:
        _handle_sync_db_error("set-machine-id", err)
        return  # pragma: no cover
    try:
        set_explicit_machine_id(conn, machine_id)
    except ValueError as err:
        console.print(f"[red]pt sync set-machine-id: {err}[/red]")
        sys.exit(2)
    except sqlite3.Error as err:
        _handle_sync_db_error("set-machine-id", err)
        return  # pragma: no cover
    finally:
        conn.close()

    console.print(f"[green]✓ pt.machine_id set to {machine_id}.[/green]")


@sync_group.command(name="pause")
@click.option(
    "--all", "all_scope", is_flag=True,
    help="Halt control plane too (stops migration announcements). Rare.",
)
def sync_pause(all_scope: bool):
    """Halt data-plane replication. Control plane keeps running unless --all."""
    if _USE_TURSO:
        console.print("[red]pt sync pause: Turso mode — nothing to pause locally.[/red]")
        sys.exit(2)
    from db.sync_state import set_paused
    scope = "all" if all_scope else "data_plane"
    try:
        conn = _sync_conn()
    except sqlite3.Error as err:
        _handle_sync_db_error("pause", err)
        return  # pragma: no cover
    try:
        set_paused(conn, scope=scope)  # type: ignore[arg-type]
    except sqlite3.Error as err:
        _handle_sync_db_error("pause", err)
        return  # pragma: no cover
    finally:
        conn.close()
    console.print(f"[yellow]✓ sync paused ({scope}).[/yellow]")
    if scope == "all":
        console.print(
            "[dim]Control plane is ALSO halted — migration announcements "
            "won't cross machines until resume.[/dim]"
        )


@sync_group.command(name="resume")
@click.option(
    "--force", is_flag=True,
    help="Resume even if the peer hasn't acknowledged a recently-applied migration.",
)
def sync_resume(force: bool):
    """Resume data-plane replication.

    Implements the §2.3 step-6 gate: refuses to clear the pause state
    when this machine has applied a migration that the peer hasn't
    announced yet (determined from ``schema_migration_announcements``
    — which is CRR-classified, so peer's rows replicate in via the
    always-on control plane once cr-sqlite lands).

    The gate only activates once ``schema_migration_announcements`` is
    flipped to CRR (§2.5) AND this machine has a local ``site_id``
    (cr-sqlite loaded). Before then it's a no-op — otherwise a
    daemon-less install could never resume, since no peer rows can
    replicate in.
    """
    if _USE_TURSO:
        console.print("[red]pt sync resume: Turso mode — nothing to resume locally.[/red]")
        sys.exit(2)
    from db.sync_state import clear_paused, is_paused
    try:
        conn = _sync_conn()
    except sqlite3.Error as err:
        _handle_sync_db_error("resume", err)
        return  # pragma: no cover
    try:
        if not force:
            blocked = _sync_resume_blocked_versions(conn)
            if blocked:
                versions = ", ".join(f"{v:03d}" for v in blocked)
                console.print(
                    f"[yellow]pt sync resume: waiting for peer to apply "
                    f"migration(s) {versions}.[/yellow]"
                )
                console.print(
                    "On the peer machine, run:\n"
                    "    cd ~/projects/project-tracker && git pull\n"
                    "    pt db migrate\n"
                    "Resume will proceed automatically once the peer's "
                    "announcement arrives. "
                    "Use [cyan]--force[/cyan] to override this gate."
                )
                sys.exit(3)
        was_paused = is_paused(conn)
        clear_paused(conn)
    except sqlite3.Error as err:
        _handle_sync_db_error("resume", err)
        return  # pragma: no cover
    finally:
        conn.close()
    if was_paused:
        console.print("[green]✓ sync resumed.[/green]")
    else:
        console.print("[dim]sync was not paused.[/dim]")


def _sync_resume_blocked_versions(conn: sqlite3.Connection) -> list[int]:
    """Migration versions applied locally but not yet announced by the peer.

    Returns an empty list when the gate can't meaningfully run (no
    cr-sqlite ⇒ no site_id ⇒ peer rows can't replicate in anyway, so
    blocking on "peer hasn't announced" would be blocking forever).
    This mirrors the guard in ``sync_daemon._outstanding_peer_announcements``
    and keeps the CLI's logic in sync with the daemon's.
    """
    try:
        site_row = conn.execute("SELECT crsql_site_id()").fetchone()
    except sqlite3.OperationalError:
        return []  # cr-sqlite not loaded — nothing to gate on
    # `not site_row[0]` catches both None and empty-string site ids.
    # An empty site id would match WHERE machine_id = '' and silently
    # return zero rows, making the gate a no-op with misleading logs.
    if not site_row or not site_row[0]:
        return []
    site_id = site_row[0]
    try:
        rows = conn.execute(
            "SELECT version FROM schema_migration_announcements "
            "WHERE machine_id = ? "
            "EXCEPT "
            "SELECT version FROM schema_migration_announcements "
            "WHERE machine_id != ?",
            (site_id, site_id),
        ).fetchall()
    except sqlite3.OperationalError:
        return []  # table missing — gate is moot
    return sorted(r[0] for r in rows)


# =============================================================================
# Register subgroups and run
# =============================================================================

cli.add_command(backup_group)
cli.add_command(tasks_group)
cli.add_command(inbox_group)
cli.add_command(calendar_group)
cli.add_command(memory_group)
cli.add_command(graph_group)
cli.add_command(worktrees_group)
cli.add_command(info_group)
cli.add_command(config_group)
cli.add_command(message_group)
cli.add_command(skills_group)
cli.add_command(db_group)
cli.add_command(sync_group)

if __name__ == "__main__":
    cli()
