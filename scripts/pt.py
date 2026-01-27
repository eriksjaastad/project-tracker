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

from config import PROJECTS_BASE_DIR
from db.schema import init_db
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


@app.command()
def scan(
    no_graph: bool = typer.Option(False, "--no-graph", help="Skip rebuilding the knowledge graph")
):
    """Scan projects directory and update database."""
    console.print(f"[bold blue]Scanning projects in {PROJECTS_BASE_DIR}...[/bold blue]")
    
    # Ensure database exists
    init_db()
    db = DatabaseManager()
    
    # Discover projects
    with Progress() as progress:
        task = progress.add_task("[cyan]Discovering projects...", total=None)
        projects = discover_projects(PROJECTS_BASE_DIR, sync_indexes=True)
        progress.update(task, completed=True)
    
    console.print(f"\n[green]Found {len(projects)} projects[/green]\n")
    
    # Run health checks in parallel
    with Progress() as progress:
        task = progress.add_task("[cyan]Auditing project health...", total=len(projects))
        health_results = scan_health_parallel(projects)
        progress.update(task, advance=len(projects))
    
    # Get current project IDs in database
    existing_projects = db.get_all_projects()
    existing_ids = {p["id"] for p in existing_projects}
    discovered_ids = {p["id"] for p in projects}
    
    # NOTE: We intentionally do NOT delete projects that are no longer found.
    # Projects may be temporarily unavailable (unmounted drives, renamed folders).
    # Deleting a project cascades to delete ALL tasks - too dangerous for auto-cleanup.
    # Use explicit `./pt remove <project>` command if needed (to be implemented).
    stale_ids = existing_ids - discovered_ids
    if stale_ids:
        console.print(f"  [dim]ℹ {len(stale_ids)} projects not found in scan (preserved in DB)[/dim]")

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

        # Add/update project
        db.add_project(
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
        
        # Clear old AI agents, cron jobs, and services
        db.delete_ai_agents(project["id"])
        db.delete_cron_jobs(project["id"])
        db.delete_services(project["id"])
        # Services will be repopulated from EXTERNAL_RESOURCES.md below
        
        # Add AI agents
        for agent in project.get("ai_agents", []):
            db.add_ai_agent(
                project_id=project["id"],
                agent_name=agent["agent_name"],
                role=agent.get("role")
            )
        
        # Add cron jobs
        for job in project.get("cron_jobs", []):
            db.add_cron_job(
                project_id=project["id"],
                schedule=job["schedule"],
                command=job["command"],
                description=job.get("description")
            )
        
        console.print(f"  ✓ {project['name']}")
        
        # Update health if available
        health = health_results.get(project["id"])
        if health:
            db.update_health(
                project_id=project["id"],
                score=health["score"],
                grade=health["grade"]
            )
    
    # Parse and add services from EXTERNAL_RESOURCES.md
    console.print(f"\n[bold blue]Loading services from EXTERNAL_RESOURCES.md...[/bold blue]")
    services_by_project = parse_external_resources()
    
    services_added = 0
    services_skipped = 0
    known_project_ids = {p["id"] for p in db.get_all_projects()}
    for project_id, services in services_by_project.items():
        if project_id not in known_project_ids:
            services_skipped += 1
            console.print(f"  [yellow]! Skipping services for unknown project: {project_id}[/yellow]")
            continue
        for service in services:
            db.add_service(
                project_id=project_id,
                service_name=service["service_name"],
                purpose=service.get("purpose"),
                cost_monthly=service.get("cost_monthly")
            )
            services_added += 1
    
    if services_added > 0:
        console.print(f"  [green]✓ Added {services_added} services across {len(services_by_project)} projects[/green]")
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


def _display_tasks(task_list: list, project: str | None = None, json_output: bool = False):
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
        
        # [P] marker if prompt has all three sections (Overview, Execution, Done Criteria)
        prompt_marker = "[P] " if _has_complete_prompt(task.get("prompt")) else ""

        # Plain print - no terminal width wrapping
        if project:
            print(f"#{task_id} {prompt_marker}| {status} | {priority} | {task_text}")
        else:
            print(f"#{task_id} {prompt_marker}| {task['project_id']} | {status} | {priority} | {task_text}")

    # Summary
    status_counts = {}
    for task in task_list:
        status_counts[task["status"]] = status_counts.get(task["status"], 0) + 1

    summary_parts = [f"{s}: {status_counts[s]}" for s in ["Backlog", "To Do", "In Progress", "Review", "Done"] if s in status_counts]
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
@click.option("-s", "--status", default=None, help="Filter by status (Backlog, To Do, In Progress, Done)")
@click.option("-a", "--all", "show_all", is_flag=True, help="Include completed tasks")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def tasks_group(ctx, project, status, show_all, json_output):
    """Manage Kanban board tasks.

    \b
    Examples:
        ./pt tasks                       # Show open tasks (all projects)
        ./pt tasks -p project-tracker    # Tasks for a specific project
        ./pt tasks -s "In Progress"      # Filter by status
        ./pt tasks --all                 # Include completed tasks
        ./pt tasks create "Fix bug" -p myproject
    """
    # If a subcommand is invoked, don't run the default list behavior
    if ctx.invoked_subcommand is not None:
        return

    # Default behavior: list tasks
    db = DatabaseManager()
    project_id = _resolve_project_id(db, project)

    if project and not project_id:
        console.print(f"[red]Project '{project}' not found[/red]")
        return

    task_list = db.get_tasks(project_id=project_id, status=status)

    # Filter out Done unless --all or specific status
    if not show_all and not status:
        task_list = [t for t in task_list if t["status"] != "Done"]

    _display_tasks(task_list, project, json_output=json_output)


@tasks_group.command(name="list")
@click.option("-p", "--project", default=None, help="Filter by project name or ID")
@click.option("-s", "--status", default=None, help="Filter by status")
@click.option("-a", "--all", "show_all", is_flag=True, help="Include completed tasks")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def tasks_list(project, status, show_all, json_output):
    """List tasks from the Kanban board."""
    db = DatabaseManager()
    project_id = _resolve_project_id(db, project)

    if project and not project_id:
        console.print(f"[red]Project '{project}' not found[/red]")
        return

    task_list = db.get_tasks(project_id=project_id, status=status)

    if not show_all and not status:
        task_list = [t for t in task_list if t["status"] != "Done"]

    _display_tasks(task_list, project, json_output=json_output)


@tasks_group.command(name="create")
@click.argument("text")
@click.option("-p", "--project", default=None, help="Project ID or name (auto-detects from cwd)")
@click.option("-s", "--status", default="Backlog", help="Initial status (default: Backlog)")
@click.option("--priority", default=None, help="Priority: Critical, High, Medium, Low")
@click.option("--prompt", default=None, help="Agent prompt (execution instructions for AI)")
def tasks_create(text, project, status, priority, prompt):
    """Create a new task. Auto-detects project from current directory.

    \b
    Examples:
        ./pt tasks create "Fix login bug"
        ./pt tasks create "Add tests" -p myproject -s "To Do" --priority High
        ./pt tasks create "Refactor auth" --prompt "Overview: ... Execution: ... Done:"
    """
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
    valid_statuses = ["Backlog", "To Do", "In Progress", "Review", "Done"]
    if status not in valid_statuses:
        console.print(f"[red]Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}[/red]")
        return

    # Validate priority if provided
    valid_priorities = ["Critical", "High", "Medium", "Low", None]
    if priority and priority not in valid_priorities:
        console.print(f"[red]Invalid priority '{priority}'. Must be one of: Critical, High, Medium, Low[/red]")
        return

    try:
        task = db.add_task(text=text, project_id=project_id, status=status, priority=priority, prompt=prompt)
        console.print(f"[green]Created task #{task['id']}: {text[:50]}{'...' if len(text) > 50 else ''}[/green]")
    except Exception as e:
        console.print(f"[red]Failed to create task: {e}[/red]")


@tasks_group.command(name="update")
@click.argument("task_id", type=int)
@click.option("-s", "--status", default=None, help="New status")
@click.option("-t", "--text", default=None, help="New task text")
@click.option("--priority", default=None, help="New priority")
@click.option("--prompt", default=None, help="Agent prompt (execution instructions for AI)")
def tasks_update(task_id, status, text, priority, prompt):
    """Update an existing task.

    \b
    Examples:
        ./pt tasks update 42 -s "In Progress"
        ./pt tasks update 42 -t "Updated description" --priority High
        ./pt tasks update 42 --prompt "Overview: ... Execution: ... Done:"
    """
    db = DatabaseManager()

    # Build updates dict
    updates = {}
    if status:
        valid_statuses = ["Backlog", "To Do", "In Progress", "Review", "Done"]
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

    if not updates:
        console.print("[yellow]No updates specified. Use -s, -t, --priority, or --prompt.[/yellow]")
        return

    try:
        task = db.update_task(task_id, **updates)
        console.print(f"[green]Updated task #{task_id}[/green]")

        # Show what was updated
        for key, value in updates.items():
            console.print(f"  {key}: {value}")
    except Exception as e:
        console.print(f"[red]Failed to update task #{task_id}: {e}[/red]")


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
            db.update_task(task_id, status="In Progress")
            print(f"Started: #{task_id} - {task['text'][:50]}")
            success_count += 1
        except Exception as e:
            print(f"Failed to start task #{task_id}: {e}")
    
    if len(task_ids) > 1:
        print(f"\nStarted {success_count}/{len(task_ids)} tasks")


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
                print(f"Created: {task['created_at']}")
                print(f"Updated: {task['updated_at']}")
                if task.get('completed_at'):
                    print(f"Completed: {task['completed_at']}")
                print()
                print("Description:")
                print(task['text'])

                if task.get('prompt'):
                    print()
                    print("Agent Prompt:")
                    print(task['prompt'])
        except Exception as e:
            if not json_output:
                console.print(f"[red]Failed to get task #{task_id}: {e}[/red]")

    if json_output:
        import json as json_lib
        if len(tasks) == 1:
            print(json_lib.dumps(tasks[0], indent=2))
        else:
            print(json_lib.dumps(tasks, indent=2))


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
        scope = f"for project '{project}'" if project else "across all projects"
        confirm = click.confirm(f"Delete {count} Done task(s) {scope}?", default=False)
        if not confirm:
            console.print("[dim]Cancelled[/dim]")
            return

    try:
        deleted_count = db.delete_done_tasks(project_id=project_id)
        console.print(f"[green]Deleted {deleted_count} Done task(s)[/green]")
    except Exception as e:
        console.print(f"[red]Failed to delete tasks: {e}[/red]")


# Register Click group with Typer app and create the combined CLI
typer_click_object = typer.main.get_command(app)
typer_click_object.add_command(tasks_group)


if __name__ == "__main__":
    typer_click_object()

