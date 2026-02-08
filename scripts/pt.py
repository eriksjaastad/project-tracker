#!/usr/bin/env python3
"""
Project Tracker CLI - Track all your projects in one place.

🚀 How to Use:
--------------
1. Activate Virtual Environment (Erik, do this first!):
   source venv/bin/activate

2. Run with Launcher (easiest):
   ./pt [command]

3. Run with Python directly:
   python scripts/pt.py [command]

Common Commands:
- ./pt scan      # Scan for new projects and rebuild graph
- ./pt launch    # Start the web dashboard
- ./pt list      # List all projects in terminal
"""

import sys
import webbrowser
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Annotated
import subprocess

import typer
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

app = typer.Typer(
    name="pt",
    help="Project Tracker - Manage and track all your projects",
    add_completion=False,
    rich_markup_mode=None,
    pretty_exceptions_show_locals=False
)
console = Console()


def compare_versions(v1: str | None, v2: str | None) -> int:
    """Compare semantic versions. Returns: -1 if v1 < v2, 0 if equal, 1 if v1 > v2.
    
    None is treated as oldest version (below any actual version).
    """
    if v1 is None and v2 is None:
        return 0
    if v1 is None:
        return -1
    if v2 is None:
        return 1
    
    # Try semantic version parsing
    try:
        parts1 = [int(x) for x in v1.split('.')]
        parts2 = [int(x) for x in v2.split('.')]
        
        # Pad to same length
        while len(parts1) < len(parts2):
            parts1.append(0)
        while len(parts2) < len(parts1):
            parts2.append(0)
        
        for p1, p2 in zip(parts1, parts2):
            if p1 < p2:
                return -1
            elif p1 > p2:
                return 1
        return 0
    except (ValueError, AttributeError):
        # Fall back to string comparison
        return -1 if v1 < v2 else (1 if v1 > v2 else 0)


def get_current_scaffolding_version() -> tuple[str | None, str | None]:
    """Get current scaffolding version from project-scaffolding/.scaffolding-version."""
    import json
    version_file = Path(PROJECTS_BASE_DIR) / "project-scaffolding" / ".scaffolding-version"
    if not version_file.exists():
        return None, None
    try:
        data = json.loads(version_file.read_text())
        return data.get("scaffolding_version"), data.get("rules_version")
    except Exception:
        return None, None


@app.command()
def init():
    """Initialize the project tracker database."""
    console.print("[bold green]Initializing project tracker...[/bold green]")
    db_path = init_db()
    console.print(f"✅ Database created at: {db_path}")


def rebuild_knowledge_graph():
    """Run the knowledge graph builder."""
    console.print("[bold blue]Rebuilding knowledge graph & analysis...[/bold blue]")
    try:
        root_path = Path(PROJECTS_BASE_DIR)
        output_path = Path(__file__).parent.parent / "data" / "graph.json"
        analysis_path = Path(__file__).parent.parent / "data" / "graph_analysis.md"
        ecosystem_todo = root_path / "TODO.md"
        
        # 1. Run Librarian to network all projects
        console.print("[bold cyan]  → Running Librarian (Networking projects)...[/bold cyan]")
        for item in root_path.iterdir():
            if item.is_dir() and not item.name.startswith(".") and item.name not in ["node_modules", "venv", ".venv", "_trash", "_inbox", "trash"]:
                update_directory_index(item, recursive=True)
        
        # 2. Run Graph Builder
        builder = GraphBuilder(root_path)
        builder.scan()
        builder.save(output_path)
        
        # Save analysis
        analysis_text = builder.generate_analysis()
        analysis_path.write_text(analysis_text)
        
        # Update ecosystem TODO if it exists
        if ecosystem_todo.exists():
            builder.update_todo(ecosystem_todo)
            
        console.print(f"  ✓ Knowledge graph & analysis updated")

        # Run Journal Specialist
        console.print("[bold cyan]  → Running Journal Specialist (Enriching links)...[/bold cyan]")
        specialist = JournalSpecialist()
        specialist.scan()
        
    except Exception as e:
        console.print(f"  [red]✗ Error rebuilding knowledge graph: {e}[/red]")


def scan(
    no_graph: bool = False,
    dry_run: bool = False,
    force: bool = False
):
    """Scan projects directory and update database."""
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

    # Discover projects
    with Progress() as progress:
        task = progress.add_task("[cyan]Discovering projects...", total=None)
        projects = discover_projects(PROJECTS_BASE_DIR, sync_indexes=not dry_run)
        progress.update(task, completed=True)

    console.print(f"\n[green]Found {len(projects)} projects[/green]\n")

    existing_projects = db.get_all_projects() if db_exists else []
    existing_count = len(existing_projects)

    # Warn on empty or steeply reduced results
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

    # Run health checks in parallel
    if dry_run:
        console.print("[dim]Dry-run: skipping health checks and database writes.[/dim]")
        return

    with Progress() as progress:
        task = progress.add_task("[cyan]Auditing project health...", total=len(projects))
        health_results = scan_health_parallel(projects)
        progress.update(task, advance=len(projects))

    # Get current project IDs in database
    existing_ids = {p["id"] for p in existing_projects}
    discovered_ids = {p["id"] for p in projects}
    
    # NOTE: We intentionally do NOT delete projects that are no longer found.
    # Projects may be temporarily unavailable (unmounted drives, renamed folders).
    # Deleting a project cascades to delete ALL tasks - too dangerous for auto-cleanup.
    # Use explicit `./pt remove <project>` command if needed (to be implemented).
    stale_ids = existing_ids - discovered_ids
    if stale_ids:
        console.print(f"  [dim]ℹ {len(stale_ids)} projects not found in scan (preserved in DB)[/dim]")

    # Parse services from EXTERNAL_RESOURCES.md
    console.print(f"\n[bold blue]Loading services from EXTERNAL_RESOURCES.md...[/bold blue]")
    services_by_project = parse_external_resources()

    # Update database
    hygiene_fixes = 0
    for project in projects:
        # Run hygiene check/fix
        todo_path = Path(project["path"]) / "TODO.md"
        if todo_path.exists():
            fixes = fix_hygiene_issues(todo_path)
            if fixes > 0:
                hygiene_fixes += fixes
                # Re-parse metadata if we fixed something
                from discovery.project_scanner import extract_project_metadata
                project.update(extract_project_metadata(Path(project["path"])))

        # Per-project transaction boundary
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
                    scaffolding_version=project.get("scaffolding_version"),
                    rules_version=project.get("rules_version"),
                    scaffolding_applied_at=project.get("scaffolding_applied_at")
                )

                db._sync_ai_agents_with_cursor(
                    cursor=cursor,
                    project_id=project["id"],
                    agents=project.get("ai_agents", [])
                )

                db._sync_cron_jobs_with_cursor(
                    cursor=cursor,
                    project_id=project["id"],
                    cron_jobs=project.get("cron_jobs", [])
                )

                db._sync_services_with_cursor(
                    cursor=cursor,
                    project_id=project["id"],
                    services=services_by_project.get(project["id"], [])
                )

                # Update health if available
                health = health_results.get(project["id"])
                if health:
                    db._update_health_with_cursor(
                        cursor=cursor,
                        project_id=project["id"],
                        score=health["score"],
                        grade=health["grade"]
                    )

                conn.commit()
                console.print(f"  ✓ {project['name']}")
            except Exception as e:
                conn.rollback()
                console.print(f"  [red]✗ Failed to update {project['name']}: {e}[/red]")
                continue

    # Report skipped services for unknown projects
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
    
    # Rebuild knowledge graph
    if not no_graph:
        console.print("")
        rebuild_knowledge_graph()
    
    console.print(f"\n[bold green]✅ Scan complete! {len(projects)} projects updated[/bold green]")


