"""FastAPI web dashboard for project tracker."""

import sys
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
import markdown

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from db.manager import DatabaseManager
from discovery.project_scanner import discover_projects
from discovery.alert_detector import get_all_alerts

app = FastAPI(title="Project Tracker Dashboard")

# Setup templates and static files
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


def format_time_ago(iso_date: str) -> str:
    """Convert ISO date to human-readable time ago."""
    try:
        date = datetime.fromisoformat(iso_date.replace('Z', '+00:00'))
        now = datetime.now(date.tzinfo) if date.tzinfo else datetime.now()
        diff = now - date
        
        days = diff.days
        hours = diff.seconds // 3600
        minutes = (diff.seconds % 3600) // 60
        
        if days > 365:
            years = days // 365
            return f"{years}y ago"
        elif days > 30:
            months = days // 30
            return f"{months}mo ago"
        elif days > 0:
            return f"{days}d ago"
        elif hours > 0:
            return f"{hours}h ago"
        elif minutes > 0:
            return f"{minutes}m ago"
        else:
            return "just now"
    except Exception:
        return iso_date


def categorize_services(services):
    """Categorize services by type."""
    categories = {
        "backend": [],
        "hosting": [],
        "ai": [],
        "storage": [],
        "database": [],
        "notifications": [],
        "monitoring": [],
        "other": []
    }
    
    # Service name to category mapping
    service_types = {
        # Backend Infrastructure (services, APIs, background jobs)
        "railway": "backend",
        "heroku": "backend",
        "aws": "backend",
        
        # Web Hosting (static sites, web apps)
        "vercel": "hosting",
        "netlify": "hosting",
        "cloudflare pages": "hosting",
        "github pages": "hosting",
        
        # AI
        "openai": "ai",
        "anthropic": "ai",
        "claude": "ai",
        "google ai": "ai",
        "gemini": "ai",
        "xai": "ai",
        "grok": "ai",
        
        # Storage
        "cloudflare r2": "storage",
        "r2": "storage",
        "s3": "storage",
        "google drive": "storage",
        "dropbox": "storage",
        
        # Database
        "postgres": "database",
        "postgresql": "database",
        "mysql": "database",
        "mongodb": "database",
        "sqlite": "database",
        
        # Notifications
        "discord": "notifications",
        "slack": "notifications",
        "telegram": "notifications",
        
        # Monitoring
        "healthchecks.io": "monitoring",
        "healthchecks": "monitoring",
        "sentry": "monitoring",
        "datadog": "monitoring",
    }
    
    for service in services:
        name_lower = service["service_name"].lower()
        category = "other"
        
        # Find matching category
        for service_key, cat in service_types.items():
            if service_key in name_lower:
                category = cat
                break
        
        categories[category].append(service)
    
    # Remove empty categories
    return {k: v for k, v in categories.items() if v}


