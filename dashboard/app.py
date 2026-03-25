"""FastAPI web dashboard for project tracker."""

import sys
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import subprocess

from fastapi import FastAPI, Request, HTTPException, status, UploadFile, File
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler
)
import re
import sqlite3
import json
import uuid
from time import time as _time

import numpy as np

# Add parent directory to path for logger import
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.logger import get_logger

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from db.manager import DatabaseManager
from discovery.agent_config_health import build_empty_agent_config_health, get_agent_config_health
from discovery.project_scanner import discover_projects
from discovery.alert_detector import get_all_alerts
from discovery.code_review_parser import parse_code_review
from discovery.providers import get_provider, LegacyProvider
from discovery.telemetry_reader import get_telemetry_stats
from discovery.backup_reader import get_backup_status
from discovery.agent_registry import (
    get_available_agents,
    run_agent_command,
    Agent,
    AgentCommand,
    CommandResult
)
from pydantic import BaseModel

# Import config
from scripts.config import PROJECTS_BASE_DIR, REINDEX_SCRIPT_PATH

# Import scaffolding version helpers
from scripts.pt import get_current_scaffolding_version, compare_versions, rebuild_knowledge_graph

logger = get_logger(__name__)

app = FastAPI(title="Project Tracker Dashboard")

# Run idempotent migrations on startup
try:
    DatabaseManager().migrate_attachments_table()
except Exception as _mig_err:
    logger.warning(f"Attachments migration skipped: {_mig_err}")

# Setup templates and static files
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

# Mount React frontend build
frontend_dist = Path(__file__).parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

NAVIGATION_TITLE = "Project Tracker"
NAVIGATION_ITEMS = [
    {
        "id": "dashboard",
        "label": "Dashboard",
        "href": "/dashboard",
        "match_prefixes": ["/dashboard", "/project"],
        "navigation_type": "document",
    },
    {
        "id": "kanban",
        "label": "Kanban",
        "href": "/kanban",
        "match_prefixes": ["/kanban"],
        "navigation_type": "spa",
    },
    {
        "id": "agentic",
        "label": "Agentic",
        "href": "/agentic",
        "match_prefixes": ["/agentic"],
        "navigation_type": "spa",
    },
    {
        "id": "calendar",
        "label": "Calendar",
        "href": "/calendar",
        "match_prefixes": ["/calendar"],
        "navigation_type": "spa",
    },
    {
        "id": "graph",
        "label": "Graph",
        "href": "/graph",
        "match_prefixes": ["/graph"],
        "navigation_type": "document",
    },
    {
        "id": "memory",
        "label": "Memory 🧠",
        "href": "/memory",
        "match_prefixes": ["/memory"],
        "navigation_type": "document",
    },
]


def is_navigation_item_active(item: Dict[str, object], path: str) -> bool:
    """Return True when a navigation item should be active for the given path."""
    for prefix in item.get("match_prefixes", []):
        if not isinstance(prefix, str):
            continue
        if path == prefix or path.startswith(f"{prefix}/"):
            return True
    return False


def build_navigation(current_path: Optional[str] = None) -> List[Dict[str, object]]:
    """Build navigation metadata for templates and API responses."""
    nav_items: List[Dict[str, object]] = []
    for item in NAVIGATION_ITEMS:
        nav_item = dict(item)
        nav_item["active"] = bool(current_path and is_navigation_item_active(item, current_path))
        nav_items.append(nav_item)
    return nav_items


def build_navigation_payload(current_path: Optional[str] = None) -> Dict[str, object]:
    """Return the shared navigation payload for templates, the API, and the SPA shell."""
    return {
        "title": NAVIGATION_TITLE,
        "items": build_navigation(current_path),
    }


def build_template_context(request: Request, **context) -> Dict[str, object]:
    """Attach shared shell/navigation context to Jinja responses."""
    return {
        "request": request,
        "nav_title": NAVIGATION_TITLE,
        "nav_items": build_navigation_payload(request.url.path)["items"],
        **context,
    }


def build_spa_shell_html(index_html: str, current_path: str) -> str:
    """Inject backend-owned navigation metadata into the SPA shell."""
    payload = json.dumps(build_navigation_payload(current_path)).replace("<", "\\u003c")
    bootstrap_script = f"<script>window.__PT_NAVIGATION__ = {payload};</script>"

    if "</head>" in index_html:
        return index_html.replace("</head>", f"    {bootstrap_script}\n</head>", 1)

    return f"{bootstrap_script}\n{index_html}"


async def serve_spa_shell(request: Request):
    """Serve the React SPA shell for SPA-owned routes."""
    index_path = frontend_dist / "index.html"
    if index_path.exists():
        return HTMLResponse(content=build_spa_shell_html(index_path.read_text(), request.url.path), status_code=200)

    # Fallback to dashboard when the frontend bundle is not built.
    return await dashboard(request)


@app.get("/kanban", response_class=HTMLResponse)
@app.get("/kanban/{project}", response_class=HTMLResponse)
@app.get("/agentic", response_class=HTMLResponse)
@app.get("/calendar", response_class=HTMLResponse)
async def serve_react_app(request: Request):
    """Serve the React frontend for SPA routes."""
    return await serve_spa_shell(request)


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
    except Exception as e:
        logger.warning(f"Failed to format date '{iso_date}': {e}")
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


