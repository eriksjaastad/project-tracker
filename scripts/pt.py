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

import sys
import webbrowser
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
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
from db.manager import DatabaseManager
from discovery.project_scanner import discover_projects, scan_health_parallel
from discovery.external_resources_parser import parse_external_resources
from discovery.hygiene_detector import fix_hygiene_issues, detect_hygiene_issues
from discovery.graph_builder import GraphBuilder
from discovery.librarian import update_directory_index
from discovery.journal_specialist import JournalSpecialist

console = Console()



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


@click.group(invoke_without_command=True)
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
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


def compare_versions(v1, v2):
    if v1 is None and v2 is None: return 0
    if v1 is None: return -1
    if v2 is None: return 1
    try:
        parts1 = [int(x) for x in v1.split('.')]
        parts2 = [int(x) for x in v2.split('.')]
        while len(parts1) < len(parts2): parts1.append(0)
        while len(parts2) < len(parts1): parts2.append(0)
        for p1, p2 in zip(parts1, parts2):
            if p1 < p2: return -1
            elif p1 > p2: return 1
        return 0
    except (ValueError, AttributeError):
        return -1 if v1 < v2 else (1 if v1 > v2 else 0)


def get_current_scaffolding_version():
    import json
    version_file = Path(PROJECTS_BASE_DIR) / "project-scaffolding" / ".scaffolding-version"
    if not version_file.exists(): return None, None
    try:
        data = json.loads(version_file.read_text())
        return data.get("scaffolding_version"), data.get("rules_version")
    except Exception:
        return None, None


def rebuild_knowledge_graph():
    console.print("[bold blue]Rebuilding knowledge graph & analysis...[/bold blue]")
    try:
        root_path = Path(PROJECTS_BASE_DIR)
        output_path = Path(__file__).parent.parent / "data" / "graph.json"
        analysis_path = Path(__file__).parent.parent / "data" / "graph_analysis.md"
        ecosystem_todo = root_path / "TODO.md"
        console.print("[bold cyan]  → Running Librarian (Networking projects)...[/bold cyan]")
        for item in root_path.iterdir():
            if item.is_dir() and not item.name.startswith(".") and item.name not in ["node_modules", "venv", ".venv", "_trash", "_inbox", "trash"]:
                update_directory_index(item, recursive=True)
        builder = GraphBuilder(root_path)
        builder.scan()
        builder.save(output_path)
        analysis_text = builder.generate_analysis()
        analysis_path.write_text(analysis_text)
        if ecosystem_todo.exists():
            builder.update_todo(ecosystem_todo)
        console.print(f"  ✓ Knowledge graph & analysis updated")
        console.print("[bold cyan]  → Running Journal Specialist (Enriching links)...[/bold cyan]")
        specialist = JournalSpecialist()
        specialist.scan()
    except Exception as e:
        console.print(f"  [red]✗ Error rebuilding knowledge graph: {e}[/red]")


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
        projects = discover_projects(PROJECTS_BASE_DIR, sync_indexes=not dry_run)
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
    hygiene_fixes = 0
    for project in projects:
        todo_path = Path(project["path"]) / "TODO.md"
        if todo_path.exists():
            fixes = fix_hygiene_issues(todo_path)
            if fixes > 0:
                hygiene_fixes += fixes
                from discovery.project_scanner import extract_project_metadata
                project.update(extract_project_metadata(Path(project["path"])))
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
                    scaffolding_version=project.get("scaffolding_version"),
                    rules_version=project.get("rules_version"),
                    scaffolding_applied_at=project.get("scaffolding_applied_at")
                )
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
    if hygiene_fixes > 0:
        console.print(f"\n[bold yellow]✨ Hygiene: Applied {hygiene_fixes} auto-fixes to TODO.md files[/bold yellow]")
    if not no_graph:
        console.print("")
        rebuild_knowledge_graph()
    console.print(f"\n[bold green]✅ Scan complete! {len(projects)} projects updated[/bold green]")


def _has_complete_prompt(prompt):
    if not prompt: return False
    prompt_lower = prompt.lower()
    return "## overview" in prompt_lower and "## execution" in prompt_lower and "## done criteria" in prompt_lower