def enrich_project_data(project: dict, db: DatabaseManager) -> dict:
    """Add related data to project."""
    # Get AI agents
    agents = db.get_ai_agents(project["id"])
    project["ai_agents"] = [a["agent_name"] for a in agents]
    
    # Get cron jobs
    jobs = db.get_cron_jobs(project["id"])
    project["has_cron"] = len(jobs) > 0
    project["cron_jobs"] = jobs
    
    # Get services
    services = db.get_services(project["id"])
    project["services"] = [s["service_name"] for s in services]
    project["service_details"] = services
    project["services_by_category"] = categorize_services(services)
    
    # Format time
    project["last_modified_human"] = format_time_ago(project.get("last_modified", ""))
    
    return project


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard view."""
    db = DatabaseManager()
    projects = db.get_all_projects(order_by="last_modified DESC")
    
    # Enrich with related data
    enriched_projects = [enrich_project_data(p, db) for p in projects]
    
    # Get alerts
    alerts = get_all_alerts(enriched_projects)
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "projects": enriched_projects,
        "alerts": alerts,
        "total_projects": len(projects)
    })


@app.get("/project/{project_id}", response_class=HTMLResponse)
async def project_detail(request: Request, project_id: str):
    """Project detail view."""
    db = DatabaseManager()
    project = db.get_project(project_id)
    
    if not project:
        return HTMLResponse(content="<h1>Project not found</h1>", status_code=404)
    
    # Enrich with related data
    project = enrich_project_data(project, db)
    
    # Get work log
    work_log = db.get_work_log(project_id, limit=20)
    
    return templates.TemplateResponse("project_detail.html", {
        "request": request,
        "project": project,
        "work_log": work_log
    })


@app.get("/todo/{project_id}", response_class=HTMLResponse)
async def view_todo(request: Request, project_id: str):
    """View rendered TODO.md."""
    db = DatabaseManager()
    project = db.get_project(project_id)
    
    if not project:
        return HTMLResponse(content="<h1>Project not found</h1>", status_code=404)
    
    # Read TODO.md
    todo_path = Path(project["path"]) / "TODO.md"
    
    if not todo_path.exists():
        todo_html = "<p class='no-todo'>No TODO.md found for this project.</p>"
    else:
        try:
            todo_content = todo_path.read_text()
            
            # Render markdown with extensions
            md = markdown.Markdown(
                extensions=[
                    'tables',
                    'fenced_code',
                    'codehilite',
                    'nl2br',
                    'sane_lists'
                ]
            )
            todo_html = md.convert(todo_content)
        except Exception as e:
            todo_html = f"<p class='error'>Error reading TODO.md: {e}</p>"
    
    return templates.TemplateResponse("todo_viewer.html", {
        "request": request,
        "project": project,
        "todo_html": todo_html
    })


@app.post("/api/refresh")
async def refresh_data():
    """Trigger full data refresh."""
    try:
        db = DatabaseManager()
        
        # Scan projects
        projects = discover_projects()
        
        # Update database
        for project in projects:
            db.add_project(
                project_id=project["id"],
                name=project["name"],
                path=project["path"],
                status=project["status"],
                description=project.get("description"),
                phase=project.get("phase"),
                last_modified=project["last_modified"],
                completion_pct=project.get("completion_pct", 0),
                is_infrastructure=project.get("is_infrastructure", False)
            )
            
            # Log refresh
            db.log_event(project["id"], "refresh", "Manual refresh via dashboard")
        
        return JSONResponse({
            "status": "success",
            "message": f"Refreshed {len(projects)} projects"
        })
    except Exception as e:
        return JSONResponse({
            "status": "error",
            "message": str(e)
        }, status_code=500)


@app.get("/api/projects")
async def api_projects():
    """JSON API for projects."""
    db = DatabaseManager()
    projects = db.get_all_projects(order_by="last_modified DESC")
    
    # Enrich with related data
    enriched_projects = [enrich_project_data(p, db) for p in projects]
    
    return {"projects": enriched_projects}


@app.get("/api/alerts")
async def api_alerts():
    """Get all alerts."""
    db = DatabaseManager()
    projects = db.get_all_projects()
    enriched_projects = [enrich_project_data(p, db) for p in projects]
    alerts = get_all_alerts(enriched_projects)
    return {"alerts": alerts}


@app.get("/api/stats")
async def api_stats():
    """Dashboard statistics."""
    db = DatabaseManager()
    projects = db.get_all_projects()
    
    # Count by status
    status_counts = {}
    for project in projects:
        status = project["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
    
    # Count projects with cron jobs
    projects_with_cron = 0
    for project in projects:
        jobs = db.get_cron_jobs(project["id"])
        if jobs:
            projects_with_cron += 1
    
    # Count projects with AI agents
    projects_with_ai = 0
    for project in projects:
        agents = db.get_ai_agents(project["id"])
        if agents:
            projects_with_ai += 1
    
    # Get alert counts
    enriched_projects = [enrich_project_data(p, db) for p in projects]
    alerts = get_all_alerts(enriched_projects)
    alert_counts = {
        "critical": len([a for a in alerts if a["severity"] == "critical"]),
        "warning": len([a for a in alerts if a["severity"] == "warning"]),
        "info": len([a for a in alerts if a["severity"] == "info"])
    }
    
    return {
        "total_projects": len(projects),
        "status_counts": status_counts,
        "projects_with_cron": projects_with_cron,
        "projects_with_ai": projects_with_ai,
        "alerts": alert_counts
    }