def enrich_project_data(project: dict, db: DatabaseManager, current_scaffolding_version: Optional[str] = None) -> dict:
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
    
    # Get task counts
    all_tasks = db.get_tasks(project_id=project["id"])
    open_tasks = [t for t in all_tasks if t.get("status") != "Done"]
    project["task_count"] = len(open_tasks)
    project["total_tasks"] = len(all_tasks)

    # Per-status breakdowns (excluding Done)
    project["backlog_count"] = len([t for t in all_tasks if t.get("status") == "Backlog"])
    project["todo_count"] = len([t for t in all_tasks if t.get("status") == "To Do"])
    project["in_progress_count"] = len([t for t in all_tasks if t.get("status") == "In Progress"])
    project["review_count"] = len([t for t in all_tasks if t.get("status") == "Review"])
    
    # Check for code review
    review_path = Path(project["path"]) / "CODE_REVIEW.md"
    if review_path.exists():
        review_data = parse_code_review(review_path)
        if review_data and review_data.get("completion_pct", 100) < 100:
            project["code_review"] = review_data
    
    # Format time
    project["last_modified_human"] = format_time_ago(project.get("last_modified", ""))
    
    # Format index time
    if project.get("index_updated_at"):
        project["index_updated_human"] = format_time_ago(project["index_updated_at"])
    
    # Calculate version status (opt-in: only check projects with .scaffolding-version)
    project_id = project.get("id", "")
    project_path = Path(project.get("path", ""))
    if project_path.exists():
        project["agent_config_health"] = get_agent_config_health(project_path)
    else:
        project["agent_config_health"] = build_empty_agent_config_health(project.get("name", project_id))

    try:
        path_exists = project_path.exists()
        version_file = project_path / ".scaffolding-version" if path_exists else None
        has_scaffolding_file = version_file is not None and version_file.exists()
    except OSError:
        path_exists = False
        has_scaffolding_file = False

    if not path_exists:
        # Project directory doesn't exist (stale/deleted) or inaccessible
        project["version_status"] = "unmanaged"
    elif not has_scaffolding_file:
        # No .scaffolding-version file — project is not managed by scaffolding
        project["version_status"] = "unmanaged"
    else:
        project_version = project.get("scaffolding_version")
        scaffolding_issues = []

        # Check for {placeholder} content in CLAUDE.md
        claude_md = project_path / "CLAUDE.md"
        if claude_md.exists():
            try:
                content = claude_md.read_text(errors='ignore')
                if '{project_description}' in content or '{language}' in content or '{framework}' in content:
                    scaffolding_issues.append("CLAUDE.md has unfilled placeholders")
            except Exception as e:
                logger.warning(f"Could not check CLAUDE.md for placeholders in {claude_md}: {e}")

        # Check for rogue 00-full-content.md in .agentsync/rules/
        rogue_file = project_path / ".agentsync" / "rules" / "00-full-content.md"
        if rogue_file.exists():
            scaffolding_issues.append("rogue 00-full-content.md in .agentsync/rules/")

        if scaffolding_issues:
            project["scaffolding_issues"] = scaffolding_issues
            # If version is also outdated, keep 'outdated' — it captures both problems
            # Only use 'structural_issue' when version is actually current
            if project_version is None:
                project["version_status"] = "unscaffolded"
            elif current_scaffolding_version and compare_versions(project_version, current_scaffolding_version) < 0:
                project["version_status"] = "outdated"
            else:
                project["version_status"] = "structural_issue"
        elif project_version is None:
            project["version_status"] = "unscaffolded"
        elif current_scaffolding_version and compare_versions(project_version, current_scaffolding_version) < 0:
            project["version_status"] = "outdated"
        else:
            project["version_status"] = "current"
    
    return project


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Redirect the root route to the canonical dashboard URL."""
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

@app.get("/old", response_class=HTMLResponse)
async def react_frontend():
    """Redirect the legacy SPA entry to the canonical Kanban route."""
    return RedirectResponse(url="/kanban", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard view."""
    db = DatabaseManager()
    projects = db.get_all_projects(order_by="last_modified DESC")
    
    # Get current scaffolding version
    current_scaffolding, _ = get_current_scaffolding_version()
    
    # Enrich with related data
    enriched_projects = [enrich_project_data(p, db, current_scaffolding) for p in projects]
    
    # Get alerts
    alerts = get_all_alerts(enriched_projects)
    
    # Calculate index compliance
    indexed_count = len([p for p in enriched_projects if p.get("has_index") and p.get("index_is_valid")])
    compliance_pct = int((indexed_count / len(projects)) * 100) if projects else 0
    
    # Check if audit binary is available
    provider = get_provider()
    audit_available = not isinstance(provider, LegacyProvider)
    
    # Get available agents for dispatcher
    agents = get_available_agents()
    agents_data = [
        {
            "name": a.name,
            "description": a.description,
            "available": a.available,
            "commands": [{"name": c.name, "description": c.description} for c in a.commands]
        }
        for a in agents
    ]
    
    # Get backup status
    backup_status = get_backup_status()
    
    # Collect code reviews separately for prominent display
    code_reviews = []
    for project in enriched_projects:
        review_path = Path(project["path"]) / "CODE_REVIEW.md"
        if review_path.exists():
            review_data = parse_code_review(review_path)
            if review_data and review_data.get("completion_pct", 100) < 100:
                code_reviews.append({
                    "project_id": project["id"],
                    "project_name": project["name"],
                    **review_data
                })
    
    # Calculate version status counts
    outdated_projects = [p for p in enriched_projects if p.get("version_status") == "outdated"]
    unscaffolded_projects = [p for p in enriched_projects if p.get("version_status") == "unscaffolded"]
    structural_projects = [p for p in enriched_projects if p.get("version_status") == "structural_issue"]
    
    return templates.TemplateResponse(
        request,
        "index.html",
        build_template_context(
            request,
            projects=enriched_projects,
            alerts=alerts,
            code_reviews=code_reviews,
            total_projects=len(projects),
            indexed_count=indexed_count,
            compliance_pct=compliance_pct,
            agents=agents_data,
            backup_status=backup_status,
            current_scaffolding_version=current_scaffolding,
            outdated_projects=outdated_projects,
            unscaffolded_projects=unscaffolded_projects,
            structural_projects=structural_projects,
            outdated_count=len(outdated_projects),
            unscaffolded_count=len(unscaffolded_projects),
            structural_count=len(structural_projects),
        ),
    )


@app.get("/project/{project_id}", response_class=HTMLResponse)
async def project_detail(request: Request, project_id: str):
    """Project detail view."""
    db = DatabaseManager()
    project = db.get_project(project_id)
    
    if not project:
        return HTMLResponse(content="<h1>Project not found</h1>", status_code=404)
    
    # Get current scaffolding version
    current_scaffolding, _ = get_current_scaffolding_version()
    
    # Enrich with related data
    project = enrich_project_data(project, db, current_scaffolding)
    
    return templates.TemplateResponse(
        request,
        "project_detail.html",
        build_template_context(request, project=project),
    )


@app.get("/api/navigation")
async def api_navigation():
    """Return shared top-level navigation metadata for all app shells."""
    return build_navigation_payload()


@app.post("/api/create-index/{project_id}")
async def create_index(project_id: str):
    """Run reindex_projects.py for a specific project."""
    try:
        db = DatabaseManager()
        project = db.get_project(project_id)
        if not project:
            return JSONResponse({"status": "error", "message": "Project not found"}, status_code=404)
            
        if not REINDEX_SCRIPT_PATH.exists():
            return JSONResponse({"status": "error", "message": "Reindex script not found"}, status_code=500)
            
        # Run script
        try:
            result = subprocess.run(
                [sys.executable, str(REINDEX_SCRIPT_PATH), project["path"]],
                capture_output=True,
                text=True,
                timeout=30
            )
        except subprocess.TimeoutExpired:
            return JSONResponse({
                "status": "error", 
                "message": "Reindex script timed out after 30 seconds"
            }, status_code=504)
        
        if result.returncode != 0:
            return JSONResponse({
                "status": "error", 
                "message": f"Script failed: {result.stderr}"
            }, status_code=500)
            
        # Rescan to update DB
        try:
            rescan_result = subprocess.run(
                [sys.executable, str(Path(__file__).parent.parent / "scripts" / "pt.py"), "scan"],
                capture_output=True,
                text=True,
                timeout=30
            )
        except subprocess.TimeoutExpired:
            logger.warning("Project rescan timed out after index creation, but index may have been created.")
            # We don't return error here because the index was already created
        
        return JSONResponse({
            "status": "success",
            "message": f"Index created for {project['name']}"
        })
    except Exception as e:
        logger.error(f"Error creating index: {e}")
        return JSONResponse({
            "status": "error",
            "message": str(e)
        }, status_code=500)