def _display_tasks(task_list, project=None, json_output=False, db=None):
    import json as json_lib
    if json_output:
        print(json_lib.dumps({"tasks": task_list, "total": len(task_list)}, indent=2))
        return
    if not task_list:
        filter_msg = f" for project '{project}'" if project else ""
        print(f"No tasks found{filter_msg}.")
        return
    title = f"Tasks - {project}" if project else "Tasks"
    print(f"{title}\n")
    for task in task_list:
        priority = task.get("priority") or "-"
        status = task["status"]
        task_id = task["id"]
        task_text = task["text"]
        if _has_complete_prompt(task.get("prompt")): prompt_marker = ""
        elif task.get("prompt"): prompt_marker = "[~P] "
        else: prompt_marker = "[!P] "
        blocked_marker = ""
        if db and task.get("blocked_by"):
            is_blocked, blocking_ids = db.is_blocked(task_id)
            if is_blocked:
                blocked_marker = f"[B:{','.join(str(i) for i in blocking_ids)}] "
        machine_str = task.get("machine") or ""
        machine_marker = f" | {machine_str}" if machine_str else ""
        if project:
            print(f"#{task_id} {prompt_marker}{blocked_marker}| {status} | {priority}{machine_marker} | {task_text}")
        else:
            print(f"#{task_id} {prompt_marker}{blocked_marker}| {task['project_id']} | {status} | {priority}{machine_marker} | {task_text}")
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


def _detect_project_from_cwd(db):
    import os
    cwd = os.getcwd()
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
@click.option("--no-graph", is_flag=True, help="Skip rebuilding the knowledge graph")
@click.option("--dry-run", is_flag=True, help="Show what would change without writing")
@click.option("--force", is_flag=True, help="Proceed even if scan results look unsafe")
def scan_cli(no_graph, dry_run, force):
    """Scan projects directory and update database."""
    scan(no_graph=no_graph, dry_run=dry_run, force=force)


@cli.command(name="list")
@click.option("--outdated", is_flag=True, help="Show only projects with outdated scaffolding")
def list_projects(outdated):
    """List all projects."""
    db = DatabaseManager()
    projects = db.get_all_projects()
    if not projects:
        print("No projects found. Run 'pt scan' first.")
        return
    if outdated:
        current_scaffolding, current_rules = get_current_scaffolding_version()
        filtered_projects = []
        for p in projects:
            project_version = p.get("scaffolding_version")
            if project_version is None:
                filtered_projects.append(p)
            elif current_scaffolding and compare_versions(project_version, current_scaffolding) < 0:
                filtered_projects.append(p)
        projects = filtered_projects
        if not projects:
            print("No outdated projects found. All projects are up to date!")
            return
    print("Projects\n")
    for project in projects:
        idx = "✓" if project.get("has_index") and project.get("index_is_valid") else "!"
        phase = project.get("phase") or "-"
        pct = project.get("completion_pct", 0)
        version_info = ""
        if "scaffolding_version" in project:
            if project["scaffolding_version"]:
                version_info = f" | v{project['scaffolding_version']}"
            else:
                version_info = " | no scaffolding"
        print(f"{project['name']} | {project['status']} | {phase} | {pct}% | {idx}{version_info}")
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
def refresh():
    """Refresh all project metadata."""
    console.print("[bold blue]Refreshing project data...[/bold blue]")
    _scan_impl()