@app.command(name="list")
def list_projects(
    outdated: bool = typer.Option(False, "--outdated", help="Show only projects with outdated scaffolding")
):
    """List all projects. AI-first: plain print(), no terminal width constraints."""
    db = DatabaseManager()
    projects = db.get_all_projects()

    if not projects:
        print("No projects found. Run 'pt scan' first.")
        return
    
    # Filter for outdated if requested
    if outdated:
        current_scaffolding, current_rules = get_current_scaffolding_version()
        filtered_projects = []
        for p in projects:
            project_version = p.get("scaffolding_version")
            # Include if: no version (never scaffolded) OR version is older than current
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
        # Format index status
        idx = "✓" if project.get("has_index") and project.get("index_is_valid") else "!"
        phase = project.get("phase") or "-"
        pct = project.get("completion_pct", 0)
        
        # Add version info if available
        version_info = ""
        if "scaffolding_version" in project:
            if project["scaffolding_version"]:
                version_info = f" | v{project['scaffolding_version']}"
            else:
                version_info = " | no scaffolding"

        print(f"{project['name']} | {project['status']} | {phase} | {pct}% | {idx}{version_info}")

    print(f"\nTotal: {len(projects)} projects")


@app.command()
def status(name: str):
    """Show detailed status for a project."""
    db = DatabaseManager()
    
    # Find project by name
    projects = db.get_all_projects()
    project = None
    for p in projects:
        if p["name"].lower() == name.lower():
            project = p
            break
    
    if not project:
        console.print(f"[red]Project '{name}' not found[/red]")
        return
    
    # Display project info
    console.print(f"\n[bold cyan]{project['name']}[/bold cyan]")
    console.print(f"Path: {project['path']}")
    console.print(f"Status: [green]{project['status']}[/green]")
    if project.get("phase"):
        console.print(f"Phase: {project['phase']}")
    console.print(f"Progress: {project.get('completion_pct', 0)}%")
    console.print(f"Last Modified: {project.get('last_modified', 'unknown')}")
    
    if project.get("description"):
        console.print(f"\n{project['description']}")
    
    # Show AI agents
    agents = db.get_ai_agents(project["id"])
    if agents:
        console.print("\n[bold]AI Agents:[/bold]")
        for agent in agents:
            role = f" - {agent['role']}" if agent.get('role') else ""
            console.print(f"  • {agent['agent_name']}{role}")
    
    # Show cron jobs
    jobs = db.get_cron_jobs(project["id"])
    if jobs:
        console.print("\n[bold]Cron Jobs:[/bold]")
        for job in jobs:
            console.print(f"  • {job['schedule']}: {job['command']}")
    
    # Show services
    services = db.get_services(project["id"])
    if services:
        console.print("\n[bold]Services:[/bold]")
        for service in services:
            cost = f" (${service['cost_monthly']}/mo)" if service.get('cost_monthly') else ""
            console.print(f"  • {service['service_name']}{cost}")
    
    console.print()


@app.command()
def refresh():
    """Refresh all project metadata."""
    console.print("[bold blue]Refreshing project data...[/bold blue]")
    scan()


@app.command()
def hygiene(fix: bool = typer.Option(False, "--fix", help="Apply fixes automatically")):
    """Check all projects for TODO.md hygiene issues."""
    console.print("[bold blue]Checking project hygiene...[/bold blue]")
    projects = discover_projects(PROJECTS_BASE_DIR)
    
    total_issues = 0
    total_fixes = 0
    
    for p in projects:
        todo_path = Path(p["path"]) / "TODO.md"
        if not todo_path.exists():
            continue
            
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
    else:
        if fix:
            console.print(f"\n[bold green]✅ Applied {total_fixes} total fixes across {total_issues} issues.[/bold green]")
        else:
            console.print(f"\n[bold yellow]⚠ Found {total_issues} total issues. Run 'pt hygiene --fix' to resolve.[/bold yellow]")


