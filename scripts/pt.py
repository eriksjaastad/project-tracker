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
    
    # Delete projects that are no longer found
    to_delete = existing_ids - discovered_ids
    for project_id in to_delete:
        db.delete_project(project_id)
        project_name = next((p["name"] for p in existing_projects if p["id"] == project_id), project_id)
        console.print(f"  [red]✗ Removed {project_name}[/red]")
    
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
            project_type=project.get("project_type", "standard")
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
def list_projects():
    """List all projects. AI-first: plain print(), no terminal width constraints."""
    db = DatabaseManager()
    projects = db.get_all_projects()

    if not projects:
        print("No projects found. Run 'pt scan' first.")
        return

    print("Projects\n")
    for project in projects:
        # Format index status
        idx = "✓" if project.get("has_index") and project.get("index_is_valid") else "!"
        phase = project.get("phase") or "-"
        pct = project.get("completion_pct", 0)

        print(f"{project['name']} | {project['status']} | {phase} | {pct}% | {idx}")

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

def _display_tasks(task_list: list, project: str | None = None):
    """Display tasks. AI-first: plain print(), no terminal width constraints."""
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

        # Plain print - no terminal width wrapping
        if project:
            print(f"#{task_id} | {status} | {priority} | {task_text}")
        else:
            print(f"#{task_id} | {task['project_id']} | {status} | {priority} | {task_text}")

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
@click.option("--archived", is_flag=True, help="Include archived tasks (Done > 7 days)")
def tasks_group(ctx, project, status, show_all, archived):
    """Manage Kanban board tasks.

    \b
    Examples:
        ./pt tasks                       # Show open tasks (all projects)
        ./pt tasks -p project-tracker    # Tasks for a specific project
        ./pt tasks -s "In Progress"      # Filter by status
        ./pt tasks --all                 # Include completed tasks
        ./pt tasks --archived            # Include archived tasks
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

    task_list = db.get_tasks(project_id=project_id, status=status, include_archived=archived)

    # Filter out Done unless --all or specific status
    if not show_all and not status:
        task_list = [t for t in task_list if t["status"] != "Done"]

    _display_tasks(task_list, project)


@tasks_group.command(name="list")
@click.option("-p", "--project", default=None, help="Filter by project name or ID")
@click.option("-s", "--status", default=None, help="Filter by status")
@click.option("-a", "--all", "show_all", is_flag=True, help="Include completed tasks")
@click.option("--archived", is_flag=True, help="Include archived tasks (Done > 7 days)")
def tasks_list(project, status, show_all, archived):
    """List tasks from the Kanban board."""
    db = DatabaseManager()
    project_id = _resolve_project_id(db, project)

    if project and not project_id:
        console.print(f"[red]Project '{project}' not found[/red]")
        return

    task_list = db.get_tasks(project_id=project_id, status=status, include_archived=archived)

    if not show_all and not status:
        task_list = [t for t in task_list if t["status"] != "Done"]

    _display_tasks(task_list, project)


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
@click.argument("task_id", type=int)
def tasks_done(task_id):
    """Mark a task as Done.

    \b
    Example:
        ./pt tasks done 42
    """
    db = DatabaseManager()

    try:
        task = db.get_task(task_id)
        if not task:
            console.print(f"[red]Task #{task_id} not found[/red]")
            return
        db.update_task(task_id, status="Done")
        console.print(f"[green]Done:[/green] {task['text']}")
    except Exception as e:
        console.print(f"[red]Failed to complete task #{task_id}: {e}[/red]")


@tasks_group.command(name="start")
@click.argument("task_id", type=int)
def tasks_start(task_id):
    """Move a task to In Progress.

    \b
    Example:
        ./pt tasks start 42
    """
    db = DatabaseManager()

    try:
        task = db.get_task(task_id)
        if not task:
            console.print(f"[red]Task #{task_id} not found[/red]")
            return
        db.update_task(task_id, status="In Progress")
        console.print(f"[yellow]Started:[/yellow] {task['text']}")
    except Exception as e:
        console.print(f"[red]Failed to start task #{task_id}: {e}[/red]")


@tasks_group.command(name="show")
@click.argument("task_id", type=int)
def tasks_show(task_id):
    """Show full details of a task including prompt.

    \b
    Example:
        ./pt tasks show 42
    """
    db = DatabaseManager()

    try:
        task = db.get_task(task_id)
        if not task:
            console.print(f"[red]Task #{task_id} not found[/red]")
            return

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
        console.print(f"[red]Failed to get task #{task_id}: {e}[/red]")


@tasks_group.command(name="archive")
@click.option("--days", default=7, help="Archive Done tasks older than N days (default: 7)")
def tasks_archive(days):
    """Manually archive old Done tasks.

    \b
    Tasks in Done status for more than N days are archived.
    Archived tasks are hidden from normal views but preserved in the database.

    \b
    Examples:
        ./pt tasks archive           # Archive Done tasks > 7 days old
        ./pt tasks archive --days 14 # Archive Done tasks > 14 days old
    """
    db = DatabaseManager()

    try:
        archived_count = db.archive_old_done_tasks(days=days)
        if archived_count > 0:
            console.print(f"[green]Archived {archived_count} task(s) completed more than {days} days ago[/green]")
        else:
            console.print(f"[dim]No tasks to archive (none in Done > {days} days)[/dim]")
    except Exception as e:
        console.print(f"[red]Failed to archive tasks: {e}[/red]")


# Register Click group with Typer app and create the combined CLI
typer_click_object = typer.main.get_command(app)
typer_click_object.add_command(tasks_group)


if __name__ == "__main__":
    typer_click_object()