@cli.command()
@click.option("--fix", is_flag=True, help="Apply fixes automatically")
def hygiene(fix):
    """Check all projects for TODO.md hygiene issues."""
    console.print("[bold blue]Checking project hygiene...[/bold blue]")
    projects = discover_projects(PROJECTS_BASE_DIR)
    total_issues = 0
    total_fixes = 0
    for p in projects:
        todo_path = Path(p["path"]) / "TODO.md"
        if not todo_path.exists(): continue
        issues = detect_hygiene_issues(todo_path)
        if issues:
            console.print(f"\n[bold cyan]{p['name']}[/bold cyan]")
            for issue in issues:
                console.print(f"  [yellow]⚠ {issue['message']}[/yellow]")
                total_issues += 1
            if fix:
                fixes = fix_hygiene_issues(todo_path)
                total_fixes += fixes
                if fixes > 0:
                    console.print(f"  [green]✓ Applied {fixes} fixes[/green]")
    if total_issues == 0:
        console.print("\n[bold green]✅ All projects are clean![/bold green]")
    elif fix:
        console.print(f"\n[bold green]✅ Applied {total_fixes} total fixes across {total_issues} issues.[/bold green]")
    else:
        console.print(f"\n[bold yellow]⚠ Found {total_issues} total issues. Run 'pt hygiene --fix' to resolve.[/bold yellow]")


@cli.command()
@click.option("--port", default=8000, type=int, help="Port to run on")
@click.option("--no-scan", is_flag=True, help="Skip the initial project scan on launch")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
def launch(port, no_scan, reload):
    """Launch the web dashboard."""
    console.print("[bold green]Launching Project Tracker Dashboard...[/bold green]\n")
    init_db()
    if not no_scan:
        console.print("[dim]Running quick scan...[/dim]")
        _scan_impl()
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
    venv_python = Path(__file__).parent.parent / "venv" / "bin" / "python"
    cmd = [str(venv_python), "-m", "uvicorn", "dashboard.app:app", "--host", "0.0.0.0", "--port", str(port)]
    if reload: cmd.append("--reload")
    try:
        subprocess.run(cmd, cwd=Path(__file__).parent.parent)
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


@cli.command(name="set-machine")
@click.argument("project")
@click.argument("machine_value", type=click.Choice(["MacBook", "OpenClaw", "Both", "none"], case_sensitive=True))
def set_machine(project, machine_value):
    """Set the default machine for a project."""
    db = DatabaseManager()
    project_id = _resolve_project_id(db, project)
    if not project_id:
        console.print(f"[red]Project '{project}' not found[/red]"); return
    value = None if machine_value == "none" else machine_value
    db.update_project(project_id, machine=value)
    if value:
        console.print(f"[green]Set {project} machine to {value}[/green]")
    else:
        console.print(f"[green]Cleared machine designation for {project}[/green]")