@app.command()
def launch(
    port: int = 8000,
    no_scan: bool = typer.Option(False, "--no-scan", help="Skip the initial project scan on launch"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development")
):
    """Launch the web dashboard."""
    no_browser = False
    console.print("[bold green]🚀 Launching Project Tracker Dashboard...[/bold green]\n")
    
    # Ensure database exists
    init_db()
    
    # Run scan to ensure data is fresh (unless skipped)
    if not no_scan:
        console.print("[dim]Running quick scan...[/dim]")
        scan()
    else:
        console.print("[yellow]Skipping initial scan. Using existing data.[/yellow]")
    
    # Start web server
    dashboard_path = Path(__file__).parent.parent / "dashboard" / "app.py"
    
    if not dashboard_path.exists():
        console.print("[red]Error: Dashboard not found. Check installation.[/red]")
        return
    
    url = f"http://localhost:{port}"
    console.print(f"\n[bold green]✅ Dashboard starting at {url}[/bold green]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")
    
    # Open browser after a short delay
    if not no_browser:
        def open_browser():
            time.sleep(2)
            webbrowser.open(url)
        
        import threading
        threading.Thread(target=open_browser, daemon=True).start()
    
    # Start uvicorn
    venv_python = Path(__file__).parent.parent / "venv" / "bin" / "python"
    
    cmd = [
        str(venv_python), "-m", "uvicorn",
        "dashboard.app:app",
        "--host", "0.0.0.0",
        "--port", str(port)
    ]
    
    if reload:
        cmd.append("--reload")
        
    try:
        subprocess.run(cmd, cwd=Path(__file__).parent.parent)
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Dashboard stopped[/yellow]")


# Additional commands for managing specific metadata

@app.command()
def add_agent(project: str, agent_name: str, role: str = ""):
    """Add an AI agent to a project."""
    db = DatabaseManager()
    
    # Find project
    projects = db.get_all_projects()
    project_id = None
    for p in projects:
        if p["name"].lower() == project.lower():
            project_id = p["id"]
            break
    
    if not project_id:
        console.print(f"[red]Project '{project}' not found[/red]")
        return
    
    db.add_ai_agent(project_id, agent_name, role)
    console.print(f"[green]✅ Added AI agent '{agent_name}' to {project}[/green]")


@app.command()
def add_cron(project: str, schedule: str, command: str, description: str = ""):
    """Add a cron job to a project."""
    db = DatabaseManager()
    
    # Find project
    projects = db.get_all_projects()
    project_id = None
    for p in projects:
        if p["name"].lower() == project.lower():
            project_id = p["id"]
            break
    
    if not project_id:
        console.print(f"[red]Project '{project}' not found[/red]")
        return
    
    db.add_cron_job(project_id, schedule, command, description)
    console.print(f"[green]✅ Added cron job to {project}[/green]")


@app.command()
def add_service(project: str, service_name: str, cost: float = 0, purpose: str = ""):
    """Add a service dependency to a project."""
    db = DatabaseManager()

    # Find project
    projects = db.get_all_projects()
    project_id = None
    for p in projects:
        if p["name"].lower() == project.lower():
            project_id = p["id"]
            break

    if not project_id:
        console.print(f"[red]Project '{project}' not found[/red]")
        return

    db.add_service(project_id, service_name, purpose, cost)
    console.print(f"[green]✅ Added service '{service_name}' to {project}[/green]")


# -----------------------------------------------------------------------------
# Tasks CLI (Pure Click for Python 3.14 compatibility)
# -----------------------------------------------------------------------------

import click


@click.command(name="scan")
@click.option("--no-graph", is_flag=True, help="Skip rebuilding the knowledge graph")
@click.option("--dry-run", is_flag=True, help="Show what would change without writing")
@click.option("--force", is_flag=True, help="Proceed even if scan results look unsafe")
def scan_cli(no_graph: bool, dry_run: bool, force: bool):
    """Scan projects directory and update database (Click wrapper)."""
    scan(no_graph=no_graph, dry_run=dry_run, force=force)


def _has_complete_prompt(prompt: str | None) -> bool:
    """Check if a prompt has all three required sections."""
    if not prompt:
        return False
    prompt_lower = prompt.lower()
    return (
        "## overview" in prompt_lower and
        "## execution" in prompt_lower and
        "## done criteria" in prompt_lower
    )


def _display_tasks(task_list: list, project: str | None = None, json_output: bool = False, db: "DatabaseManager | None" = None):
    """Display tasks. AI-first: plain print(), no terminal width constraints."""
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

        # Prompt marker: highlight MISSING or INCOMPLETE prompts (problems stand out)
        if _has_complete_prompt(task.get("prompt")):
            prompt_marker = ""
        elif task.get("prompt"):
            prompt_marker = "[~P] "
        else:
            prompt_marker = "[!P] "

        # [B] marker if task is blocked by incomplete tasks
        blocked_marker = ""
        if db and task.get("blocked_by"):
            is_blocked, blocking_ids = db.is_blocked(task_id)
            if is_blocked:
                blocked_marker = f"[B:{','.join(str(i) for i in blocking_ids)}] "

        # Plain print - no terminal width wrapping
        if project:
            print(f"#{task_id} {prompt_marker}{blocked_marker}| {status} | {priority} | {task_text}")
        else:
            print(f"#{task_id} {prompt_marker}{blocked_marker}| {task['project_id']} | {status} | {priority} | {task_text}")

    # Summary
    status_counts = {}
    for task in task_list:
        status_counts[task["status"]] = status_counts.get(task["status"], 0) + 1

    summary_parts = [f"{s}: {status_counts[s]}" for s in ["Backlog", "To Do", "In Progress", "Review", "Done", "Cancelled"] if s in status_counts]
    print(f"\nTotal: {len(task_list)} tasks ({', '.join(summary_parts)})")


def _resolve_project_id(db: DatabaseManager, project: str | None) -> str | None:
    """Resolve project name to project_id, returns None if not found or not specified."""
    if not project:
        return None
    projects = db.get_all_projects()
    for p in projects:
        if p["name"].lower() == project.lower() or p["id"].lower() == project.lower():
            return p["id"]
    return None


def _detect_project_from_cwd(db: DatabaseManager) -> str | None:
    """Auto-detect project from current working directory. AI-first: no flags needed."""
    import os
    cwd = os.getcwd()
    dir_name = os.path.basename(cwd)
    # Check if current directory name matches a known project
    return _resolve_project_id(db, dir_name)


@click.group(name="tasks", invoke_without_command=True)
@click.pass_context
@click.option("-p", "--project", default=None, help="Filter by project name or ID")
@click.option("-s", "--status", default=None, help="Filter by status (Backlog, To Do, In Progress, Review, Done)")
@click.option("-a", "--all", "show_all", is_flag=True, help="Include completed tasks")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.option("--needs-prompt", is_flag=True, help="Show only tasks without prompts")
@click.option("--ready", is_flag=True, help="Show To Do tasks with complete prompts (ready to start)")
def tasks_group(ctx, project, status, show_all, json_output, needs_prompt, ready):
    """Manage Kanban board tasks.

    \b
    Examples:
        ./pt tasks                       # Show open tasks (all projects)
        ./pt tasks -p project-tracker    # Tasks for a specific project
        ./pt tasks -s "In Progress"      # Filter by status
        ./pt tasks --all                 # Include completed tasks
        ./pt tasks --needs-prompt        # Show tasks that need prompts
        ./pt tasks --ready               # Show tasks ready to start
        ./pt tasks create "Fix bug" -p myproject
    """
    # If a subcommand is invoked, don't run the default list behavior
    if ctx.invoked_subcommand is not None:
        return

    # Default behavior: list tasks
    db = DatabaseManager()
    if project:
        project_id = _resolve_project_id(db, project)
        project_label = project
        if not project_id:
            console.print(f"[red]Project '{project}' not found[/red]")
            return
    else:
        project_id = _detect_project_from_cwd(db)
        project_label = None
        if project_id:
            detected = db.get_project(project_id)
            project_label = detected["name"] if detected else None

    task_list = db.get_tasks(project_id=project_id, status=status)

    # Filter out Done and Cancelled unless --all or specific status
    if not show_all and not status:
        task_list = [t for t in task_list if t["status"] not in ("Done", "Cancelled")]

    # Apply filter flags
    if needs_prompt:
        task_list = [t for t in task_list if not t.get("prompt")]
    if ready:
        task_list = [t for t in task_list if t["status"] == "To Do" and _has_complete_prompt(t.get("prompt"))]

    _display_tasks(task_list, project_label, json_output=json_output, db=db)


@tasks_group.command(name="list")
@click.option("-p", "--project", default=None, help="Filter by project name or ID")
@click.option("-s", "--status", default=None, help="Filter by status (Backlog, To Do, In Progress, Review, Done)")
@click.option("-a", "--all", "show_all", is_flag=True, help="Include completed tasks")
@click.option("--board", is_flag=True, help="Show columnar Kanban board view")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.option("--needs-prompt", is_flag=True, help="Show only tasks without prompts")
@click.option("--ready", is_flag=True, help="Show To Do tasks with complete prompts (ready to start)")
def tasks_list(project, status, show_all, board, json_output, needs_prompt, ready):
    """List tasks from the Kanban board."""
    db = DatabaseManager()
    if project:
        project_id = _resolve_project_id(db, project)
        project_label = project
        if not project_id:
            console.print(f"[red]Project '{project}' not found[/red]")
            return
    else:
        project_id = _detect_project_from_cwd(db)
        project_label = None
        if project_id:
            detected = db.get_project(project_id)
            project_label = detected["name"] if detected else None

    task_list = db.get_tasks(project_id=project_id, status=status)

    if not show_all and not status:
        task_list = [t for t in task_list if t["status"] not in ("Done", "Cancelled")]

    # Apply filter flags
    if needs_prompt:
        task_list = [t for t in task_list if not t.get("prompt")]
    if ready:
        task_list = [t for t in task_list if t["status"] == "To Do" and _has_complete_prompt(t.get("prompt"))]

    if board and not json_output:
        statuses = ["Backlog", "To Do", "In Progress", "Review", "Done"]
        table = Table(show_header=True, header_style="bold")
        for col in statuses:
            table.add_column(col, width=20)

        def format_task(task):
            text = task["text"]
            if len(text) > 18:
                text = text[:17] + "..."
            label = f"#{task['id']} {text}"
            priority = task.get("priority")
            color = {
                "Critical": "red",
                "High": "red",
                "Medium": "yellow",
                "Low": "green"
            }.get(priority)
            return f"[{color}]{label}[/]" if color else label

        by_status = {s: [] for s in statuses}
        for task in task_list:
            by_status.get(task["status"], []).append(task)

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
@click.option("-s", "--status", default="Backlog", help="Initial status (default: Backlog; options: Backlog, To Do, In Progress, Review, Done)")
@click.option("--priority", default=None, help="Priority: Critical, High, Medium, Low")
@click.option("--prompt", default=None, help="Agent prompt (execution instructions for AI)")
@click.option("--parent", type=int, default=None, help="Parent task ID (creates subtask)")
@click.option("--blocked-by", default=None, help="Comma-separated task IDs that block this task")
def tasks_create(text, project, status, priority, prompt, parent, blocked_by):
    """Create a new task. Auto-detects project from current directory.

    \b
    Examples:
        ./pt tasks create "Fix login bug"
        ./pt tasks create "Add tests" -p myproject -s "To Do" --priority High
        ./pt tasks create "Refactor auth" --prompt "Overview: ... Execution: ... Done:"
        ./pt tasks create "Subtask" --parent 4645
        ./pt tasks create "Blocked task" --blocked-by "4646,4647"
    """
    import json
    db = DatabaseManager()

    # Auto-detect project from cwd if not specified
    if project:
        project_id = _resolve_project_id(db, project)
    else:
        project_id = _detect_project_from_cwd(db)

    if not project_id:
        if project:
            console.print(f"[red]Project '{project}' not found[/red]")
        else:
            console.print("[red]Could not auto-detect project from current directory. Use -p to specify.[/red]")
        return

    # Validate status
    valid_statuses = ["Backlog", "To Do", "In Progress", "Review", "Done", "Cancelled"]
    if status not in valid_statuses:
        console.print(f"[red]Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}[/red]")
        return

    # Validate priority if provided
    valid_priorities = ["Critical", "High", "Medium", "Low", None]
    if priority and priority not in valid_priorities:
        console.print(f"[red]Invalid priority '{priority}'. Must be one of: Critical, High, Medium, Low[/red]")
        return
    
    # Parse blocked_by
    blocked_by_json = None
    if blocked_by:
        try:
            ids = [int(tid.strip()) for tid in blocked_by.split(",")]
            blocked_by_json = json.dumps(ids)
        except ValueError:
            console.print("[red]Error: blocked-by must be comma-separated task IDs (e.g., '4645,4646')[/red]")
            return

    # Workflow protocol footer - appended to all task prompts
    WORKFLOW_FOOTER = """
---

## Workflow Protocol
- [ ] Start: `./pt tasks start <id>`
- [ ] Complete work
- [ ] Report: "Work complete. Awaiting Conductor sign-off."
- [ ] FORBIDDEN: `./pt tasks done` (Conductor only)"""

    try:
        # Append workflow footer to prompt if prompt exists
        final_prompt = prompt
        if prompt:
            final_prompt = prompt.rstrip() + WORKFLOW_FOOTER

        task = db.add_task(
            text=text,
            project_id=project_id,
            status=status,
            priority=priority,
            prompt=final_prompt,
            parent_id=parent,
            blocked_by=blocked_by_json
        )
        
        # Show created task with parent/blocking info
        msg = f"[green]Created task #{task['id']}: {text[:50]}{'...' if len(text) > 50 else ''}[/green]"
        if parent:
            msg += f" [dim](subtask of #{parent})[/dim]"
        if blocked_by:
            msg += f" [dim](blocked by {blocked_by})[/dim]"
        console.print(msg)
    except Exception as e:
        console.print(f"[red]Failed to create task: {e}[/red]")


@tasks_group.command(name="update")
@click.argument("task_id", type=int)
@click.option("-s", "--status", default=None, help="New status (Backlog, To Do, In Progress, Review, Done)")
@click.option("-t", "--text", default=None, help="New task text")
@click.option("--priority", default=None, help="New priority")
@click.option("--prompt", default=None, help="Agent prompt (execution instructions for AI)")
@click.option("--review-comment", default=None, help="Reviewer feedback when sending back from Review")
@click.option("--notes", default=None, help="Internal notes/comments for the task")
@click.option("--blocked-by", default=None, help="Comma-separated task IDs that block this task (replaces existing, empty string clears)")
def tasks_update(task_id, status, text, priority, prompt, review_comment, notes, blocked_by):
    """Update an existing task.

    \b
    Examples:
        ./pt tasks update 42 -s "In Progress"
        ./pt tasks update 42 -t "Updated description" --priority High
        ./pt tasks update 42 --prompt "Overview: ... Execution: ... Done:"
        ./pt tasks update 42 --notes "Blocked waiting for API changes"
        ./pt tasks update 42 --blocked-by "4645,4646"
        ./pt tasks update 42 --blocked-by ""
    """
    import json as json_lib
    db = DatabaseManager()

    # Build updates dict
    updates = {}
    if status:
        valid_statuses = ["Backlog", "To Do", "In Progress", "Review", "Done", "Cancelled"]
        if status not in valid_statuses:
            console.print(f"[red]Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}[/red]")
            return
        updates["status"] = status
    if text:
        updates["text"] = text
    if priority:
        valid_priorities = ["Critical", "High", "Medium", "Low"]
        if priority not in valid_priorities:
            console.print(f"[red]Invalid priority '{priority}'. Must be one of: {', '.join(valid_priorities)}[/red]")
            return
        updates["priority"] = priority
    if prompt:
        updates["prompt"] = prompt
    if review_comment is not None:
        updates["review_comment"] = review_comment
    if notes is not None:
        updates["notes"] = notes
    if blocked_by is not None:
        if blocked_by == "":
            updates["blocked_by"] = None
        else:
            try:
                ids = [int(tid.strip()) for tid in blocked_by.split(",")]
                updates["blocked_by"] = json_lib.dumps(ids)
            except ValueError:
                console.print("[red]Error: blocked-by must be comma-separated task IDs (e.g., '4645,4646')[/red]")
                return

    if not updates:
        console.print("[yellow]No updates specified. Use -s, -t, --priority, --prompt, --notes, or --blocked-by.[/yellow]")
        return

    try:
        task = db.update_task(task_id, **updates)
        console.print(f"[green]Updated task #{task_id}[/green]")

        # Show what was updated
        for key, value in updates.items():
            console.print(f"  {key}: {value}")
    except Exception as e:
        console.print(f"[red]Failed to update task #{task_id}: {e}[/red]")


@tasks_group.command(name="move")
@click.argument("project", type=str)
@click.argument("task_ids", type=int, nargs=-1, required=True)
def tasks_move(project, task_ids):
    """Reassign one or more tasks to a different project.

    \b
    Examples:
        ./pt tasks move ai-memory 4694
        ./pt tasks move project-tracker 4694 4695 4696
    """
    db = DatabaseManager()
    
    # Validate target project exists
    target_project_id = _resolve_project_id(db, project)
    if not target_project_id:
        console.print(f"[red]Project '{project}' not found[/red]")
        return
    
    target_project = db.get_project(target_project_id)
    target_name = target_project["name"] if target_project else target_project_id
    
    success_count = 0
    for task_id in task_ids:
        try:
            task = db.get_task(task_id)
            if not task:
                print(f"Task #{task_id} not found")
                continue
            
            old_project = task["project_id"]
            if old_project == target_project_id:
                print(f"Task #{task_id} already in project '{target_name}'")
                continue
            
            # Raw SQL is required because DatabaseManager.update_task() has a field
            # whitelist that doesn't include project_id (by design - project moves
            # are a distinct operation from task updates). Consider adding a dedicated
            # move_task() method if this pattern becomes common.
            with db._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE tasks SET project_id = ?, updated_at = ? WHERE id = ?",
                    (target_project_id, datetime.now().isoformat(), task_id)
                )
                conn.commit()
            
            print(f"Moved: #{task_id} from '{old_project}' to '{target_name}'")
            success_count += 1
        except Exception as e:
            print(f"Failed to move task #{task_id}: {e}")
    
    if len(task_ids) > 1:
        print(f"\nMoved {success_count}/{len(task_ids)} tasks to '{target_name}'")