@app.post("/api/fix-frontmatter/{project_id}")
async def fix_frontmatter(project_id: str):
    """Call audit fix for a specific project's index file."""
    db = DatabaseManager()
    project = db.get_project(project_id)
    if not project:
        return JSONResponse({"success": False, "error": "Project not found"}, status_code=404)
    
    # Find index file
    index_files = list(Path(project["path"]).glob("00_Index_*.md"))
    if not index_files:
        return JSONResponse({"success": False, "error": "No index file found"}, status_code=404)
    
    provider = get_provider()
    try:
        success = provider.fix_file(str(index_files[0]))
        return {"success": success, "error": None if success else "Fix failed"}
    except NotImplementedError:
        return JSONResponse({"success": False, "error": "audit-agent not installed"}, status_code=501)
    except Exception as e:
        logger.error(f"Error fixing frontmatter: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


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
                is_infrastructure=project.get("is_infrastructure", False),
                has_index=project.get("has_index", False),
                index_is_valid=project.get("index_is_valid", False),
                index_updated_at=project.get("index_updated_at"),
                project_type=project.get("project_type", "standard"),
                scaffolding_version=project.get("scaffolding_version"),
                rules_version=project.get("rules_version"),
                scaffolding_applied_at=project.get("scaffolding_applied_at")
            )

        # Clean up stale projects whose directories no longer exist on disk.
        # Only remove projects whose path is under the local PROJECTS_BASE_DIR
        # so we don't accidentally delete remote/Turso entries from other machines.
        disk_paths = {p["path"] for p in projects}
        local_prefix = str(PROJECTS_BASE_DIR)
        all_db_projects = db.get_all_projects()
        removed = 0
        for db_proj in all_db_projects:
            proj_path = db_proj.get("path", "")
            if (
                proj_path.startswith(local_prefix)
                and proj_path not in disk_paths
                and not Path(proj_path).exists()
            ):
                logger.info(f"Removing stale project from DB: {db_proj['id']} ({proj_path})")
                db.delete_project(db_proj["id"])
                removed += 1

        # Rebuild knowledge graph so dashboard is up to date
        rebuild_knowledge_graph()

        return JSONResponse({
            "status": "success",
            "message": f"Refreshed {len(projects)} projects, removed {removed} stale, rebuilt graph"
        })
    except Exception as e:
        logger.error(f"Error refreshing data: {e}")
        return JSONResponse({
            "status": "error",
            "message": str(e)
        }, status_code=500)


@app.get("/api/telemetry")
async def api_telemetry(days: int = 7):
    """Get AI Router telemetry stats."""
    try:
        stats = get_telemetry_stats(days=days)
        return stats
    except Exception as e:
        logger.error(f"Error getting telemetry: {e}")
        return {"error": str(e), "total_requests": 0}


@app.get("/api/backup")
async def api_backup():
    """Get backup audit status."""
    try:
        status = get_backup_status()
        return status
    except Exception as e:
        logger.error(f"Error getting backup status: {e}")
        return {"error": str(e), "status": "error"}


@app.get("/api/scaffolding/version")
async def api_scaffolding_version():
    """Get current scaffolding and rules versions."""
    scaffolding_version, rules_version = get_current_scaffolding_version()
    return {
        "scaffolding_version": scaffolding_version,
        "rules_version": rules_version
    }


@app.get("/api/projects")
async def api_projects():
    """JSON API for projects."""
    db = DatabaseManager()
    projects = db.get_all_projects(order_by="last_modified DESC")
    
    # Get current scaffolding version
    current_scaffolding, _ = get_current_scaffolding_version()
    
    # Enrich with related data
    enriched_projects = [enrich_project_data(p, db, current_scaffolding) for p in projects]
    
    return {"projects": enriched_projects}


@app.get("/api/alerts")
async def api_alerts():
    """Get all alerts."""
    db = DatabaseManager()
    projects = db.get_all_projects()
    
    # Get current scaffolding version
    current_scaffolding, _ = get_current_scaffolding_version()
    
    enriched_projects = [enrich_project_data(p, db, current_scaffolding) for p in projects]
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
    # Get current scaffolding version
    current_scaffolding, _ = get_current_scaffolding_version()
    
    enriched_projects = [enrich_project_data(p, db, current_scaffolding) for p in projects]
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


@app.get("/api/learning")
async def api_learning_stats():
    """Get learning activity statistics for all projects."""
    from learning_stats import get_all_learning_stats
    
    try:
        stats = get_all_learning_stats()
        
        # Calculate summary statistics
        total_with_learnings = sum(1 for s in stats if s['has_learnings'])
        total_entries = sum(s['total_entries'] for s in stats)
        stale_projects = sum(1 for s in stats if s['has_learnings'] and s['days_since_last_entry'] and s['days_since_last_entry'] > 30)
        
        # Get projects with recent activity (last 7 days)
        active_projects = [s for s in stats if s['has_learnings'] and s['days_since_last_entry'] is not None and s['days_since_last_entry'] <= 7]
        
        return {
            "summary": {
                "total_projects_with_learnings": total_with_learnings,
                "total_learning_entries": total_entries,
                "stale_projects": stale_projects,
                "active_projects_this_week": len(active_projects)
            },
            "projects": stats
        }
    except Exception as e:
        logger.error(f"Failed to get learning stats: {e}")
        return {
            "summary": {
                "total_projects_with_learnings": 0,
                "total_learning_entries": 0,
                "stale_projects": 0,
                "active_projects_this_week": 0
            },
            "projects": []
        }


# =============================================================================
# Calendar API
# =============================================================================

class CalendarEventCreate(BaseModel):
    title: str
    event_date: str
    event_time: Optional[str] = None
    event_type: str = "reminder"
    project_id: Optional[str] = None
    machine: Optional[str] = None
    prompt: Optional[str] = None
    description: Optional[str] = None
    notify_before_minutes: int = 60
    recurrence: Optional[str] = None
    created_by: str = "human"

    @staticmethod
    def _validate_date(v: str) -> str:
        from datetime import datetime
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"event_date must be YYYY-MM-DD, got '{v}'")
        return v

    # Pydantic v2 field validator
    try:
        from pydantic import field_validator
        @field_validator("event_date")
        @classmethod
        def validate_event_date(cls, v: str) -> str:
            return cls._validate_date(v)
    except ImportError:
        # Pydantic v1 fallback
        from pydantic import validator
        @validator("event_date")
        @classmethod  # type: ignore[misc]
        def validate_event_date(cls, v: str) -> str:
            return cls._validate_date(v)


def _get_cal_manager():
    from db.calendar_manager import CalendarManager
    cm = CalendarManager()
    cm.ensure_tables()
    return cm


@app.get("/api/calendar/events")
async def api_calendar_events(
    days: int = 30,
    project_id: Optional[str] = None,
    machine: Optional[str] = None,
    event_type: Optional[str] = None,
    include_all: bool = False,
):
    """Return upcoming calendar events."""
    days = max(1, min(days, 730))  # clamp: 1–730 days
    try:
        cm = _get_cal_manager()
        events = cm.get_events(
            days=days,
            project_id=project_id,
            machine=machine,
            event_type=event_type,
            include_all=include_all,
        )
        return {"events": events, "total": len(events)}
    except Exception as e:
        logger.error(f"Calendar events error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/calendar/events/{event_id}")
async def api_calendar_event_detail(event_id: int):
    """Return a single calendar event with linked tasks."""
    try:
        cm = _get_cal_manager()
        event = cm.get_event(event_id)
        if not event:
            raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
        return event
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Calendar event detail error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/calendar/events")
async def api_calendar_create(payload: CalendarEventCreate):
    """Create a calendar event."""
    try:
        cm = _get_cal_manager()
        event_id = cm.add_event(
            title=payload.title,
            event_date=payload.event_date,
            event_time=payload.event_time,
            event_type=payload.event_type,
            project_id=payload.project_id,
            machine=payload.machine,
            prompt=payload.prompt,
            description=payload.description,
            notify_before_minutes=payload.notify_before_minutes,
            recurrence=payload.recurrence,
            created_by=payload.created_by,
        )
        return {"id": event_id, "title": payload.title, "event_date": payload.event_date}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Calendar create error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/calendar/events/{event_id}/done")