@cli.command()
@click.pass_context
def help(ctx):
    """Show this help message."""
    click.echo(ctx.parent.get_help())


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
@click.option("-m", "--machine", default=None, help="Filter by machine: MacBook, OpenClaw, Both")
def tasks_group(ctx, project, status, show_all, json_output, needs_prompt, ready, machine):
    """Manage Kanban board tasks.

    \b
    Examples:
        ./pt tasks                       # Show open tasks (all projects)
        ./pt tasks -p project-tracker    # Tasks for a specific project
        ./pt tasks -s "In Progress"      # Filter by status
        ./pt tasks --all                 # Include completed tasks
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
    task_list = db.get_tasks(project_id=project_id, status=status, machine=machine)
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
@click.option("-m", "--machine", default=None, help="Filter by machine: MacBook, OpenClaw, Both")
def tasks_list(project, status, show_all, board, json_output, needs_prompt, ready, machine):
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
    task_list = db.get_tasks(project_id=project_id, status=status, machine=machine)
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
@click.option("-d", "--description", default=None, help="Rich description / acceptance criteria (stored in notes field)")
@click.option("--parent", type=int, default=None, help="Parent task ID (creates subtask)")
@click.option("--blocked-by", default=None, help="Comma-separated task IDs that block this task")
@click.option("-m", "--machine", default=None, help="Machine: MacBook, OpenClaw, Both")
def tasks_create(text, project, status, priority, prompt, description, parent, blocked_by, machine):
    """Create a new task. Auto-detects project from current directory."""
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
    if machine:
        from scripts.utils.validation import validate_machine
        is_valid, err = validate_machine(machine)
        if not is_valid:
            console.print(f"[red]{err}[/red]"); return
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
        task = db.add_task(text=text, project_id=project_id, status=status, priority=priority, prompt=final_prompt, parent_id=parent, blocked_by=blocked_by_json, notes=description, machine=machine)
        msg = f"[green]Created task #{task['id']}: {text[:50]}{'...' if len(text) > 50 else ''}[/green]"
        if description: msg += f" [dim](+ description)[/dim]"
        if parent: msg += f" [dim](subtask of #{parent})[/dim]"
        if blocked_by: msg += f" [dim](blocked by {blocked_by})[/dim]"
        console.print(msg)
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
@click.option("-m", "--machine", default=None, help="Machine: MacBook, OpenClaw, Both")
def tasks_update(task_id, status, text, priority, prompt, review_comment, notes, blocked_by, machine):
    """Update an existing task."""
    import json as json_lib
    db = DatabaseManager()
    updates = {}
    if status:
        valid_statuses = ["Backlog", "To Do", "In Progress", "Review", "Done", "Cancelled"]
        if status not in valid_statuses:
            console.print(f"[red]Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}[/red]"); return
        updates["status"] = status
    if text: updates["text"] = text
    if priority:
        if priority not in ["Critical", "High", "Medium", "Low"]:
            console.print(f"[red]Invalid priority '{priority}'[/red]"); return
        updates["priority"] = priority
    if prompt: updates["prompt"] = prompt
    if review_comment is not None: updates["review_comment"] = review_comment
    if notes is not None: updates["notes"] = notes
    if machine:
        from scripts.utils.validation import validate_machine
        is_valid, err = validate_machine(machine)
        if not is_valid:
            console.print(f"[red]{err}[/red]"); return
        updates["machine"] = machine
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
    try:
        db.update_task(task_id, **updates)
        console.print(f"[green]Updated task #{task_id}[/green]")
        for key, value in updates.items():
            console.print(f"  {key}: {value}")
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
            task = db.get_task(task_id)
            if not task: print(f"Task #{task_id} not found"); continue
            old_project = task["project_id"]
            if old_project == target_project_id: print(f"Task #{task_id} already in project '{target_name}'"); continue
            with db._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE tasks SET project_id = ?, updated_at = ? WHERE id = ?", (target_project_id, datetime.now().isoformat(), task_id))
                conn.commit()
            print(f"Moved: #{task_id} from '{old_project}' to '{target_name}'")
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
            task = db.get_task(task_id)
            if not task: print(f"Task #{task_id} not found"); continue
            db.update_task(task_id, status="Done")
            print(f"Done: #{task_id} - {task['text'][:50]}")
            success_count += 1
        except Exception as e:
            print(f"Failed to complete task #{task_id}: {e}")
    if len(task_ids) > 1: print(f"\nCompleted {success_count}/{len(task_ids)} tasks")


@tasks_group.command(name="start")
@click.argument("task_ids", type=int, nargs=-1, required=True)
def tasks_start(task_ids):
    """Move one or more tasks to In Progress."""
    db = DatabaseManager()
    success_count = 0
    for task_id in task_ids:
        try:
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
            task = db.get_task(task_id)
            if not task: print(f"Task #{task_id} not found"); continue
            db.update_task(task_id, status="Review")
            print(f"Review: #{task_id} - {task['text'][:50]}")
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
            task = db.get_task(task_id)
            if not task: print(f"Task #{task_id} not found"); continue
            db.update_task(task_id, status="Cancelled")
            print(f"Cancelled: #{task_id} - {task['text'][:50]}")
            success_count += 1
        except Exception as e:
            print(f"Failed to cancel task #{task_id}: {e}")
    if len(task_ids) > 1: print(f"\nCancelled {success_count}/{len(task_ids)} tasks")


@tasks_group.command(name="delete")
@click.argument("task_id", type=int)
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation")
def tasks_delete(task_id, yes):
    """Permanently delete a single task (one at a time for safety)."""
    db = DatabaseManager()
    task = db.get_task(task_id)
    if not task: print(f"Task #{task_id} not found"); return
    print(f"  #{task['id']} | {task['status']} | {task['text'][:60]}")
    if not yes:
        confirm = click.confirm(f"\nPermanently delete task #{task_id}?", default=False)
        if not confirm: print("Cancelled"); return
    try:
        db.delete_task(task_id)
        print(f"Deleted: #{task_id}")
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
            task = db.get_task(task_id)
            if not task:
                if not json_output: console.print(f"[red]Task #{task_id} not found[/red]")
                continue
            if json_output:
                tasks.append(task)
            else:
                if i > 0: print("\n" + "-" * 40 + "\n")
                print(f"Task #{task['id']}")
                print(f"Project: {task['project_id']}")
                print(f"Status: {task['status']}")
                print(f"Priority: {task.get('priority') or 'None'}")
                is_blocked, blocking_ids = db.is_blocked(task['id'])
                if is_blocked: print(f"Blocked by: {', '.join(f'#{tid}' for tid in blocking_ids)} (incomplete)")
                elif task.get('blocked_by'): print(f"Blocked by: (all resolved)")
                print(f"Created: {task['created_at']}")
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
    ctx.invoke(inbox_list)


@inbox_group.command(name="list")
def inbox_list():
    """List all inbox notes."""
    data = _load_inbox()
    notes = data.get("notes", [])
    if not notes: console.print("[dim]Inbox is empty[/dim]"); return
    console.print(f"\n[bold]Inbox ({len(notes)} notes)[/bold]\n")
    for note in notes:
        console.print(f"  [cyan]#{note['id']}[/cyan] {note['text']}")
    console.print()


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
            machine_str = f" | {ev['machine']}" if ev.get("machine") else ""
            project_str = f" | {ev['project_id']}" if ev.get("project_id") else ""
            prompt_marker = " [prompt]" if ev.get("prompt") else ""
            print(f"#{ev['id']} | {ev['event_date']}{time_str} | {ev['event_type']} | {ev['status']}{machine_str}{project_str}{prompt_marker} | {ev['title']}")
        print(f"\nEvents: {len(events)}")
    if cron_jobs:
        print(f"\n── Cron Jobs ──")
        for cj in cron_jobs:
            machine_str = f" | {cj['machine']}" if cj.get("machine") else " | machine:?"
            desc_str = f" | {cj['description']}" if cj.get("description") else ""
            print(f"  cron/{cj['id']} | {cj['schedule']}{machine_str} | {cj['project_id']}{desc_str} | {cj['command']}")
        print(f"\nCron jobs: {len(cron_jobs)}")


@click.group(name="calendar", invoke_without_command=True)
@click.pass_context
@click.option("--days", default=7, type=int, help="Days ahead to show (default: 7)")
@click.option("-p", "--project", default=None, help="Filter by project")
@click.option("-m", "--machine", default=None, help="Filter by machine: MacBook, OpenClaw, Both")
@click.option("-t", "--type", "event_type", default=None, help="Filter by type: reminder, deadline, milestone, meeting")
@click.option("--all", "show_all", is_flag=True, help="Show all events (no date window)")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def calendar_group(ctx, days, project, machine, event_type, show_all, json_output):
    """Manage the AI-first calendar.

    \b
    Examples:
        ./pt calendar                        # Upcoming 7 days
        ./pt calendar --days 30              # Next 30 days
        ./pt calendar -p ai-memory-replay    # Filter by project
        ./pt calendar --machine MacBook      # Filter by machine
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
        machine=machine,
        event_type=event_type,
        include_all=show_all,
    )
    cron_jobs = cm.get_cron_jobs(project_id=project_id, machine=machine)
    _display_events(events, json_output=json_output, cron_jobs=cron_jobs)