@tasks_group.command(name="done")
@click.argument("task_ids", type=int, nargs=-1, required=True)
def tasks_done(task_ids):
    """Mark one or more tasks as Done.

    \b
    Examples:
        ./pt tasks done 42
        ./pt tasks done 42 43 44
    """
    db = DatabaseManager()
    
    success_count = 0
    for task_id in task_ids:
        try:
            task = db.get_task(task_id)
            if not task:
                print(f"Task #{task_id} not found")
                continue
            db.update_task(task_id, status="Done")
            print(f"Done: #{task_id} - {task['text'][:50]}")
            success_count += 1
        except Exception as e:
            print(f"Failed to complete task #{task_id}: {e}")
    
    if len(task_ids) > 1:
        print(f"\nCompleted {success_count}/{len(task_ids)} tasks")


@tasks_group.command(name="start")
@click.argument("task_ids", type=int, nargs=-1, required=True)
def tasks_start(task_ids):
    """Move one or more tasks to In Progress.

    \b
    Examples:
        ./pt tasks start 42
        ./pt tasks start 42 43 44
    """
    db = DatabaseManager()
    
    success_count = 0
    for task_id in task_ids:
        try:
            task = db.get_task(task_id)
            if not task:
                print(f"Task #{task_id} not found")
                continue

            if not task.get("prompt"):
                console.print(f"[red]❌ Cannot start #{task_id} - no prompt defined[/red]")
                console.print("   [dim]Add a prompt with: pt tasks update <id> --prompt \"...\"[/dim]")
                console.print("   [dim]Or use the Kanban UI to add execution instructions.[/dim]")
                continue
            
            # Check if blocked (Task #4579)
            is_blocked, blocking_ids = db.is_blocked(task_id)
            if is_blocked:
                blocking_str = ", ".join([f"#{bid}" for bid in blocking_ids])
                console.print(f"[red]❌ Cannot start #{task_id} - blocked by: {blocking_str}[/red]")
                console.print(f"   [dim]Complete those tasks first, then try again.[/dim]")
                continue
            
            db.update_task(task_id, status="In Progress")
            print(f"Started: #{task_id} - {task['text'][:50]}")
            success_count += 1
        except Exception as e:
            print(f"Failed to start task #{task_id}: {e}")
    
    if len(task_ids) > 1:
        print(f"\nStarted {success_count}/{len(task_ids)} tasks")


