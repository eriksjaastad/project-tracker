"""FastAPI web dashboard for project tracker."""

import sys
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime
import subprocess

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler
)
import markdown
import sqlite3

# Add parent directory to path for logger import
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.logger import get_logger

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from db.manager import DatabaseManager
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
from scripts.config import REINDEX_SCRIPT_PATH

# Import scaffolding version helpers
from scripts.pt import get_current_scaffolding_version, compare_versions, rebuild_knowledge_graph

logger = get_logger(__name__)

app = FastAPI(title="Project Tracker Dashboard")

# Setup templates and static files
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

# Mount React frontend build
frontend_dist = Path(__file__).parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

@app.get("/kanban", response_class=HTMLResponse)
@app.get("/kanban/{project}", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def serve_react_app(request: Request):
    """Serve the React frontend for SPA routes."""
    index_path = frontend_dist / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(), status_code=200)
    else:
        # Fallback to old dashboard if React app not built
        return await dashboard(request)


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
    
    # Calculate version status
    # Exclude certain projects from scaffolding checks
    excluded_from_scaffolding = {
        'writing',           # Book/writing project - no code
        'ai-journal',        # Journal entries - has some code but shouldn't be scaffolded
        '_configs',          # Configuration files only
        '__knowledge',       # Knowledge base - no code
        '_tools',            # Tools directory - no code
        'fci-plugins',       # FCI plugins - don't scaffold
        'openclaw',          # External project - not ours
        'nanoclaw',          # External project - not ours
        'model-proving-ground'  # Renamed/stale project
    }
    
    project_id = project.get("id", "")
    project_path = Path(project.get("path", ""))
    
    if project_id in excluded_from_scaffolding:
        # Mark as current to hide from scaffolding alerts
        project["version_status"] = "current"
    elif not project_path.exists():
        # Project directory doesn't exist (stale/deleted)
        project["version_status"] = "current"
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
            except Exception:
                pass
        
        # Check for rogue 00-full-content.md in .agentsync/rules/
        rogue_file = project_path / ".agentsync" / "rules" / "00-full-content.md"
        if rogue_file.exists():
            scaffolding_issues.append("rogue 00-full-content.md in .agentsync/rules/")
        
        if scaffolding_issues:
            project["version_status"] = "outdated"
            project["scaffolding_issues"] = scaffolding_issues
        elif project_version is None:
            project["version_status"] = "unscaffolded"
        elif current_scaffolding_version and compare_versions(project_version, current_scaffolding_version) < 0:
            project["version_status"] = "outdated"
        else:
            project["version_status"] = "current"
    
    return project


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Serve the Jinja dashboard."""
    return await dashboard(request)

@app.get("/old", response_class=HTMLResponse)
async def react_frontend(request: Request):
    """Serve the React frontend or fallback to Jinja dashboard."""
    index_path = frontend_dist / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(), status_code=200)
    return await dashboard(request)

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
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "projects": enriched_projects,
        "alerts": alerts,
        "code_reviews": code_reviews,
        "total_projects": len(projects),
        "indexed_count": indexed_count,
        "compliance_pct": compliance_pct,
        "audit_available": audit_available,
        "agents": agents_data,
        "backup_status": backup_status,
        "current_scaffolding_version": current_scaffolding,
        "outdated_projects": outdated_projects,
        "unscaffolded_projects": unscaffolded_projects,
        "outdated_count": len(outdated_projects),
        "unscaffolded_count": len(unscaffolded_projects)
    })


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
    
    return templates.TemplateResponse("project_detail.html", {
        "request": request,
        "project": project
    })


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

        # Rebuild knowledge graph so dashboard is up to date
        rebuild_knowledge_graph()

        return JSONResponse({
            "status": "success",
            "message": f"Refreshed {len(projects)} projects and rebuilt graph"
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


@app.get("/graph", response_class=HTMLResponse)
async def graph_view(request: Request):
    """Render the graph visualization page."""
    return templates.TemplateResponse("graph.html", {"request": request})


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