async def api_calendar_done(event_id: int):
    """Mark calendar event as done."""
    try:
        cm = _get_cal_manager()
        if cm.mark_done(event_id):
            return {"ok": True}
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Calendar done error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/calendar/crons")
async def api_calendar_crons(
    project_id: Optional[str] = None,
    machine: Optional[str] = None,
):
    """Return all active cron jobs with machine designations."""
    try:
        cm = _get_cal_manager()
        crons = cm.get_cron_jobs(project_id=project_id, machine=machine)
        return {"cron_jobs": crons, "total": len(crons)}
    except Exception as e:
        logger.error(f"Calendar crons error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/calendar/remind")
async def api_calendar_remind(
    within_minutes: int = 60,
    machine: Optional[str] = None,
):
    """Events firing soon — for agent polling and notification widgets."""
    try:
        cm = _get_cal_manager()
        events = cm.get_upcoming_reminders(within_minutes=within_minutes, machine=machine)
        return {"events": events, "total": len(events), "within_minutes": within_minutes}
    except Exception as e:
        logger.error(f"Calendar remind error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


_graph_cache: Dict = {"data": None, "timestamp": 0, "params": None}
_GRAPH_CACHE_TTL = 300  # 5 minutes


@app.get("/graph", response_class=HTMLResponse)
async def graph_view(request: Request):
    """Render the graph visualization page."""
    return templates.TemplateResponse(request, "graph.html", build_template_context(request))


@app.get("/memory", response_class=HTMLResponse)
async def memory_view(request: Request):
    """Render the memory graph visualization page."""
    return templates.TemplateResponse(request, "memory.html", build_template_context(request))


@app.get("/api/memory-graph")
async def get_memory_graph_data(
    min_similarity: float = 0.3,   # Minimum similarity threshold for edges
    max_edges_per_node: int = 10   # Limit edges per node to keep response size reasonable
):
    """Return full memory graph JSON for client-side rendering.

    Type filtering is intentionally done client-side so the browser can
    switch filters instantly without a network round-trip.

    Uses numpy vectorized cosine similarity for ~1600x speedup over
    pure Python loops on large graphs.
    """
    now = _time()
    cache_key = (min_similarity, max_edges_per_node)
    if (_graph_cache["data"] is not None
            and now - _graph_cache["timestamp"] < _GRAPH_CACHE_TTL
            and _graph_cache["params"] == cache_key):
        return _graph_cache["data"]

    projects_root = Path(__file__).parent.parent.parent
    brain_db_path = projects_root / "ai-memory" / "brain.db"

    if not brain_db_path.exists():
        return JSONResponse({
            "error": f"Memory database not found. Expected at: {brain_db_path}"
        }, status_code=404)

    try:
        conn = sqlite3.connect(brain_db_path)
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            "SELECT id, content, embedding, metadata, created_at, source_machine FROM thoughts WHERE embedding IS NOT NULL"
        ).fetchall()
        conn.close()

        nodes = []
        embeddings = []

        for row in rows:
            metadata = json.loads(row["metadata"]) if row["metadata"] else {}
            embedding = json.loads(row["embedding"])
            thought_type_val = metadata.get("type", "observation")

            nodes.append({
                "id": str(row["id"]),
                "content": row["content"],
                "type": thought_type_val,
                "project": metadata.get("project", ""),
                "agent_family": metadata.get("agent_family", ""),
                "created_at": row["created_at"],
                "source_machine": row["source_machine"] or "",
                "size": 1
            })
            embeddings.append(embedding)

        # Vectorized cosine similarity via numpy
        edges = []
        connection_counts = {node["id"]: 0 for node in nodes}

        if embeddings:
            matrix = np.array(embeddings, dtype=np.float32)
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            normed = matrix / norms
            sim_matrix = normed @ normed.T
            np.fill_diagonal(sim_matrix, 0)

            # Edge extraction with threshold + top-k per node
            for i in range(len(nodes)):
                row = sim_matrix[i, i+1:]
                mask = row > min_similarity
                indices = np.where(mask)[0]
                values = row[mask]
                if len(values) > max_edges_per_node:
                    top_k = np.argpartition(values, -max_edges_per_node)[-max_edges_per_node:]
                    indices = indices[top_k]
                    values = values[top_k]
                for idx, sim_val in zip(indices, values):
                    j = int(idx) + i + 1
                    edges.append({
                        "source": nodes[i]["id"],
                        "target": nodes[j]["id"],
                        "similarity": round(float(sim_val), 3)
                    })
                    connection_counts[nodes[i]["id"]] += 1
                    connection_counts[nodes[j]["id"]] += 1

        for node in nodes:
            node["size"] = connection_counts[node["id"]]

        result = {
            "generated_at": datetime.now().isoformat(),
            "stats": {
                "total_thoughts": len(nodes),
                "total_connections": len(edges),
                "avg_connections": round(sum(connection_counts.values()) / len(nodes), 2) if nodes else 0
            },
            "nodes": nodes,
            "edges": edges
        }

        _graph_cache["data"] = result
        _graph_cache["timestamp"] = _time()
        _graph_cache["params"] = cache_key

        return result

    except Exception as e:
        logger.error(f"Error reading memory database: {e}")
        return JSONResponse({"error": f"Error reading memory data: {e}"}, status_code=500)


@app.get("/api/memory/types")
async def get_memory_types():
    """Return distinct thought types present in brain.db.

    Used by the frontend to populate filter dropdowns dynamically.
    """
    import json
    import sqlite3

    projects_root = Path(__file__).parent.parent.parent
    brain_db_path = projects_root / "ai-memory" / "brain.db"

    if not brain_db_path.exists():
        return {"types": ["observation", "decision", "idea", "question"]}

    try:
        conn = sqlite3.connect(brain_db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT DISTINCT json_extract(metadata, '$.type') AS thought_type FROM thoughts "
            "WHERE metadata IS NOT NULL ORDER BY thought_type"
        ).fetchall()
        conn.close()

        types = sorted(set(
            row["thought_type"] for row in rows
            if row["thought_type"] is not None
        ))
        # Always ensure the canonical types are present
        for t in ("observation", "decision", "idea", "question"):
            if t not in types:
                types.insert(0, t)

        return {"types": types}

    except Exception as e:
        logger.error(f"Error reading memory types: {e}")
        return {"types": ["observation", "decision", "idea", "question"]}


@app.get("/api/memory/heatmap")
async def get_memory_heatmap():
    """Return thought density grouped by date and type for the heatmap view.

    Returns rows of { date, type, count } sorted chronologically.
    """
    import json
    import sqlite3

    projects_root = Path(__file__).parent.parent.parent
    brain_db_path = projects_root / "ai-memory" / "brain.db"

    if not brain_db_path.exists():
        return {"rows": [], "error": "Memory database not found"}

    try:
        conn = sqlite3.connect(brain_db_path)
        conn.row_factory = sqlite3.Row

        rows = conn.execute("""
            SELECT
                date(created_at) AS day,
                json_extract(metadata, '$.type') AS thought_type,
                COUNT(*) AS count
            FROM thoughts
            WHERE metadata IS NOT NULL
            GROUP BY day, thought_type
            ORDER BY day ASC, thought_type ASC
        """).fetchall()
        conn.close()

        return {
            "rows": [
                {
                    "date": row["day"],
                    "type": row["thought_type"] or "observation",
                    "count": row["count"]
                }
                for row in rows
            ]
        }

    except Exception as e:
        logger.error(f"Error reading memory heatmap: {e}")
        return JSONResponse({"error": f"Error reading heatmap data: {e}"}, status_code=500)


