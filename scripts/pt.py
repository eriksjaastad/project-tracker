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
    """List all projects."""
    db = DatabaseManager()
    projects = db.get_all_projects()
    
    if not projects:
        console.print("[yellow]No projects found. Run 'pt scan' first.[/yellow]")
        return
    
    # Create table
    table = Table(title="Projects")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Status", style="green")
    table.add_column("Phase")
    table.add_column("Progress", justify="right")
    table.add_column("Index", justify="center")
    table.add_column("Last Modified")
    
    for project in projects:
        # Format last modified
        last_mod = project.get("last_modified", "unknown")
        if last_mod and last_mod != "unknown":
            # Just show date part
            last_mod = last_mod.split("T")[0]
            
        # Format index status
        index_status = "-"
        if project.get("has_index"):
            index_status = "[green]✓[/green]" if project.get("index_is_valid") else "[yellow]![/yellow]"
        else:
            index_status = "[red]✗[/red]"
        
        table.add_row(
            project["name"],
            project["status"],
            project.get("phase") or "-",
            f"{project.get('completion_pct', 0)}%",
            index_status,
            last_mod
        )
    
    console.print(table)
    console.print(f"\n[bold]Total: {len(projects)} projects[/bold]")


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


if __name__ == "__main__":
    app()