@tasks_group.command(name="review")
@click.argument("task_ids", type=int, nargs=-1, required=True)
def tasks_review(task_ids):
    """Move one or more tasks to Review.

    \b
    Examples:
        ./pt tasks review 42
        ./pt tasks review 42 43 44
    """
    db = DatabaseManager()
    
    success_count = 0
    for task_id in task_ids:
        try:
            task = db.get_task(task_id)
            if not task:
                print(f"Task #{task_id} not found")
                continue
            db.update_task(task_id, status="Review")
            print(f"Review: #{task_id} - {task['text'][:50]}")
            success_count += 1
        except Exception as e:
            print(f"Failed to review task #{task_id}: {e}")
    
    if len(task_ids) > 1:
        print(f"\nReviewed {success_count}/{len(task_ids)} tasks")


@tasks_group.command(name="cancel")
@click.argument("task_ids", type=int, nargs=-1, required=True)
def tasks_cancel(task_ids):
    """Cancel one or more tasks (soft delete - keeps history).

    \b
    Examples:
        ./pt tasks cancel 42
        ./pt tasks cancel 42 43 44
    """
    db = DatabaseManager()
    
    success_count = 0
    for task_id in task_ids:
        try:
            task = db.get_task(task_id)
            if not task:
                print(f"Task #{task_id} not found")
                continue
            db.update_task(task_id, status="Cancelled")
            print(f"Cancelled: #{task_id} - {task['text'][:50]}")
            success_count += 1
        except Exception as e:
            print(f"Failed to cancel task #{task_id}: {e}")
    
    if len(task_ids) > 1:
        print(f"\nCancelled {success_count}/{len(task_ids)} tasks")