@calendar_group.command(name="list")
@click.option("--days", default=7, type=int, help="Days ahead to show (default: 7)")
@click.option("-p", "--project", default=None, help="Filter by project")
@click.option("-m", "--machine", default=None, help="Filter by machine")
@click.option("-t", "--type", "event_type", default=None, help="Filter by event type")
@click.option("--all", "show_all", is_flag=True, help="Show all events ignoring date window")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def calendar_list(days, project, machine, event_type, show_all, json_output):
    """List upcoming calendar events and active cron jobs."""
    db = DatabaseManager()
    project_id = _resolve_project_id(db, project) if project else None
    cm = _get_calendar_manager()
    events = cm.get_events(
        days=days, project_id=project_id, machine=machine,
        event_type=event_type, include_all=show_all,
    )
    cron_jobs = cm.get_cron_jobs(project_id=project_id, machine=machine)
    _display_events(events, json_output=json_output, cron_jobs=cron_jobs)


@calendar_group.command(name="crons")
@click.option("-p", "--project", default=None, help="Filter by project")
@click.option("-m", "--machine", default=None, help="Filter by machine: MacBook, OpenClaw, Both, web")
@click.option("--all", "show_all", is_flag=True, help="Include inactive cron jobs")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def calendar_crons(project, machine, show_all, json_output):
    """List all cron jobs with their machine designations.

    \b
    Examples:
        ./pt calendar crons
        ./pt calendar crons --machine MacBook
        ./pt calendar crons -p project-tracker --json
    """
    import json as json_lib
    db = DatabaseManager()
    project_id = _resolve_project_id(db, project) if project else None
    cm = _get_calendar_manager()
    cron_jobs = cm.get_cron_jobs(
        project_id=project_id, machine=machine, active_only=not show_all
    )
    if json_output:
        print(json_lib.dumps({"cron_jobs": cron_jobs, "total": len(cron_jobs)}, indent=2))
        return
    if not cron_jobs:
        print("No cron jobs found.")
        return
    print("Cron Jobs\n")
    for cj in cron_jobs:
        machine_str = f" | {cj['machine']}" if cj.get("machine") else " | machine:?"
        desc_str = f" | {cj['description']}" if cj.get("description") else ""
        active_str = "" if cj.get("is_active", 1) else " [inactive]"
        print(f"  cron/{cj['id']} | {cj['schedule']}{machine_str} | {cj['project_id']}{desc_str}{active_str}")
        print(f"    {cj['command']}")
    print(f"\nTotal: {len(cron_jobs)} cron job(s)")