@app.get("/api/graph")
async def get_graph_data(
    project: Optional[str] = None,      # Filter to single project
    file_types: Optional[str] = None,   # Comma-separated: "py,ts,md"
    include_orphans: bool = True,       # Show orphaned nodes
    min_connections: int = 0            # Filter by connection count
):
    """Return graph JSON for D3.js visualization."""
    import json
    graph_path = Path(__file__).parent.parent / "data" / "graph.json"
    if not graph_path.exists():
        return JSONResponse({
            "error": "Graph not built. Run: python scripts/discovery/graph_builder.py"
        }, status_code=404)

    try:
        graph = json.loads(graph_path.read_text())
    except Exception as e:
        logger.error(f"Error reading graph.json: {e}")
        return JSONResponse({"error": f"Error reading graph data: {e}"}, status_code=500)

    # Apply filters
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    # Filter by project
    if project:
        nodes = [n for n in nodes if n.get("project") == project]
        node_ids = {n["id"] for n in nodes}
        edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]

    # Filter by file types
    if file_types:
        allowed_types = [t.strip().lower() for t in file_types.split(',')]
        nodes = [n for n in nodes if n.get("type") in allowed_types]
        node_ids = {n["id"] for n in nodes}
        edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]

    # Filter orphans
    if not include_orphans:
        nodes = [n for n in nodes if not n.get("is_orphan")]
        node_ids = {n["id"] for n in nodes}
        edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]

    # Filter by min connections
    if min_connections > 0:
        nodes = [n for n in nodes if n.get("size", 0) >= min_connections]
        node_ids = {n["id"] for n in nodes}
        edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]

    return {
        "generated_at": graph.get("generated_at"),
        "stats": {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "orphan_count": len([n for n in nodes if n.get("is_orphan")])
        },
        "nodes": nodes,
        "edges": edges
    }


# Pydantic model for run request
class AgentRunRequest(BaseModel):
    agent_name: str
    command_name: str
    args: Optional[str] = ""


# Pydantic models for task requests
class TaskCreateRequest(BaseModel):
    text: str
    project_id: str
    status: Optional[str] = "Backlog"
    priority: Optional[str] = None
    task_type: Optional[str] = None
    parent_id: Optional[int] = None  # Task #4645
    blocked_by: Optional[List[int]] = None  # Task #4579


class TaskUpdateRequest(BaseModel):
    text: Optional[str] = None
    title: Optional[str] = None
    notes: Optional[str] = None
    commit_sha: Optional[str] = None
    category: Optional[str] = None
    review_comment: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    task_type: Optional[str] = None
    parent_id: Optional[int] = None  # Task #4645
    blocked_by: Optional[List[int]] = None  # Task #4579


# GET /api/loops - Get autonomous loop status
@app.get("/api/loops")
async def get_loop_status():
    """Return status of all autonomous loops."""
    db = DatabaseManager()
    
    loops = ["janitor", "librarian", "patch-bot"]
    status_data = []
    
    with db._get_conn() as conn:
        cursor = conn.cursor()
        
        for loop_name in loops:
            # Get last execution
            cursor.execute("""
                SELECT id, started_at, completed_at, status, cards_created, error_message
                FROM loop_executions
                WHERE loop_name = ?
                ORDER BY started_at DESC
                LIMIT 1
            """, (loop_name,))
            
            last_run = cursor.fetchone()
            
            if last_run:
                started = datetime.fromisoformat(last_run[1])
                completed = datetime.fromisoformat(last_run[2]) if last_run[2] else None
                
                # Calculate health status
                now = datetime.now()
                time_since_run = now - started
                
                # Expected intervals (in hours)
                expected_intervals = {
                    "janitor": 1,      # Hourly
                    "librarian": 6,    # Every 6 hours
                    "patch-bot": 0.5   # Every 30 minutes
                }
                
                expected_hours = expected_intervals.get(loop_name, 24)
                expected_delta = timedelta(hours=expected_hours)
                
                # Determine health
                if last_run[3] == "failed":
                    health = "failed"
                    health_icon = "🔴"
                elif time_since_run > expected_delta * 2:
                    health = "overdue"
                    health_icon = "🔴"
                elif time_since_run > expected_delta * 1.5:
                    health = "warning"
                    health_icon = "🟡"
                else:
                    health = "healthy"
                    health_icon = "🟢"
                
                status_data.append({
                    "loop": loop_name,
                    "health": health,
                    "health_icon": health_icon,
                    "last_run": started.isoformat(),
                    "last_run_human": format_time_ago(started.isoformat()),
                    "status": last_run[3],
                    "cards_created": last_run[4],
                    "duration_seconds": (completed - started).total_seconds() if completed else None,
                    "error": last_run[5] if last_run[5] else None
                })
            else:
                status_data.append({
                    "loop": loop_name,
                    "health": "never_run",
                    "health_icon": "⚪",
                    "last_run": None,
                    "last_run_human": "Never",
                    "status": "N/A",
                    "cards_created": 0,
                    "duration_seconds": None,
                    "error": None
                })
    
    return {"loops": status_data}


# GET /api/agents - List all agents
@app.get("/api/agents")
async def list_agents():
    """Return list of available agents and their commands."""
    agents = get_available_agents()
    return {
        "agents": [
            {
                "name": a.name,
                "description": a.description,
                "available": a.available,
                "commands": [
                    {
                        "name": c.name,
                        "description": c.description,
                        "args_template": c.args_template,
                        "dangerous": c.dangerous
                    }
                    for c in a.commands
                ]
            }
            for a in agents
        ]
    }



# POST /api/agents/run - Execute agent command
@app.post("/api/agents/run")
async def run_agent(request: AgentRunRequest):
    """Execute an agent command and return result."""
    result = run_agent_command(
        request.agent_name,
        request.command_name,
        request.args or ""
    )

    return {
        "success": result.success,
        "output": result.output,
        "error": result.error,
        "return_code": result.return_code,
        "duration_ms": result.duration_ms,
        "command": result.command
    }


# ==================== ERROR HANDLING MIDDLEWARE ====================

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handle validation errors (ValueError from DatabaseManager)."""
    error_message = str(exc)
    
    # Check if it's a validation error (contains common validation keywords)
    if any(keyword in error_message.lower() for keyword in [
        "must be", "invalid", "does not exist", "contains potential secret",
        "required", "too long", "too short"
    ]):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "validation_error",
                "message": error_message,
                "details": {
                    "field": _extract_field_from_error(error_message),
                    "pattern": _extract_pattern_from_error(error_message)
                }
            }
        )
    
    # Check if it's a not found error
    if "not found" in error_message.lower():
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": "not_found",
                "message": error_message
            }
        )
    
    # Default to 400 for other ValueError cases
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "validation_error",
            "message": error_message
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle FastAPI request validation errors."""
    errors = exc.errors()
    first_error = errors[0] if errors else {}

    # Debug logging
    try:
        body = await request.body()
        logger.error(f"Validation error for {request.method} {request.url.path}: {body.decode()}")
        logger.error(f"Errors: {errors}")
    except (UnicodeDecodeError, RuntimeError) as e:
        logger.debug(f"Could not read request body for logging: {e}")

    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "validation_error",
            "message": f"Invalid request: {first_error.get('msg', 'Validation failed')}",
            "details": {
                "field": ".".join(str(loc) for loc in first_error.get("loc", [])),
                "type": first_error.get("type", "unknown")
            }
        }
    )