@tasks_group.command(name="delete")
@click.argument("task_ids", type=int, nargs=-1, required=True)
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation")
def tasks_delete(task_ids, yes):
    """Permanently delete one or more tasks.

    \b
    Examples:
        ./pt tasks delete 42
        ./pt tasks delete 42 43 44
        ./pt tasks delete 42 -y
    """
    db = DatabaseManager()
    
    # Show what will be deleted
    tasks_to_delete = []
    for task_id in task_ids:
        task = db.get_task(task_id)
        if not task:
            print(f"Task #{task_id} not found")
            continue
        tasks_to_delete.append(task)
        print(f"  #{task['id']} | {task['status']} | {task['text'][:60]}")
    
    if not tasks_to_delete:
        return
    
    if not yes:
        confirm = click.confirm(f"\nPermanently delete {len(tasks_to_delete)} task(s)?", default=False)
        if not confirm:
            print("Cancelled")
            return
    
    success_count = 0
    for task in tasks_to_delete:
        try:
            db.delete_task(task["id"])
            print(f"Deleted: #{task['id']}")
            success_count += 1
        except Exception as e:
            print(f"Failed to delete task #{task['id']}: {e}")
    
    if len(tasks_to_delete) > 1:
        print(f"\nDeleted {success_count}/{len(tasks_to_delete)} tasks")