@calendar_group.command(name="add-cron")
@click.argument("project")
@click.argument("schedule")
@click.argument("command")
@click.option("--description", default="", help="What this cron job does")
@click.option("-m", "--machine", default=None,
              type=click.Choice(["MacBook", "OpenClaw", "Both", "web"]),
              help="Which machine runs this job")
def calendar_add_cron(project, schedule, command, description, machine):
    """Add a cron job from the calendar (with machine designation).

    \b
    Examples:
        ./pt calendar add-cron project-tracker "*/15 * * * *" "./pt calendar remind --json" \\
            --machine MacBook --description "Agent reminder poller"
        ./pt calendar add-cron ai-memory-replay "0 9 * * 1" "bash scripts/render_replay.sh" \\
            --machine MacBook --description "Weekly brain replay render"
    """
    from datetime import datetime, timezone as _tz
    db = DatabaseManager()
    project_id = _resolve_project_id(db, project)
    if not project_id:
        console.print(f"[red]Project '{project}' not found[/red]"); return

    cm = _get_calendar_manager()
    # Insert directly so we can capture lastrowid atomically — avoids duplicate-command race
    with cm._conn() as conn:
        cursor = conn.execute(
            """INSERT INTO cron_jobs (project_id, schedule, command, description, machine, is_active)
               VALUES (?, ?, ?, ?, ?, 1)""",
            (project_id, schedule, command, description or None, machine),
        )
        conn.commit()
        new_id = cursor.lastrowid

    machine_note = f" on {machine}" if machine else ""
    console.print(f"[green]✅ Added cron job #{new_id} to {project}{machine_note}[/green]")
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
@click.option("-m", "--machine", default=None, help="Machine: MacBook, OpenClaw, Both")
@click.option("--prompt", default=None, help="Agent instructions when event fires")
@click.option("--description", default=None, help="Human-readable description")
@click.option("--notify", "notify_before_minutes", default=60, type=int,
              help="Minutes before to notify (default: 60)")
@click.option("--recurrence", default=None,
              type=click.Choice(["daily", "weekly", "monthly"]),
              help="Recurrence pattern")