@app.exception_handler(sqlite3.Error)
async def database_error_handler(request: Request, exc: sqlite3.Error):
    """Handle database errors."""
    logger.error(f"Database error: {exc}", exc_info=True)
    
    error_type = type(exc).__name__
    operation = "unknown"
    
    # Try to extract operation from request path
    if "/tasks" in str(request.url.path):
        if request.method == "POST":
            operation = "INSERT"
        elif request.method == "PATCH":
            operation = "UPDATE"
        elif request.method == "DELETE":
            operation = "DELETE"
        elif request.method == "GET":
            operation = "SELECT"
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "database_error",
            "message": "Failed to process request due to database error",
            "details": {
                "operation": operation,
                "table": "tasks",
                "error_type": error_type
            }
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors."""
    logger.error(f"Unexpected error: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_error",
            "message": "An unexpected error occurred"
        }
    )


def _extract_field_from_error(error_message: str) -> Optional[str]:
    """Extract field name from error message."""
    # Common patterns: "Task text...", "Project ID...", "Status...", "Priority..."
    if "task text" in error_message.lower() or "text" in error_message.lower():
        return "text"
    elif "project" in error_message.lower():
        return "project_id"
    elif "status" in error_message.lower():
        return "status"
    elif "priority" in error_message.lower():
        return "priority"
    return None


def _extract_pattern_from_error(error_message: str) -> Optional[str]:
    """Extract secret pattern from error message if present."""
    if "pattern:" in error_message.lower():
        parts = error_message.split("pattern:")
        if len(parts) > 1:
            return parts[1].strip()
    return None


# ==================== TASK API ENDPOINTS ====================

@app.post("/api/tasks", status_code=status.HTTP_201_CREATED)
async def create_task(task_data: TaskCreateRequest):
    """Create a new task.
    
    Args:
        task_data: Task creation data (text, project_id, status, priority)
        
    Returns:
        Created task object with ID and timestamps
        
    Raises:
        HTTPException: 400 if validation fails, 404 if project not found
    """
    try:
        db = DatabaseManager()
        
        # Convert blocked_by list to JSON string if provided
        blocked_by_json = None
        if task_data.blocked_by:
            import json
            blocked_by_json = json.dumps(task_data.blocked_by)
        
        task = db.add_task(
            text=task_data.text,
            project_id=task_data.project_id,
            status=task_data.status or "Backlog",
            priority=task_data.priority,
            task_type=task_data.task_type,
            parent_id=task_data.parent_id,
            blocked_by=blocked_by_json
        )
        return task
    except ValueError as e:
        # Re-raise to be caught by error handler
        raise
    except Exception as e:
        logger.error(f"Error creating task: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create task"
        )


@app.get("/api/tasks")
async def list_tasks(
    project_id: Optional[str] = None,
    task_status: Optional[str] = None,
    include_subtasks: bool = True,
    parent_id: Optional[int] = None
):
    """List tasks with optional filtering.

    Args:
        project_id: Filter by project ID (optional)
        task_status: Filter by status (optional)
        include_subtasks: Include subtasks in results (default: True)
        parent_id: Filter to subtasks of specific parent (optional)

    Returns:
        Dictionary with enriched tasks list and total count
    """
    try:
        import json
        db = DatabaseManager()
        tasks = db.get_tasks(project_id=project_id, status=task_status)

        # Filter by parent_id if specified
        if parent_id is not None:
            tasks = [t for t in tasks if t.get("parent_id") == parent_id]

        # Filter out subtasks if include_subtasks is False
        if not include_subtasks:
            tasks = [t for t in tasks if t.get("parent_id") is None]

        # Enrich each task with subtask info and blocking status
        # NOTE: Subtasks feature (#4645) is incomplete - methods not yet implemented
        enriched_tasks = []
        for task in tasks:
            task_dict = dict(task)

            # Add subtask progress if task is a parent (when implemented)
            if hasattr(db, 'get_subtasks'):
                subtasks = db.get_subtasks(task["id"])
                if subtasks:
                    task_dict["subtasks"] = subtasks
                    task_dict["subtask_progress"] = db.get_subtask_progress(task["id"])

            # Add blocking info if task has blocked_by (when implemented)
            if task.get("blocked_by") and hasattr(db, 'get_blocking_tasks'):
                try:
                    blocked_by_ids = json.loads(task["blocked_by"])
                    task_dict["blocked_by_ids"] = blocked_by_ids
                    task_dict["blocking_tasks"] = db.get_blocking_tasks(task["id"])
                    is_blocked, blocking_ids = db.is_blocked(task["id"])
                    task_dict["is_blocked"] = is_blocked
                    task_dict["incomplete_blocking_ids"] = blocking_ids
                except (json.JSONDecodeError, TypeError):
                    pass

            enriched_tasks.append(task_dict)

        return {
            "tasks": enriched_tasks,
            "total": len(enriched_tasks)
        }
    except Exception as e:
        logger.error(f"Error listing tasks: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve tasks"
        )


@app.delete("/api/tasks/done")
async def delete_done_tasks(project_id: Optional[str] = None):
    """Delete all tasks in Done status (disabled)."""
    logger.warning("Blocked API delete_done_tasks attempt")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Task deletions are disabled. Use manual DBA operations if needed."
    )


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: int):
    """Get a single task by ID with full enriched data.
    
    Args:
        task_id: Task ID
        
    Returns:
        Enriched task object with subtasks, parent, and blocking info
        
    Raises:
        HTTPException: 404 if task not found
    """
    try:
        import json
        db = DatabaseManager()
        task = db.get_task(task_id)
        
        if not task:
            raise ValueError(f"Task with ID {task_id} not found")
        
        task_dict = dict(task)
        
        # Add subtasks if this is a parent
        subtasks = db.get_subtasks(task_id)
        if subtasks:
            task_dict["subtasks"] = subtasks
            task_dict["subtask_progress"] = db.get_subtask_progress(task_id)
        
        # Add parent info if this is a subtask
        if task.get("parent_id"):
            parent = db.get_task(task["parent_id"])
            if parent:
                task_dict["parent"] = parent
        
        # Add blocking info if task has blocked_by
        if task.get("blocked_by"):
            try:
                blocked_by_ids = json.loads(task["blocked_by"])
                task_dict["blocked_by_ids"] = blocked_by_ids
                task_dict["blocking_tasks"] = db.get_blocking_tasks(task_id)
                is_blocked, blocking_ids = db.is_blocked(task_id)
                task_dict["is_blocked"] = is_blocked
                task_dict["incomplete_blocking_ids"] = blocking_ids
            except (json.JSONDecodeError, TypeError):
                pass
        
        return task_dict
    except ValueError as e:
        # Re-raise to be caught by error handler
        raise
    except Exception as e:
        logger.error(f"Error retrieving task {task_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve task"
        )


@app.patch("/api/tasks/{task_id}")
async def update_task(task_id: int, task_data: TaskUpdateRequest):
    """Update a task (text, status, priority).
    
    Args:
        task_id: Task ID
        task_data: Fields to update (text, status, priority)
        
    Returns:
        Updated task object
        
    Raises:
        HTTPException: 400 if validation fails, 404 if task not found
        
    Note:
        Status changes are automatically recorded in task_history.
    """
    try:
        db = DatabaseManager()
        
        # Build update dict from non-None fields
        updates = {}
        if task_data.text is not None:
            updates["text"] = task_data.text
        if task_data.title is not None:
            updates["title"] = task_data.title
        if task_data.notes is not None:
            updates["notes"] = task_data.notes
        if task_data.commit_sha is not None:
            updates["commit_sha"] = task_data.commit_sha
        if task_data.category is not None:
            updates["category"] = task_data.category
        if task_data.review_comment is not None:
            updates["review_comment"] = task_data.review_comment
        if task_data.status is not None:
            updates["status"] = task_data.status
        if task_data.priority is not None:
            updates["priority"] = task_data.priority
        if task_data.task_type is not None:
            updates["task_type"] = task_data.task_type
        if task_data.parent_id is not None:
            updates["parent_id"] = task_data.parent_id
        if task_data.blocked_by is not None:
            import json
            updates["blocked_by"] = json.dumps(task_data.blocked_by)
        
        # Prompt check for In Progress — warn but don't block
        if updates.get("status") == "In Progress":
            current = db.get_task(task_id)
            if not current:
                raise ValueError(f"Task with ID {task_id} not found")
            prompt_value = updates.get("prompt")
            if prompt_value is None:
                prompt_value = current.get("prompt")
            task_type_value = updates.get("task_type")
            if task_type_value is None:
                task_type_value = current.get("task_type") or "manual"
            if task_type_value == "agent" and not prompt_value:
                logger.warning(f"Agent task #{task_id} started without a prompt")
            is_blocked, blocking_ids = db.is_blocked(task_id)
            if is_blocked:
                blocking_str = ", ".join([f"#{bid}" for bid in blocking_ids])
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot start task while blocked by: {blocking_str}"
                )

        if not updates:
            # No updates provided, return current task
            task = db.get_task(task_id)
            if not task:
                raise ValueError(f"Task with ID {task_id} not found")
            return task
        
        # update_task handles history recording for status changes
        task = db.update_task(task_id, **updates)
        return task
    except ValueError as e:
        # Re-raise to be caught by error handler
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating task {task_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update task"
        )


@app.delete("/api/tasks/{task_id}", status_code=status.HTTP_200_OK)
async def delete_task(task_id: int):
    """Delete a single task."""
    try:
        db = DatabaseManager()
        db.delete_task(task_id)
        return {"deleted": True, "task_id": task_id}
    except ValueError as e:
        message = str(e)
        if "SAFE_MODE=1" in message:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=message
            )
        if "not found" in message.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )
    except Exception as e:
        logger.error(f"Error deleting task {task_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete task"
        )


# ==================== ATTACHMENT API ENDPOINTS (#5216) ====================

ATTACHMENT_MAX_BYTES = 20 * 1024 * 1024  # 20 MB


@app.post("/api/tasks/{task_id}/attachments", status_code=status.HTTP_201_CREATED)
async def upload_attachment(task_id: int, file: UploadFile = File(...)):
    """Upload a file and attach it to a task."""
    import mimetypes
    import shutil

    db = DatabaseManager()
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    # Stream to a temp file so we never hold >ATTACHMENT_MAX_BYTES in RAM
    import tempfile
    dest_dir = DatabaseManager._attachments_dir(task_id)
    ext = Path(file.filename or "upload").suffix
    stored_name = f"{uuid.uuid4()}{ext}"
    dest_path = dest_dir / stored_name

    size = 0
    with dest_path.open("wb") as out:
        while chunk := await file.read(65_536):  # 64 KB chunks
            size += len(chunk)
            if size > ATTACHMENT_MAX_BYTES:
                out.close()
                dest_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="File exceeds 20 MB limit")
            out.write(chunk)

    mime_type = file.content_type or mimetypes.guess_type(file.filename or "")[0]
    record = db.add_attachment(
        task_id=task_id,
        filename=file.filename or stored_name,
        stored_name=stored_name,
        mime_type=mime_type,
        size_bytes=size,
    )
    return record


@app.get("/api/tasks/{task_id}/attachments")
async def list_attachments(task_id: int):
    """List all attachments for a task."""
    db = DatabaseManager()
    if not db.get_task(task_id):
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return {"attachments": db.get_attachments(task_id)}


@app.delete("/api/tasks/{task_id}/attachments/{attachment_id}", status_code=status.HTTP_200_OK)
async def delete_attachment(task_id: int, attachment_id: int):
    """Delete an attachment record and its file from disk."""
    db = DatabaseManager()
    record = db.delete_attachment(attachment_id=attachment_id, task_id=task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Attachment not found")
    file_path = DatabaseManager._attachments_dir(task_id) / record["stored_name"]
    if file_path.exists():
        file_path.unlink()
    return {"deleted": True, "attachment_id": attachment_id}


@app.get("/api/attachments/{task_id}/{stored_name}")
async def serve_attachment(task_id: int, stored_name: str):
    """Serve an attachment file for inline preview."""
    from fastapi.responses import FileResponse
    import mimetypes
    attach_dir = DatabaseManager._attachments_dir(task_id)
    file_path = (attach_dir / stored_name).resolve()
    # Path traversal guard: resolved path must stay inside the task's attachment dir
    if not file_path.is_relative_to(attach_dir.resolve()):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    media_type = mimetypes.guess_type(stored_name)[0] or "application/octet-stream"
    return FileResponse(path=str(file_path), media_type=media_type)


@app.get("/api/agentic/summary")
async def agentic_summary(days: int = 30, project_id: Optional[str] = None):
    """Get agentic workflow metrics from task_history.

    Tracks Review -> In Progress bounces, Review -> Done promotions, and
    In Progress -> Review entries over time.
    """
    try:
        db = DatabaseManager()

        if days <= 0:
            days = 30

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days - 1)
        start_iso = start_date.isoformat()

        with db._get_conn() as conn:
            cursor = conn.cursor()
            if project_id:
                cursor.execute(
                    """
                    SELECT
                        DATE(timestamp) as date,
                        SUM(CASE WHEN old_status = 'Review' AND new_status = 'In Progress' THEN 1 ELSE 0 END) as review_bounces,
                        SUM(CASE WHEN old_status = 'Review' AND new_status = 'Done' THEN 1 ELSE 0 END) as review_promotions,
                        SUM(CASE WHEN old_status = 'In Progress' AND new_status = 'Review' THEN 1 ELSE 0 END) as review_entries
                    FROM task_history
                    WHERE timestamp >= ?
                      AND project_id = ?
                    GROUP BY DATE(timestamp)
                    ORDER BY date ASC
                    """,
                    (start_iso, project_id),
                )
            else:
                cursor.execute(
                    """
                    SELECT
                        DATE(timestamp) as date,
                        SUM(CASE WHEN old_status = 'Review' AND new_status = 'In Progress' THEN 1 ELSE 0 END) as review_bounces,
                        SUM(CASE WHEN old_status = 'Review' AND new_status = 'Done' THEN 1 ELSE 0 END) as review_promotions,
                        SUM(CASE WHEN old_status = 'In Progress' AND new_status = 'Review' THEN 1 ELSE 0 END) as review_entries
                    FROM task_history
                    WHERE timestamp >= ?
                    GROUP BY DATE(timestamp)
                    ORDER BY date ASC
                    """,
                    (start_iso,),
                )

            rows = cursor.fetchall()

        row_map = {row["date"]: row for row in rows}

        marker_path = Path(__file__).parent.parent / "data" / "agentic_markers.json"
        markers = []
        if marker_path.exists():
            try:
                marker_data = json.loads(marker_path.read_text())
                if isinstance(marker_data, list):
                    markers = [
                        m for m in marker_data
                        if isinstance(m, dict) and m.get("date") and m.get("label")
                    ]
            except Exception as e:
                logger.warning(f"Failed to load agentic markers: {e}")
        series = []
        totals = {"review_bounces": 0, "review_promotions": 0, "review_entries": 0}

        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.isoformat()
            row = row_map.get(date_str)
            entry = {
                "date": date_str,
                "review_bounces": int(row["review_bounces"]) if row else 0,
                "review_promotions": int(row["review_promotions"]) if row else 0,
                "review_entries": int(row["review_entries"]) if row else 0,
            }
            totals["review_bounces"] += entry["review_bounces"]
            totals["review_promotions"] += entry["review_promotions"]
            totals["review_entries"] += entry["review_entries"]
            series.append(entry)
            current_date += timedelta(days=1)

        review_total = totals["review_bounces"] + totals["review_promotions"]
        bounce_rate = (totals["review_bounces"] / review_total) if review_total else 0.0
        promotion_rate = (totals["review_promotions"] / review_total) if review_total else 0.0

        filtered_markers = [
            m for m in markers
            if start_date.isoformat() <= m["date"] <= end_date.isoformat()
        ]

        return {
            "summary": {
                "review_bounces": totals["review_bounces"],
                "review_promotions": totals["review_promotions"],
                "review_entries": totals["review_entries"],
                "bounce_rate": bounce_rate,
                "promotion_rate": promotion_rate,
            },
            "series": series,
            "markers": filtered_markers,
            "date_range": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "project_id": project_id,
        }
    except Exception as e:
        logger.error(f"Error building agentic summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to build agentic summary"
        )
# ==================== AGENTIC MARKERS API (#5009) ====================

MARKERS_PATH = Path(__file__).parent.parent / "data" / "agentic_markers.json"


def _load_markers() -> list:
    """Load markers from disk, returning empty list on any error."""
    if not MARKERS_PATH.exists():
        return []
    try:
        data = json.loads(MARKERS_PATH.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_markers(markers: list) -> None:
    """Atomically write markers to disk."""
    MARKERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = MARKERS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(markers, indent=2))
    tmp.replace(MARKERS_PATH)


class MarkerCreateRequest(BaseModel):
    date: str
    label: str
    source: str = "manual"
    agent: Optional[str] = None


class MarkerUpdateRequest(BaseModel):
    date: Optional[str] = None
    label: Optional[str] = None
    agent: Optional[str] = None


def _validate_marker_fields(date: Optional[str], label: Optional[str]) -> None:
    """Raise 400 if fields fail validation."""
    if date is not None:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    if label is not None:
        label = label.strip()
        if not label:
            raise HTTPException(status_code=400, detail="label must not be empty")
        if len(label) > 120:
            raise HTTPException(status_code=400, detail="label must be 120 characters or fewer")


@app.get("/api/agentic/markers")
async def get_markers():
    """Return all agentic markers."""
    return {"markers": _load_markers()}


@app.post("/api/agentic/markers", status_code=201)
async def create_marker(req: MarkerCreateRequest):
    """Create a new agentic marker."""
    _validate_marker_fields(req.date, req.label)
    markers = _load_markers()
    marker = {
        "id": str(uuid.uuid4()),
        "date": req.date,
        "label": req.label.strip(),
        "source": req.source if req.source in ("manual", "auto") else "manual",
        "agent": req.agent or None,
    }
    markers.append(marker)
    markers.sort(key=lambda m: m["date"])
    _save_markers(markers)
    return marker


@app.patch("/api/agentic/markers/{marker_id}")
async def update_marker(marker_id: str, req: MarkerUpdateRequest):
    """Update an existing agentic marker by id."""
    _validate_marker_fields(req.date, req.label)
    markers = _load_markers()
    for m in markers:
        if m.get("id") == marker_id:
            if req.date is not None:
                m["date"] = req.date
            if req.label is not None:
                m["label"] = req.label.strip()
            if req.agent is not None:
                m["agent"] = req.agent
            markers.sort(key=lambda x: x["date"])
            _save_markers(markers)
            return m
    raise HTTPException(status_code=404, detail="Marker not found")


@app.delete("/api/agentic/markers/{marker_id}", status_code=204)
async def delete_marker(marker_id: str):
    """Delete an agentic marker by id."""
    markers = _load_markers()
    updated = [m for m in markers if m.get("id") != marker_id]
    if len(updated) == len(markers):
        raise HTTPException(status_code=404, detail="Marker not found")
    _save_markers(updated)
    return None


# ==================== IDEAS API ENDPOINTS (Task #4583) ====================

class IdeaCreateRequest(BaseModel):
    text: str


class IdeaUpdateRequest(BaseModel):
    text: str


@app.get("/api/ideas")
async def get_ideas():
    """Get all ideas.
    
    Returns:
        List of all ideas ordered by creation date (newest first)
    """
    try:
        db = DatabaseManager()
        ideas = db.get_all_ideas()
        return {"ideas": ideas}
    except Exception as e:
        logger.error(f"Error fetching ideas: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch ideas"
        )


@app.post("/api/ideas", status_code=status.HTTP_201_CREATED)
async def create_idea(idea_data: IdeaCreateRequest):
    """Create a new idea.
    
    Args:
        idea_data: Idea creation data (text)
        
    Returns:
        Created idea with id and timestamps
        
    Raises:
        HTTPException: 400 if validation fails
    """
    try:
        db = DatabaseManager()
        idea = db.add_idea(idea_data.text)
        return idea
    except ValueError as e:
        # Re-raise to be caught by error handler
        raise
    except Exception as e:
        logger.error(f"Error creating idea: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create idea"
        )


@app.patch("/api/ideas/{idea_id}")
async def update_idea(idea_id: int, idea_data: IdeaUpdateRequest):
    """Update an idea's text.
    
    Args:
        idea_id: Idea ID
        idea_data: Updated text
        
    Returns:
        Updated idea
        
    Raises:
        HTTPException: 400 if validation fails, 404 if idea not found
    """
    try:
        db = DatabaseManager()
        idea = db.update_idea(idea_id, idea_data.text)
        return idea
    except ValueError as e:
        # Re-raise to be caught by error handler
        raise
    except Exception as e:
        logger.error(f"Error updating idea {idea_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update idea"
        )


@app.delete("/api/ideas/{idea_id}", status_code=status.HTTP_200_OK)
async def delete_idea(idea_id: int):
    """Delete an idea.
    
    Args:
        idea_id: Idea ID
        
    Returns:
        Success confirmation
        
    Raises:
        HTTPException: 404 if idea not found
    """
    try:
        db = DatabaseManager()
        db.delete_idea(idea_id)
        return {
            "success": True,
            "message": f"Idea {idea_id} deleted successfully"
        }
    except ValueError as e:
        # Re-raise to be caught by error handler
        raise
    except Exception as e:
        logger.error(f"Error deleting idea {idea_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete idea"
        )