@tasks_group.command(name="show")
@click.argument("task_ids", type=int, nargs=-1, required=True)
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def tasks_show(task_ids, json_output):
    """Show full details of one or more tasks including prompt.

    \b
    Examples:
        ./pt tasks show 42
        ./pt tasks show 42 43 44
    """
    db = DatabaseManager()
    
    tasks = []
    for i, task_id in enumerate(task_ids):
        try:
            task = db.get_task(task_id)
            if not task:
                if not json_output:
                    console.print(f"[red]Task #{task_id} not found[/red]")
                continue
            
            if json_output:
                tasks.append(task)
            else:
                if i > 0:
                    print("\n" + "-" * 40 + "\n")
                
                # Print task details in plain text (AI-first)
                print(f"Task #{task['id']}")
                print(f"Project: {task['project_id']}")
                print(f"Status: {task['status']}")
                print(f"Priority: {task.get('priority') or 'None'}")

                # Show blocked-by status
                is_blocked, blocking_ids = db.is_blocked(task['id'])
                if is_blocked:
                    print(f"Blocked by: {', '.join(f'#{tid}' for tid in blocking_ids)} (incomplete)")
                elif task.get('blocked_by'):
                    print(f"Blocked by: (all resolved)")

                print(f"Created: {task['created_at']}")
                print(f"Updated: {task['updated_at']}")
                if task.get('completed_at'):
                    print(f"Completed: {task['completed_at']}")
                print()
                print("Description:")
                print(task['text'])

                if task.get('notes'):
                    print()
                    print("Notes:")
                    print(task['notes'])

                if task.get('prompt'):
                    print()
                    print("Agent Prompt:")
                    print(task['prompt'])
                
                if task.get('review_comment'):
                    print()
                    print("Review Comment:")
                    print(task['review_comment'])
        except Exception as e:
            if not json_output:
                console.print(f"[red]Failed to get task #{task_id}: {e}[/red]")

    if json_output:
        import json as json_lib
        if len(tasks) == 1:
            print(json_lib.dumps(tasks[0], indent=2))
        else:
            print(json_lib.dumps(tasks, indent=2))


@tasks_group.command(name="prompt-validate")
@click.argument("task_id", type=int)
def tasks_prompt_validate(task_id):
    """Check task prompt for required sections."""
    import sys

    db = DatabaseManager()
    task = db.get_task(task_id)
    if not task:
        print(f"Task #{task_id} not found")
        sys.exit(1)

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
    if missing:
        print(f"\nStatus: INCOMPLETE ({missing} section{'s' if missing != 1 else ''} missing)")
        sys.exit(1)

    print("\nStatus: COMPLETE")
    sys.exit(0)


@tasks_group.command(name="next")
@click.option("-p", "--project", default=None, help="Filter by project (auto-detects from cwd)")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def tasks_next(project, json_output):
    """Get the next task to work on.
    
    Returns the highest-priority task that is either "To Do" or "In Progress".
    Priority order: Critical > High > Medium > Low > None
    Status order: In Progress > To Do (prefer continuing over starting new)
    
    \b
    Examples:
        ./pt tasks next
        ./pt tasks next -p project-tracker
    
    \b
    Output format (single line, parseable):
        #<id> | <project> | <status> | <priority> | <text>
    
    \b
    Exit codes:
        0: Task found
        1: No tasks available
    """
    import sys
    
    db = DatabaseManager()
    
    # Resolve project (auto-detect from cwd if not specified)
    if project:
        project_id = _resolve_project_id(db, project)
        if not project_id:
            print(f"Project '{project}' not found")
            sys.exit(1)
    else:
        project_id = _detect_project_from_cwd(db)
    
    # Get all non-done tasks
    all_tasks = db.get_tasks(project_id=project_id)
    
    # Filter to actionable statuses
    actionable = [t for t in all_tasks if t["status"] in ("In Progress", "To Do")]
    
    if not actionable:
        print("No tasks available")
        sys.exit(1)
    
    # Priority ranking (lower = higher priority)
    priority_rank = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, None: 4}
    # Status ranking (prefer In Progress over To Do)
    status_rank = {"In Progress": 0, "To Do": 1}
    
    # Sort by: status (In Progress first), then priority (Critical first)
    actionable.sort(key=lambda t: (
        status_rank.get(t["status"], 99),
        priority_rank.get(t.get("priority"), 4)
    ))
    
    # Return the top task
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
    """Show dependency tree for a parent task (AI-first: see execution plan).
    
    Displays subtasks in execution order with status indicators.
    
    \b
    Status Indicators:
        ✅ Done
        ● In Progress (can continue)
        ○ To Do / Backlog (ready)
        🔒 Blocked by incomplete dependencies
    
    \b
    Examples:
        ./pt tasks tree 4645
    """
    import json
    db = DatabaseManager()
    
    task = db.get_task(task_id)
    if not task:
        console.print(f"[red]Task #{task_id} not found[/red]")
        return
    
    subtasks = db.get_subtasks(task_id)
    if not subtasks:
        console.print(f"Task #{task_id} has no subtasks")
        return
    
    # Header
    progress = db.get_subtask_progress(task_id)
    print(f"\nExecution Tree for #{task_id}: {task['text']}\n")
    print(f"Progress: {progress['done']}/{progress['total']} complete ({progress['percent']}%)\n")
    
    # Status emoji map
    status_emoji = {
        "Done": "✅",
        "In Progress": "●",
        "To Do": "○",
        "Backlog": "○"
    }
    
    for i, subtask in enumerate(subtasks):
        is_last = (i == len(subtasks) - 1)
        prefix = "└─" if is_last else "├─"
        
        # Status indicator
        emoji = status_emoji.get(subtask["status"], "?")
        
        # Blocking indicator
        is_blocked, blocking_ids = db.is_blocked(subtask["id"])
        block_str = ""
        if is_blocked:
            block_str = f" 🔒 (blocked by {', '.join([f'#{bid}' for bid in blocking_ids])})"
        elif subtask["status"] not in ["Done", "In Progress"]:
            block_str = " ← READY NOW"
        
        print(f"{prefix} {emoji} #{subtask['id']} | {subtask['status']:12} | {subtask['text']}{block_str}")
    
    print("\nℹ️  Use 'pt tasks next' to see what you can start immediately\n")


@tasks_group.command(name="export")
@click.option("-o", "--output", default="data/tasks_export.json", help="Output file path")
def tasks_export(output):
    """Export all tasks to JSON file for backup.
    
    \b
    Exports all tasks with metadata (timestamp, count) to a JSON file.
    Default output: data/tasks_export.json
    
    \b
    Examples:
        ./pt tasks export                           # Export to data/tasks_export.json
        ./pt tasks export -o backup/tasks.json     # Export to custom path
    """
    import json as json_lib
    from datetime import datetime, timezone
    from pathlib import Path
    
    db = DatabaseManager()
    
    # Get all tasks (including Done)
    all_tasks = db.get_tasks()
    
    # Add export metadata
    export_data = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "total_count": len(all_tasks),
        "tasks": all_tasks
    }
    
    # Ensure output directory exists
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write JSON
    try:
        with open(output_path, 'w') as f:
            json_lib.dump(export_data, f, indent=2)
        console.print(f"[green]✅ Exported {len(all_tasks)} tasks to {output}[/green]")
    except Exception as e:
        console.print(f"[red]Failed to export tasks: {e}[/red]")