@click.option("--json", "json_output", is_flag=True, help="Output new event as JSON")
def calendar_add(title, event_date, event_time, event_type, project, machine,
                 prompt, description, notify_before_minutes, recurrence, json_output):
    """Add a calendar event.

    \b
    Examples:
        ./pt calendar add "Ship v2" --date 2026-03-28 --type milestone
        ./pt calendar add "Weekly review" --date 2026-03-25 --time 10:00 --recurrence weekly
        ./pt calendar add "Check cards" --date 2026-03-24 --prompt "Review all In Progress cards" --machine Both
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
            machine=machine,
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
    if event.get("machine"):       console.print(f"Machine: {event['machine']}")
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
@click.option("-m", "--machine", default=None)
@click.option("--prompt", default=None)
@click.option("--description", default=None)
@click.option("--notify", "notify_before_minutes", default=None, type=int)
def calendar_update(event_id, title, event_date, event_time, event_type, project,
                    machine, prompt, description, notify_before_minutes):
    """Update any fields on a calendar event."""
    db = DatabaseManager()
    cm = _get_calendar_manager()
    updates = {}
    if title is not None:                 updates["title"] = title
    if event_date is not None:            updates["event_date"] = event_date
    if event_time is not None:            updates["event_time"] = event_time
    if event_type is not None:            updates["event_type"] = event_type
    if machine is not None:               updates["machine"] = machine
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
@click.option("-m", "--machine", default=None, help="Filter by machine")
@click.option("--dry-run", is_flag=True, help="Print what would fire without marking as notified")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON (for cron/agent polling)")
def calendar_remind(within_minutes, machine, dry_run, json_output):
    """Show events firing soon — designed for cron/agent polling.

    \b
    Run every 15 min:
        */15 * * * * cd ~/projects/project-tracker && \\
          doppler run -- ./pt calendar remind --machine MacBook --json
    """
    import json as json_lib
    cm = _get_calendar_manager()
    events = cm.get_upcoming_reminders(within_minutes=within_minutes, machine=machine)
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
@click.option("--ical", is_flag=True, help="Export as iCal (.ics) format")
@click.option("-o", "--output", default=None, help="Output file path (default: stdout)")
@click.option("-p", "--project", default=None, help="Filter by project")
@click.option("-m", "--machine", default=None, help="Filter by machine")
def calendar_export(ical, output, project, machine):
    """Export calendar events.

    \b
    Example:
        ./pt calendar export --ical -o ~/Desktop/pt-calendar.ics
    """
    db = DatabaseManager()
    project_id = _resolve_project_id(db, project) if project else None
    cm = _get_calendar_manager()

    if ical:
        content = cm.export_ical(project_id=project_id, machine=machine, include_all=True)
        if output:
            Path(output).write_text(content)
            console.print(f"[green]✅ Exported to {output}[/green]")
        else:
            print(content)
    else:
        console.print("[yellow]Specify --ical for iCal export format[/yellow]")




@calendar_group.command(name="poll")
@click.option("-m", "--machine", default=None, help="Machine to filter events for (default: auto-detect)")
@click.option("--within", "within_minutes", default=60, type=int,
              help="Notify events firing within this many minutes (default: 60)")
@click.option("--dry-run", is_flag=True, help="Show what would fire without marking as notified or writing to brain")
@click.option("--quiet", is_flag=True, help="Suppress human-readable output")
@click.option("--json", "as_json", is_flag=True, help="Output results as JSON")
def calendar_poll(machine, within_minutes, dry_run, quiet, as_json):
    """Run one calendar poll cycle — fire events, write to brain, run agent prompts.

    \b
    Designed to be run every 5-15 minutes via cron. Use install-poll-cron to
    set that up automatically.

    \b
    Examples:
        ./pt calendar poll                          # auto-detect machine, 60 min window
        ./pt calendar poll --machine MacBook        # explicit machine filter
        ./pt calendar poll --within 15 --dry-run    # preview without side effects
        ./pt calendar poll --json                   # structured output for agents
    """
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.hooks.calendar_poller import poll as _poll
    results = _poll(
        machine=machine,
        within_minutes=within_minutes,
        dry_run=dry_run,
        quiet=quiet,
        as_json=as_json,
    )
    if results.get("errors"):
        raise SystemExit(1)


@calendar_group.command(name="install-poll-cron")
@click.option("--interval", default=10, type=int, help="Run every N minutes (default: 10)")
@click.option("-m", "--machine", default=None,
              type=click.Choice(["MacBook", "OpenClaw", "Both", "web"]),
              help="Machine to filter events for in the cron job")
@click.option("--within", "within_minutes", default=60, type=int,
              help="Notify events firing within N minutes (default: 60)")
@click.option("--remove", is_flag=True, help="Remove the poller cron job instead of installing")
@click.option("--dry-run", is_flag=True, help="Print the crontab line without installing it")
def calendar_install_poll_cron(interval, machine, within_minutes, remove, dry_run):
    """Install (or remove) the calendar_poller cron job in the current user's crontab.

    \b
    Installs a sentinel-tagged crontab line that runs the calendar poller every
    N minutes using uv run. Output appended to data/logs/poller.log.

    \b
    Examples:
        ./pt calendar install-poll-cron                          # every 10 min, auto-detect machine
        ./pt calendar install-poll-cron --machine MacBook        # explicit machine
        ./pt calendar install-poll-cron --interval 5 --within 15
        ./pt calendar install-poll-cron --remove                 # uninstall
        ./pt calendar install-poll-cron --dry-run                # preview
    """
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.hooks.cron_installer import install as _install

    result = _install(
        interval=interval,
        machine=machine,
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
    console.print(f"   Machine  : {result['machine'] or 'auto-detect'}")
    console.print(f"   Log      : {result['log_path']}")
    if result["previous_lines_removed"]:
        console.print(f"   Replaced : {result['previous_lines_removed']} old poller line(s)")
    console.print(f"\n   Crontab entry:")
    console.print(f"   [dim]{result['line']}[/dim]")

# =============================================================================
# Memory group — wraps ai-memory/brain.py for cross-agent semantic memory
# =============================================================================

BRAIN_PY_PATH = PROJECTS_BASE_DIR / "ai-memory" / "brain.py"


def _run_brain(*args: str) -> None:
    """Call brain.py via uv run, streaming output directly to the terminal."""
    if not BRAIN_PY_PATH.exists():
        raise click.ClickException(
            f"brain.py not found at {BRAIN_PY_PATH}. "
            "Is PROJECTS_ROOT set correctly and is ai-memory cloned?"
        )
    subprocess.run(
        ["uv", "run", str(BRAIN_PY_PATH), *args],
        check=False,
        cwd=str(BRAIN_PY_PATH.parent),
    )


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
@click.argument("query")
@click.option("--top", "-n", default=5, type=int, help="Number of results (default: 5)")
@click.option("--agent-family", "-a", default="",
              help="Filter to agent family: claude | gemini | codex | antigravity | qwen")
@click.option("--namespace", default="", help="Filter by project prefix (e.g. loop/sales)")
@click.option("--goal-id", default="", help="Filter to loop_state entries for a specific goal ID")
def memory_search(query: str, top: int, agent_family: str, namespace: str, goal_id: str) -> None:
    """Search the shared brain by semantic similarity.

    \b
    Examples:
      pt memory search "what was the Turso decision?"
      pt memory search "MCP firewall" --top 10
      pt memory search "calendar" --agent-family claude
    """
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
    args = ["write", content, "--type", entry_type]
    if project:
        args += ["--project", project]
    if agent_family:
        args += ["--agent-family", agent_family]
    if scope:
        args += ["--scope", scope]
    _run_brain(*args)


@memory_group.command(name="stats")
def memory_stats() -> None:
    """Show brain database statistics and per-agent search efficiency."""
    _run_brain("stats")


# =============================================================================
# Register subgroups and run
# =============================================================================

cli.add_command(tasks_group)
cli.add_command(inbox_group)
cli.add_command(calendar_group)
cli.add_command(memory_group)

if __name__ == "__main__":
    cli()