@app.command(name="export-projects")
def export_projects(output: str = "data/projects_export.json"):
    """Export all projects to JSON file for backup."""
    import json as json_lib
    from datetime import datetime, timezone
    from pathlib import Path
    
    db = DatabaseManager()
    projects = db.get_all_projects()
    
    export_data = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "total_count": len(projects),
        "projects": projects
    }
    
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Convert sqlite3.Row to dict for JSON serialization
        projects_dict = [dict(p) for p in projects]
        export_data["projects"] = projects_dict
        
        with open(output_path, 'w') as f:
            json_lib.dump(export_data, f, indent=2)
        console.print(f"[green]✅ Exported {len(projects)} projects to {output}[/green]")
    except Exception as e:
        console.print(f"[red]Failed to export projects: {e}[/red]")


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
        if not tasks:
            console.print("[yellow]No tasks found in import file[/yellow]")
            return
            
        console.print(f"Importing {len(tasks)} tasks...")
        success_count = db.raw_import_tasks(tasks)
        console.print(f"[green]✅ Successfully imported {success_count}/{len(tasks)} tasks[/green]")
    except Exception as e:
        console.print(f"[red]Failed to import tasks: {e}[/red]")


@tasks_group.command(name="clear-done")
@click.option("-p", "--project", default=None, help="Filter by project (optional, clears all if not specified)")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation")
def tasks_clear_done(project, yes):
    """Delete all tasks in Done status.

    \b
    Permanently removes completed tasks from the database.

    \b
    Examples:
        ./pt tasks clear-done                    # Delete all Done tasks (with confirmation)
        ./pt tasks clear-done -p project-tracker # Delete Done tasks for specific project
        ./pt tasks clear-done -y                 # Skip confirmation
    """
    db = DatabaseManager()
    project_id = _resolve_project_id(db, project) if project else None

    if project and not project_id:
        console.print(f"[red]Project '{project}' not found[/red]")
        return

    # Count tasks that will be deleted
    done_tasks = db.get_tasks(project_id=project_id, status="Done")
    count = len(done_tasks)

    if count == 0:
        console.print("[dim]No Done tasks to delete[/dim]")
        return

    # Confirm unless -y flag
    if not yes:
        scope_label = f"project {project}" if project else "all projects"
        console.print(f"[dim]Scope: {scope_label}[/dim]")
        confirm = click.confirm(f"Delete {count} Done task(s)?", default=False)
        if not confirm:
            console.print("[dim]Cancelled[/dim]")
            return

    try:
        deleted_count = db.delete_done_tasks(project_id=project_id)
        console.print(f"[green]Deleted {deleted_count} Done task(s)[/green]")
    except Exception as e:
        console.print(f"[red]Failed to delete tasks: {e}[/red]")


# --- INBOX COMMANDS - Simple JSON-based message board for project-less notes ---

INBOX_FILE = Path(__file__).parent.parent / "data" / "inbox.json"


def _load_inbox():
    """Load inbox from JSON file."""
    if not INBOX_FILE.exists():
        return {"notes": [], "next_id": 1}
    import json
    with open(INBOX_FILE, "r") as f:
        return json.load(f)


def _save_inbox(data):
    """Save inbox to JSON file."""
    import json
    INBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(INBOX_FILE, "w") as f:
        json.dump(data, f, indent=2)


@click.group(name="inbox", invoke_without_command=True)
@click.pass_context
def inbox_group(ctx):
    """Quick capture notes not attached to any project.

    \b
    Examples:
        ./pt inbox                    # List all notes
        ./pt inbox add "Remember X"   # Add a note
        ./pt inbox clear              # Clear all notes
        ./pt inbox remove 1           # Remove note by ID
    """
    if ctx.invoked_subcommand is not None:
        return

    # Default behavior: list notes
    ctx.invoke(inbox_list)


@inbox_group.command(name="list")
def inbox_list():
    """List all inbox notes."""
    data = _load_inbox()
    notes = data.get("notes", [])

    if not notes:
        console.print("[dim]Inbox is empty[/dim]")
        return

    console.print(f"\n[bold]📥 Inbox ({len(notes)} notes)[/bold]\n")
    for note in notes:
        console.print(f"  [cyan]#{note['id']}[/cyan] {note['text']}")
    console.print()


@inbox_group.command(name="add")
@click.argument("text")
def inbox_add(text: str):
    """Add a note to the inbox."""
    from datetime import datetime, timezone

    data = _load_inbox()
    note_id = data.get("next_id", 1)

    note = {
        "id": note_id,
        "text": text,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    data["notes"].append(note)
    data["next_id"] = note_id + 1

    _save_inbox(data)
    console.print(f"[green]Added note #{note_id}:[/green] {text}")


@inbox_group.command(name="remove")
@click.argument("note_id", type=int)
def inbox_remove(note_id: int):
    """Remove a note by ID."""
    data = _load_inbox()
    original_count = len(data["notes"])
    data["notes"] = [n for n in data["notes"] if n["id"] != note_id]

    if len(data["notes"]) == original_count:
        console.print(f"[red]Note #{note_id} not found[/red]")
        return

    _save_inbox(data)
    console.print(f"[green]Removed note #{note_id}[/green]")


@inbox_group.command(name="clear")
@click.confirmation_option(prompt="Clear all inbox notes?")
def inbox_clear():
    """Clear all inbox notes."""
    data = {"notes": [], "next_id": 1}
    _save_inbox(data)
    console.print("[green]Inbox cleared[/green]")


# Register Click groups with Typer app and create the combined CLI
typer_click_object = typer.main.get_command(app)
typer_click_object.add_command(scan_cli)
typer_click_object.add_command(tasks_group)
typer_click_object.add_command(inbox_group)


if __name__ == "__main__":
    typer_click_object()

