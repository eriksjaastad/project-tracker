"""FastAPI web dashboard for project tracker."""

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import os
import shutil
import subprocess
import threading
import httpx

from fastapi import FastAPI, Request, HTTPException, status, UploadFile, File, BackgroundTasks, Query
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.background import BackgroundTask
from fastapi.exceptions import RequestValidationError
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
from discovery.project_scanner import discover_projects
from discovery.alert_detector import get_all_alerts
from discovery.code_review_parser import parse_code_review
from discovery.providers import get_provider
from discovery.telemetry_reader import get_telemetry_stats
from discovery.backup_reader import get_backup_status
from discovery.agent_registry import (
    get_available_agents,
    run_agent_command
)
from pydantic import BaseModel

# Import config
from scripts.config import PROJECTS_BASE_DIR, REINDEX_SCRIPT_PATH
from scripts.utils.validation import get_blocked_card_reason, get_blocked_card_project_ids, is_card_creation_allowed

from scripts.pt import rebuild_project_graph

logger = get_logger(__name__)

@asynccontextmanager
async def _lifespan(application: FastAPI):
    """Lifespan handler: rebuild project graph in background after server starts."""
    def _rebuild():
        try:
            from scripts.pt import rebuild_project_graph
            logger.info("Background graph rebuild starting...")
            rebuild_project_graph()
            logger.info("Background graph rebuild complete.")
        except Exception as e:
            logger.error(f"Background graph rebuild failed: {e}")

    thread = threading.Thread(target=_rebuild, daemon=True, name="graph-rebuild")
    thread.start()
    yield  # server is running
    # shutdown: nothing to clean up (daemon thread dies with process)


app = FastAPI(title="Project Tracker Dashboard", lifespan=_lifespan)

# Run idempotent migrations on startup
try:
    DatabaseManager().migrate_attachments_table()
except Exception as _mig_err:
    logger.warning(f"Attachments migration skipped: {_mig_err}")

# Setup templates and static files
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


def _friendly_time(value: str) -> str:
    """Convert ISO timestamp to '3:14 PM  Mar 26' style."""
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        # Convert to local time
        local_dt = dt.astimezone()
        return local_dt.strftime("%-I:%M %p  %b %-d")
    except (ValueError, TypeError):
        return value


templates.env.filters["friendly_time"] = _friendly_time

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
        "navigation_type": "spa",
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


_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def _is_loopback_host(host: Optional[str]) -> bool:
    """Return True when the host is local to this machine."""
    return bool(host and host in _LOOPBACK_HOSTS)


def _require_local_admin_request(request: Request) -> None:
    """Restrict sensitive execution endpoints to loopback by default."""
    if os.getenv("PT_ALLOW_REMOTE_ADMIN") == "1":
        return

    client_host = request.client.host if request.client else None
    if _is_loopback_host(client_host):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="This endpoint is restricted to local requests. Set PT_ALLOW_REMOTE_ADMIN=1 to override.",
    )


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

    # Fallback when the frontend bundle is not built.
    return HTMLResponse(
        content="<h1>Frontend not built</h1><p>Run <code>npm run build</code> in dashboard/frontend/</p>",
        status_code=503,
    )


@app.get("/dashboard", response_class=HTMLResponse)
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

    project["version_status"] = "unmanaged"

    return project


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Redirect the root route to the canonical dashboard URL."""
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

@app.get("/old", response_class=HTMLResponse)
async def react_frontend():
    """Redirect the legacy SPA entry to the canonical Kanban route."""
    return RedirectResponse(url="/kanban", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

# ---------------------------------------------------------------------------
# Dashboard cache — stale-while-revalidate
# ---------------------------------------------------------------------------
_dashboard_cache: Dict = {"data": None, "timestamp": 0}
_DASHBOARD_CACHE_TTL = 300  # 5 minutes — matches the page auto-refresh
_dashboard_refresh_lock = threading.Lock()
_dashboard_refreshing = False


def _group_by_project(rows: List[Dict], key: str = "project_id") -> Dict[str, List[Dict]]:
    """Group a flat list of row dicts by project_id for O(1) per-project lookup."""
    grouped: Dict[str, List[Dict]] = {}
    for row in rows:
        pid = row.get(key, "")
        grouped.setdefault(pid, []).append(row)
    return grouped


_ALERT_TYPE_LABELS = {
    "rules_drift": "Rules Drift",
    "missing_index": "Missing Index",
    "stalled": "Stalled Projects",
    "blocked": "Project Blocked",
    "code_review": "Code Review",
    "cron_execution_error": "Cron Errors",
    "cron_missed_run": "Cron Missed Runs",
    "stale_heartbeat": "Stale Heartbeats",
    "telemetry_error": "Telemetry Errors",
    "unknown_status": "Unknown Status",
}

_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def _group_alerts_by_type(alerts: List[Dict]) -> List[Dict]:
    """Group flat alerts into collapsible type groups for the template.

    Returns a list of groups sorted by worst severity then count, each with:
        type, label, severity (worst in group), count, items, collapsed (bool).
    """
    groups_map: Dict[str, Dict] = {}
    for alert in alerts:
        atype = alert["type"]
        if atype not in groups_map:
            groups_map[atype] = {
                "type": atype,
                "label": _ALERT_TYPE_LABELS.get(atype, atype.replace("_", " ").title()),
                "severity": alert["severity"],
                "items": [],
            }
        group = groups_map[atype]
        group["items"].append(alert)
        # Escalate group severity to worst member
        if _SEVERITY_ORDER.get(alert["severity"], 9) < _SEVERITY_ORDER.get(group["severity"], 9):
            group["severity"] = alert["severity"]

    groups = list(groups_map.values())
    for g in groups:
        g["count"] = len(g["items"])
        g["collapsed"] = g["severity"] != "critical"

    groups.sort(key=lambda g: (_SEVERITY_ORDER.get(g["severity"], 9), -g["count"]))
    return groups


def _bulk_enrich(projects: List[dict], db: DatabaseManager) -> List[dict]:
    """Enrich all projects using bulk-fetched data (4 DB queries instead of 4N).

    Populates: ai_agents, cron_jobs, services, tasks, code_review,
    and time formatting fields.
    """
    all_agents = _group_by_project(db.get_ai_agents())
    all_crons = _group_by_project(db.get_cron_jobs())
    all_services = _group_by_project(db.get_services())
    all_tasks = _group_by_project(db.get_tasks())
    all_project_info_entries = db.get_info(project_id="__all__")
    project_info_by_project: dict[str, dict[str, str]] = {}
    for entry in all_project_info_entries:
        project_id = entry.get("project_id")
        key = entry.get("key")
        if not project_id or not key:
            logger.warning("Skipping malformed project_info row: %s", entry)
            continue
        project_info_by_project.setdefault(project_id, {})[key] = entry.get("value", "")

    for project in projects:
        pid = project["id"]

        # AI agents
        agents = all_agents.get(pid, [])
        project["ai_agents"] = [a["agent_name"] for a in agents]

        # Cron jobs
        jobs = all_crons.get(pid, [])
        project["has_cron"] = len(jobs) > 0
        project["cron_jobs"] = jobs

        # Services
        services = all_services.get(pid, [])
        project["services"] = [s["service_name"] for s in services]
        project["service_details"] = services
        project["services_by_category"] = categorize_services(services)

        # Tasks
        tasks = all_tasks.get(pid, [])
        open_tasks = [t for t in tasks if t.get("status") != "Done"]
        project["task_count"] = len(open_tasks)
        project["total_tasks"] = len(tasks)
        project["backlog_count"] = len([t for t in tasks if t.get("status") == "Backlog"])
        project["todo_count"] = len([t for t in tasks if t.get("status") == "To Do"])
        project["in_progress_count"] = len([t for t in tasks if t.get("status") == "In Progress"])
        project["review_count"] = len([t for t in tasks if t.get("status") == "Review"])

        # Code review (filesystem — kept per-project, cheap)
        review_path = Path(project["path"]) / "CODE_REVIEW.md"
        if review_path.exists():
            review_data = parse_code_review(review_path)
            if review_data and review_data.get("completion_pct", 100) < 100:
                project["code_review"] = review_data

        # Time formatting
        project["last_modified_human"] = format_time_ago(project.get("last_modified", ""))
        if project.get("index_updated_at"):
            project["index_updated_human"] = format_time_ago(project["index_updated_at"])

        # Agent config health
        project_info = project_info_by_project.get(pid, {})
        project["portfolio_group"] = project_info.get("portfolio_group")
        project["portfolio_label"] = project_info.get("portfolio_label")
        project["portfolio_parent"] = project_info.get("portfolio_parent")
        project["version_status"] = "unmanaged"

    return projects


def _sync_portfolio_project_info(db: DatabaseManager, cursor, project: dict) -> None:
    """Persist tracker-owned portfolio metadata without overwriting other project info."""
    db._replace_project_info_entries_with_cursor(
        cursor,
        project["id"],
        {
            "portfolio_group": project.get("portfolio_group"),
            "portfolio_label": project.get("portfolio_label"),
            "portfolio_parent": project.get("portfolio_parent"),
        },
    )


def _collect_task_display_ids(task_payload: dict, acc: set[int]) -> None:
    """Collect task ids referenced by a task payload, including nested relations."""
    task_id = task_payload.get("id")
    if isinstance(task_id, int):
        acc.add(task_id)

    parent_id = task_payload.get("parent_id")
    if isinstance(parent_id, int):
        acc.add(parent_id)

    for key in ("blocked_by_ids", "incomplete_blocking_ids"):
        for ref_id in task_payload.get(key, []) or []:
            if isinstance(ref_id, int):
                acc.add(ref_id)

    parent = task_payload.get("parent")
    if isinstance(parent, dict):
        _collect_task_display_ids(parent, acc)

    for nested_key in ("subtasks", "blocking_tasks"):
        for nested_task in task_payload.get(nested_key, []) or []:
            if isinstance(nested_task, dict):
                _collect_task_display_ids(nested_task, acc)


def _apply_task_display_ids(task_payload: dict, display_map: dict[int, int]) -> dict:
    """Attach human display ids to a task payload recursively."""
    task_id = task_payload.get("id")
    if isinstance(task_id, int):
        task_payload["display_id"] = display_map.get(task_id, task_id)

    parent_id = task_payload.get("parent_id")
    if isinstance(parent_id, int):
        task_payload["parent_display_id"] = display_map.get(parent_id, parent_id)

    blocked_by_ids = task_payload.get("blocked_by_ids")
    if isinstance(blocked_by_ids, list):
        task_payload["blocked_by_display_ids"] = [
            display_map.get(ref_id, ref_id) for ref_id in blocked_by_ids if isinstance(ref_id, int)
        ]

    incomplete_ids = task_payload.get("incomplete_blocking_ids")
    if isinstance(incomplete_ids, list):
        task_payload["incomplete_blocking_display_ids"] = [
            display_map.get(ref_id, ref_id) for ref_id in incomplete_ids if isinstance(ref_id, int)
        ]

    parent = task_payload.get("parent")
    if isinstance(parent, dict):
        task_payload["parent"] = _apply_task_display_ids(parent, display_map)

    for nested_key in ("subtasks", "blocking_tasks"):
        nested_tasks = task_payload.get(nested_key)
        if isinstance(nested_tasks, list):
            task_payload[nested_key] = [
                _apply_task_display_ids(nested_task, display_map)
                for nested_task in nested_tasks
                if isinstance(nested_task, dict)
            ]

    return task_payload


def _enrich_task_payloads_with_display_ids(tasks: list[dict], db: DatabaseManager) -> list[dict]:
    """Bulk-attach display ids to task payloads."""
    task_ids: set[int] = set()
    for task in tasks:
        _collect_task_display_ids(task, task_ids)
    display_map = db.get_task_display_id_map(list(task_ids))
    return [_apply_task_display_ids(task, display_map) for task in tasks]


def _build_dashboard_data() -> Dict:
    """Compute all dashboard context data (the expensive part)."""
    db = DatabaseManager()
    projects = db.get_all_projects(order_by="last_modified DESC")

    enriched_projects = _bulk_enrich(projects, db)
    alerts = get_all_alerts(enriched_projects)

    indexed_count = len([p for p in enriched_projects if p.get("has_index") and p.get("index_is_valid")])
    compliance_pct = int((indexed_count / len(projects)) * 100) if projects else 0

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

    backup_status = get_backup_status()

    # Collect code reviews populated by _bulk_enrich (see line ~483 for identical
    # exists() + parse + completion_pct guards — removes duplicate file reads)
    code_reviews = []
    for project in enriched_projects:
        if project.get("code_review"):
            code_reviews.append({
                "project_id": project["id"],
                "project_name": project["name"],
                **project["code_review"],
            })

    # Group alerts by type for collapsible display
    alert_groups = _group_alerts_by_type(alerts)

    return {
        "projects": enriched_projects,
        "alerts": alerts,
        "alert_groups": alert_groups,
        "code_reviews": code_reviews,
        "total_projects": len(projects),
        "indexed_count": indexed_count,
        "compliance_pct": compliance_pct,
        "agents": agents_data,
        "backup_status": backup_status,
    }


def _refresh_dashboard_cache() -> None:
    """Refresh the dashboard cache in a background thread."""
    global _dashboard_refreshing
    if not _dashboard_refresh_lock.acquire(blocking=False):
        return  # Another refresh is already running
    try:
        data = _build_dashboard_data()
        _dashboard_cache["data"] = data
        _dashboard_cache["timestamp"] = _time()
    except Exception as exc:
        logger.error(f"Background dashboard refresh failed: {exc}")
    finally:
        _dashboard_refreshing = False
        _dashboard_refresh_lock.release()


# NOTE: The /dashboard HTML route is now served by the React SPA via serve_react_app().
# The Jinja2 template rendering was removed as part of the SPA migration (#5372).
# Dashboard data APIs (e.g. /api/dashboard-cache-status) are preserved below.


@app.get("/api/dashboard-cache-status")
async def dashboard_cache_status():
    """Lightweight endpoint for the frontend to poll refresh progress."""
    ts = _dashboard_cache["timestamp"]
    return {
        "cached": _dashboard_cache["data"] is not None,
        "age": int(_time() - ts) if ts else None,
        "refreshing": _dashboard_refreshing,
        "timestamp": int(ts) if ts else None,
    }


@app.get("/project/{project_id}", response_class=HTMLResponse)
async def project_detail(request: Request, project_id: str):
    """Project detail view."""
    db = DatabaseManager()
    project = db.get_project(project_id)
    
    if not project:
        return HTMLResponse(content="<h1>Project not found</h1>", status_code=404)
    
    # Enrich with related data
    project = enrich_project_data(project, db)
    
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
            subprocess.run(
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
    """Call audit fix for a specific project's CLAUDE.md file."""
    db = DatabaseManager()
    project = db.get_project(project_id)
    if not project:
        return JSONResponse({"success": False, "error": "Project not found"}, status_code=404)

    # Find CLAUDE.md or README.md
    project_path = Path(project["path"])
    target_file = project_path / "CLAUDE.md"
    if not target_file.exists():
        target_file = project_path / "README.md"
    if not target_file.exists():
        return JSONResponse({"success": False, "error": "No CLAUDE.md or README.md found"}, status_code=404)

    provider = get_provider()
    try:
        success = provider.fix_file(str(target_file))
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
            with db._get_conn() as conn:
                cursor = conn.cursor()
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
                conn.commit()

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

        # Rebuild project graph in background under a tracked job so the
        # frontend can poll /api/rebuild-status/{job_id} for real completion.
        job_id = _create_rebuild_job("project_graph")
        return JSONResponse(
            {
                "status": "success",
                "message": f"Refreshed {len(projects)} projects, removed {removed} stale. Graph rebuild started in background.",
                "job_id": job_id,
            },
            background=BackgroundTask(_run_tracked_rebuild, job_id, rebuild_project_graph),
        )
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
        return JSONResponse({"error": "Failed to get backup status", "status": "error"}, status_code=500)


@app.get("/api/projects")
async def api_projects():
    """JSON API for projects."""
    db = DatabaseManager()
    projects = db.get_all_projects(order_by="last_modified DESC")
    
    # Enrich with related data (bulk — 4 queries instead of 4N)
    enriched_projects = _bulk_enrich(projects, db)

    for project in enriched_projects:
        project["can_create_cards"] = is_card_creation_allowed(project["id"])
        project["blocked_card_reason"] = get_blocked_card_reason(project["id"])

    return {"projects": enriched_projects}


@app.get("/api/task-policy")
async def api_task_policy():
    """Return backend-owned task creation policy metadata for clients."""
    blocked_ids = get_blocked_card_project_ids()
    blocked_reasons = {project_id: get_blocked_card_reason(project_id) for project_id in blocked_ids}
    return {
        "blocked_project_ids": blocked_ids,
        "blocked_project_reasons": blocked_reasons,
    }


@app.get("/api/alerts")
async def api_alerts():
    """Get all alerts."""
    db = DatabaseManager()
    projects = db.get_all_projects()
    
    enriched_projects = _bulk_enrich(projects, db)
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
    
    # Bulk-fetch cron and agent counts (2 queries instead of 2N)
    all_crons = _group_by_project(db.get_cron_jobs())
    all_agents_map = _group_by_project(db.get_ai_agents())
    projects_with_cron = sum(1 for p in projects if p["id"] in all_crons)
    projects_with_ai = sum(1 for p in projects if p["id"] in all_agents_map)

    # Get alert counts
    enriched_projects = _bulk_enrich(projects, db)
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


# --- API Cost Proxy (#5447) ---

_COST_TRACKER_BASE = "https://api.synthinsightlabs.com"

_COST_PROXY_ALLOWED_PATHS = {"daily", "providers", "projects", "models", "callers", "usage"}


@app.get("/api/costs/{path:path}")
async def proxy_costs(path: str, request: Request):
    """Proxy requests to the SIL cost tracker API."""

    # Validate path against allowlist to prevent SSRF and path traversal
    import posixpath
    normalized = posixpath.normpath(path).lstrip("/")
    if ".." in normalized or normalized == "." or not normalized:
        raise HTTPException(status_code=400, detail="Invalid cost endpoint path")
    root_segment = normalized.split("/")[0]
    if root_segment not in _COST_PROXY_ALLOWED_PATHS:
        raise HTTPException(status_code=400, detail=f"Unknown cost endpoint: {path}")

    url = f"{_COST_TRACKER_BASE}/{normalized}"
    if request.query_params:
        url += f"?{request.query_params}"

    # Read API key at request time so Doppler rotations and env changes
    # take effect without restarting the dashboard.
    api_key = os.getenv("COST_TRACKER_API_KEY", "")
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            return JSONResponse(resp.json(), status_code=resp.status_code)
    except httpx.TimeoutException:
        logger.warning("Cost tracker proxy timed out")
        return JSONResponse({"error": "Cost tracker timed out", "data": []}, status_code=504)
    except httpx.RequestError as e:
        logger.warning(f"Cost tracker proxy error: {e}")
        return JSONResponse({"error": "Cost tracker unavailable", "data": []}, status_code=502)


# --- Section ---
# Shadow Pricing API
# --- Section ---


@app.get("/api/shadow-pricing")
async def shadow_pricing():
    """Shadow pricing: what Claude Max usage would cost at API rates."""
    from dashboard.shadow_pricing import get_shadow_pricing_data
    try:
        data = get_shadow_pricing_data()
        return JSONResponse(data)
    except FileNotFoundError as e:
        logger.warning(f"Shadow pricing file not found: {e}")
        return JSONResponse({"error": str(e), "data": {}}, status_code=404)
    except Exception as e:
        logger.warning(f"Shadow pricing error: {e}")
        return JSONResponse({"error": "Shadow pricing unavailable", "data": {}}, status_code=500)


# --- Section ---
# Calendar API
# --- Section ---

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


def _invalidate_graph_cache() -> None:
    """Drop the /api/memory-graph in-memory cache so the next request recomputes."""
    _graph_cache["data"] = None
    _graph_cache["timestamp"] = 0
    _graph_cache["params"] = None


# ---- Rebuild job tracker -------------------------------------------------
# Tracks in-flight rebuild jobs so the frontend can poll real completion
# status instead of guessing via node-count diffs. Job dicts live for the
# lifetime of the process; they're small and self-expire on restart.
_rebuild_jobs: Dict[str, Dict] = {}


def _run_tracked_rebuild(job_id: str, fn) -> None:
    """Run a rebuild function with status tracking. Invalidates graph cache on success."""
    job = _rebuild_jobs.get(job_id)
    if job is None:
        return
    job["status"] = "running"
    job["started_at"] = datetime.now().isoformat()
    try:
        fn()
        job["status"] = "done"
        job["error"] = None
        _invalidate_graph_cache()
    except Exception as e:
        logger.error(f"Rebuild job {job_id} ({job.get('kind')}) failed: {e}")
        job["status"] = "error"
        job["error"] = str(e)
    finally:
        job["finished_at"] = datetime.now().isoformat()


def _create_rebuild_job(kind: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    _rebuild_jobs[job_id] = {
        "job_id": job_id,
        "kind": kind,
        "status": "queued",
        "started_at": None,
        "finished_at": None,
        "error": None,
    }
    return job_id


@app.get("/api/rebuild-status/{job_id}")
async def get_rebuild_status(job_id: str):
    """Poll status of a rebuild job. Returns 404 if unknown job."""
    job = _rebuild_jobs.get(job_id)
    if job is None:
        return JSONResponse({"error": "unknown job_id"}, status_code=404)
    return job


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
    max_edges_per_node: int = 10,  # Limit edges per node to keep response size reasonable
    max_nodes: int = 1000          # Cap nodes to prevent N×N memory explosion
):
    """Return full memory graph JSON for client-side rendering.

    Type filtering is intentionally done client-side so the browser can
    switch filters instantly without a network round-trip.

    Uses numpy vectorized cosine similarity for ~1600x speedup over
    pure Python loops on large graphs.
    """
    now = _time()
    cache_key = (min_similarity, max_edges_per_node, max_nodes)
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
            "SELECT id, content, embedding, metadata, created_at, source_machine FROM thoughts WHERE embedding IS NOT NULL ORDER BY created_at DESC LIMIT ?",
            (max_nodes,)
        ).fetchall()
        total_in_db = conn.execute("SELECT COUNT(*) FROM thoughts").fetchone()[0]
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
            # Drop raw Python lists immediately — numpy has its own copy
            del embeddings
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            normed = matrix / norms
            del matrix, norms  # free before allocating N×N
            sim_matrix = normed @ normed.T
            del normed  # free N×D before iterating N×N
            np.fill_diagonal(sim_matrix, 0)

            # Edge extraction with threshold + top-k per node
            for i in range(len(nodes)):
                row_slice = sim_matrix[i, i+1:]
                mask = row_slice > min_similarity
                indices = np.where(mask)[0]
                values = row_slice[mask]
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
            del sim_matrix

        for node in nodes:
            node["size"] = connection_counts[node["id"]]

        result = {
            "generated_at": datetime.now().isoformat(),
            "stats": {
                "total_thoughts": len(nodes),
                "total_in_db": total_in_db,
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


@app.get("/api/open-brain")
@app.get("/api/knowledge-graph")  # legacy alias
async def get_open_brain_graph(request: Request):
    """Return the Open Brain graph from brain.db (graph_nodes + graph_edges).

    Query params:
        min_mentions: Minimum mention_count to include a node (default: 1, show all).
                      Edges where either endpoint is filtered out are also removed.
        cluster:      "auto" (default) clusters dust nodes when total > 2000,
                      "off" disables clustering, "on" forces it.
    """
    min_mentions = int(request.query_params.get("min_mentions", 1))
    cluster_mode = request.query_params.get("cluster", "auto")
    projects_root = Path(__file__).parent.parent.parent
    brain_db_path = projects_root / "ai-memory" / "brain.db"

    if not brain_db_path.exists():
        return JSONResponse({"error": "brain.db not found"}, status_code=404)

    try:
        with sqlite3.connect(brain_db_path) as conn:
            conn.row_factory = sqlite3.Row

            nodes = [dict(r) for r in conn.execute(
                "SELECT id, type, name, description, mention_count as size FROM graph_nodes WHERE mention_count >= ?",
                (min_mentions,)
            ).fetchall()]

            node_ids = {n["id"] for n in nodes}

            # Optimized edge query: use a temp table to filter in SQL instead of
            # fetching all 80K+ edges and filtering in Python.
            conn.execute("CREATE TEMP TABLE _visible_ids (id INTEGER PRIMARY KEY)")
            conn.executemany("INSERT INTO _visible_ids VALUES (?)", [(nid,) for nid in node_ids])
            edges = [dict(r) for r in conn.execute(
                "SELECT e.source_node_id as source, e.target_node_id as target, e.type, e.weight "
                "FROM graph_edges e "
                "INNER JOIN _visible_ids s ON e.source_node_id = s.id "
                "INNER JOIN _visible_ids t ON e.target_node_id = t.id"
            ).fetchall()]

        # Server-side clustering: aggregate low-value nodes into type-based clusters
        should_cluster = (
            cluster_mode == "on"
            or (cluster_mode == "auto" and len(nodes) > 2000)
        )
        if should_cluster:
            nodes, edges = _cluster_dust_nodes(nodes, edges)

        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "clustered": should_cluster,
            }
        }
    except Exception as e:
        logger.error(f"Open Brain graph error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


def _cluster_dust_nodes(nodes: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    """Collapse low-signal nodes into per-type aggregate clusters.

    Dust = mention_count <= 2 AND degree <= 5. These get grouped by type
    into a single cluster node per type, reducing rendered node count.
    """
    from collections import defaultdict

    # Count degree per node
    degree = defaultdict(int)
    for e in edges:
        degree[e["source"]] += 1
        degree[e["target"]] += 1

    # Identify dust nodes
    dust_ids = set()
    dust_by_type = defaultdict(list)
    for n in nodes:
        if n["size"] <= 2 and degree.get(n["id"], 0) <= 5:
            dust_ids.add(n["id"])
            dust_by_type[n["type"]].append(n)

    if not dust_ids:
        return nodes, edges

    # Build cluster nodes (negative IDs to avoid collisions)
    cluster_id_map = {}  # dust node id -> cluster id
    cluster_nodes = []
    for i, (ntype, dust_nodes) in enumerate(dust_by_type.items()):
        if len(dust_nodes) < 3:
            continue  # not worth clustering 1-2 nodes
        cluster_id = -(i + 1)
        for dn in dust_nodes:
            cluster_id_map[dn["id"]] = cluster_id
        cluster_nodes.append({
            "id": cluster_id,
            "type": ntype,
            "name": f"{len(dust_nodes)} {ntype}s (low-ref)",
            "description": f"Cluster of {len(dust_nodes)} {ntype} nodes with low references",
            "size": len(dust_nodes),
            "is_cluster": True,
            "cluster_count": len(dust_nodes),
        })

    # Keep non-dust nodes + add cluster nodes
    kept_nodes = [n for n in nodes if n["id"] not in cluster_id_map]
    kept_nodes.extend(cluster_nodes)

    # Rewrite edges: remap dust endpoints to their cluster
    seen_edges = set()
    kept_edges = []
    for e in edges:
        src = cluster_id_map.get(e["source"], e["source"])
        tgt = cluster_id_map.get(e["target"], e["target"])
        if src == tgt:
            continue  # skip self-loops within a cluster
        edge_key = (src, tgt, e["type"])
        if edge_key in seen_edges:
            continue  # deduplicate
        seen_edges.add(edge_key)
        kept_edges.append({"source": src, "target": tgt, "type": e["type"], "weight": e["weight"]})

    return kept_nodes, kept_edges


@app.post("/api/open-brain/rebuild")
async def rebuild_open_brain_graph(background_tasks: BackgroundTasks):
    """Trigger a rebuild of the Open Brain knowledge graph (runs in background).

    Returns a job_id the frontend can poll via /api/rebuild-status/{job_id}.
    """
    def _rebuild_brain_graph():
        projects_root = Path(__file__).parent.parent.parent
        brain_py = projects_root / "ai-memory" / "brain.py"
        result = subprocess.run(
            ["doppler", "run", "--project", "ai-memory", "--config", "dev",
             "--", "uv", "run", str(brain_py), "graph", "build"],
            cwd=str(projects_root / "ai-memory"),
            timeout=300,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"brain.py graph build exited {result.returncode}: {result.stderr[-500:]}")
        logger.info("Open Brain graph rebuild complete")

    job_id = _create_rebuild_job("open_brain_graph")
    background_tasks.add_task(_run_tracked_rebuild, job_id, _rebuild_brain_graph)
    return {"status": "rebuilding", "message": "Graph rebuild started in background", "job_id": job_id}


@app.get("/api/memory/types")
async def get_memory_types():
    """Return distinct thought types present in brain.db.

    Used by the frontend to populate filter dropdowns dynamically.
    """
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
    category: Optional[str] = None
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
    
    loops = ["janitor", "patch-bot"]
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
async def run_agent(request: Request, payload: AgentRunRequest):
    """Execute an agent command and return result."""
    _require_local_admin_request(request)
    result = run_agent_command(
        payload.agent_name,
        payload.command_name,
        payload.args or ""
    )

    return {
        "success": result.success,
        "output": result.output,
        "error": result.error,
        "return_code": result.return_code,
        "duration_ms": result.duration_ms,
        "command": result.command
    }


# --- Error Handling Middleware ---

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


# --- Task API Endpoints ---

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
            category=task_data.category,
            parent_id=task_data.parent_id,
            blocked_by=blocked_by_json
        )
        return _enrich_task_payloads_with_display_ids([dict(task)], db)[0]
    except ValueError:
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
    status_filter: Optional[str] = Query(None, alias="status"),
    task_status: Optional[str] = None,
    include_subtasks: bool = True,
    parent_id: Optional[int] = None
):
    """List tasks with optional filtering.

    Args:
        project_id: Filter by project ID (optional)
        status_filter: Filter by status (optional; canonical query param)
        task_status: Legacy filter alias preserved for compatibility
        include_subtasks: Include subtasks in results (default: True)
        parent_id: Filter to subtasks of specific parent (optional)

    Returns:
        Dictionary with enriched tasks list and total count
    """
    try:
        import json
        db = DatabaseManager()
        effective_status = status_filter if status_filter is not None else task_status
        tasks = db.get_tasks(project_id=project_id, status=effective_status)

        subtasks_by_parent: Dict[int, List[Dict[str, object]]] = {}
        task_lookup = {task["id"]: dict(task) for task in tasks}
        for task in tasks:
            parent = task.get("parent_id")
            if parent is not None:
                subtasks_by_parent.setdefault(parent, []).append(dict(task))

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

            # Build subtask metadata from the already-fetched task set so we
            # do not open a new SQLite connection for every row in the board.
            subtasks = subtasks_by_parent.get(task["id"], []) if include_subtasks else []
            if subtasks:
                ordered_subtasks = sorted(
                    subtasks,
                    key=lambda item: (
                        item.get("sequence_order") is None,
                        item.get("sequence_order") if item.get("sequence_order") is not None else 0,
                        item.get("created_at", ""),
                    ),
                )
                done_count = len([item for item in ordered_subtasks if item.get("status") == "Done"])
                task_dict["subtasks"] = ordered_subtasks
                task_dict["subtask_progress"] = {
                    "total": len(ordered_subtasks),
                    "done": done_count,
                    "percent": int(done_count / len(ordered_subtasks) * 100),
                }

            # Resolve blocking data from the same in-memory task set to avoid
            # N additional DB reads while rendering the Kanban board.
            if task.get("blocked_by"):
                try:
                    blocked_by_ids = json.loads(task["blocked_by"])
                    task_dict["blocked_by_ids"] = blocked_by_ids
                    blocking_tasks = [
                        blocking_task
                        for blocked_id in blocked_by_ids
                        if (blocking_task := task_lookup.get(blocked_id)) is not None
                    ]
                    incomplete_ids = [
                        blocking_task["id"]
                        for blocking_task in blocking_tasks
                        if blocking_task.get("status") != "Done"
                    ]
                    task_dict["blocking_tasks"] = blocking_tasks
                    task_dict["is_blocked"] = len(incomplete_ids) > 0
                    task_dict["incomplete_blocking_ids"] = incomplete_ids
                except (json.JSONDecodeError, TypeError) as exc:
                    logger.warning(
                        "Could not resolve blocked_by for task %s: %s",
                        task.get("id"),
                        exc,
                    )

            enriched_tasks.append(task_dict)

        enriched_tasks = _enrich_task_payloads_with_display_ids(enriched_tasks, db)
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
        
        return _enrich_task_payloads_with_display_ids([task_dict], db)[0]
    except ValueError:
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
        provided_fields = getattr(task_data, "model_fields_set", None)
        if provided_fields is None:
            provided_fields = getattr(task_data, "__fields_set__", set())
        
        # Build update dict from non-None fields
        updates = {}
        if "text" in provided_fields:
            updates["text"] = task_data.text
        if "title" in provided_fields:
            updates["title"] = task_data.title
        if "notes" in provided_fields:
            updates["notes"] = task_data.notes
        if "commit_sha" in provided_fields:
            updates["commit_sha"] = task_data.commit_sha
        if "category" in provided_fields:
            updates["category"] = task_data.category
        if "review_comment" in provided_fields:
            updates["review_comment"] = task_data.review_comment
        if "status" in provided_fields:
            updates["status"] = task_data.status
        if "priority" in provided_fields:
            updates["priority"] = task_data.priority
        if "task_type" in provided_fields:
            updates["task_type"] = task_data.task_type
        if "parent_id" in provided_fields:
            updates["parent_id"] = task_data.parent_id
        if "blocked_by" in provided_fields:
            import json
            updates["blocked_by"] = (
                json.dumps(task_data.blocked_by) if task_data.blocked_by is not None else None
            )
        
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
                blocking_display_map = db.get_task_display_id_map(blocking_ids)
                blocking_str = ", ".join([f"#{blocking_display_map.get(bid, bid)}" for bid in blocking_ids])
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot start task while blocked by: {blocking_str}"
                )

        if not updates:
            # No updates provided, return current task
            task = db.get_task(task_id)
            if not task:
                raise ValueError(f"Task with ID {task_id} not found")
            return _enrich_task_payloads_with_display_ids([dict(task)], db)[0]
        
        # update_task handles history recording for status changes
        task = db.update_task(task_id, **updates)
        return _enrich_task_payloads_with_display_ids([dict(task)], db)[0]
    except ValueError:
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


# --- Attachment API Endpoints (#5216) ---

ATTACHMENT_MAX_BYTES = 20 * 1024 * 1024  # 20 MB


@app.post("/api/tasks/{task_id}/attachments", status_code=status.HTTP_201_CREATED)
async def upload_attachment(task_id: int, file: UploadFile = File(...)):
    """Upload a file and attach it to a task."""
    import mimetypes

    db = DatabaseManager()
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    # Stream to a temp file so we never hold >ATTACHMENT_MAX_BYTES in RAM
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
    file_path = DatabaseManager._attachments_dir(task_id, create=False) / record["stored_name"]
    if file_path.exists():
        file_path.unlink()
    return {"deleted": True, "attachment_id": attachment_id}


@app.get("/api/attachments/{task_id}/{stored_name}")
async def serve_attachment(task_id: int, stored_name: str):
    """Serve an attachment file for inline preview."""
    from fastapi.responses import FileResponse
    import mimetypes
    db = DatabaseManager()
    attachment = db.get_attachment(task_id, stored_name)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    attach_dir = DatabaseManager._attachments_dir(task_id, create=False)
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
# --- Agentic Markers API (#5009) ---

MARKERS_PATH = Path(__file__).parent.parent / "data" / "agentic_markers.json"


def _load_markers() -> list:
    """Load markers from disk, returning empty list on any error."""
    if not MARKERS_PATH.exists():
        return []
    try:
        data = json.loads(MARKERS_PATH.read_text())
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning("Failed to load markers from %s: %s", MARKERS_PATH, e)
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


@app.get("/api/tool-stats")
async def get_tool_stats(tool: str = "WebSearch", days: int = 30):
    """Tool invocation counts from ai-memory's brain.db tool_invocations table.

    Returns two parallel series for the /agentic chart:
      by_date   — total calls per day (All Projects view)
      by_project — calls per day per project (By Project view)

    Returns empty series if brain.db is absent or the table doesn't exist yet.
    """
    projects_root = Path.home() / "projects"
    brain_db = projects_root / "ai-memory" / "brain.db"

    empty = {"by_date": [], "by_project": [], "projects": []}
    if not brain_db.is_file():
        return empty

    end_date = datetime.now().date()
    days = min(max(days, 1), 365)
    start_date = end_date - timedelta(days=days - 1)
    start_iso = start_date.isoformat()

    try:
        uri = f"file:{brain_db}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=2.0)
        conn.row_factory = sqlite3.Row
        try:
            if conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='tool_invocations'"
            ).fetchone() is None:
                return empty

            by_date_rows = conn.execute(
                """
                SELECT DATE(invoked_at) AS date, COUNT(*) AS total
                FROM tool_invocations
                WHERE tool_name = ? AND DATE(invoked_at) >= ?
                GROUP BY DATE(invoked_at)
                ORDER BY date ASC
                """,
                (tool, start_iso),
            ).fetchall()

            by_project_rows = conn.execute(
                """
                SELECT DATE(invoked_at) AS date,
                       COALESCE(project, 'unknown') AS project,
                       COUNT(*) AS count
                FROM tool_invocations
                WHERE tool_name = ? AND DATE(invoked_at) >= ?
                GROUP BY DATE(invoked_at), COALESCE(project, 'unknown')
                ORDER BY date ASC
                """,
                (tool, start_iso),
            ).fetchall()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("Failed to read tool_invocations from brain.db: %s", exc)
        return empty

    date_map = {row["date"]: row["total"] for row in by_date_rows}
    by_date = []
    current = start_date
    while current <= end_date:
        ds = current.isoformat()
        by_date.append({"date": ds, "total": date_map.get(ds, 0)})
        current += timedelta(days=1)

    projects = sorted({row["project"] for row in by_project_rows})
    by_project = [
        {"date": row["date"], "project": row["project"], "count": row["count"]}
        for row in by_project_rows
    ]

    return {"by_date": by_date, "by_project": by_project, "projects": projects}


@app.get("/api/bash-stats")
async def get_bash_stats(days: int = 30):
    """Bash error rate (stuck score) per day from ai-memory's bash_calls table.

    Returns:
      by_date    — overall error_rate % per day (All Projects view)
      by_project — error_rate % per day per project (By Project view)
      summary    — aggregate anomaly counts/rates across the requested window
      anomalies_by_date — retry/hook/auth/usage-error counts per day
      error_kinds — top error_kind counts across the requested window
      top_prefixes — top command_prefix aggregates across the requested window
      by_caller_type — aggregate totals/errors by caller_type

    Returns empty series if brain.db is absent or the table doesn't exist.
    """
    projects_root = Path.home() / "projects"
    brain_db = projects_root / "ai-memory" / "brain.db"

    empty_summary = {
        "total": 0,
        "errors": 0,
        "error_rate": 0.0,
        "retries": 0,
        "retry_rate": 0.0,
        "hook_blocks": 0,
        "hook_block_rate": 0.0,
        "auth_errors": 0,
        "auth_error_rate": 0.0,
    }
    empty = {
        "by_date": [],
        "by_project": [],
        "projects": [],
        "summary": empty_summary,
        "anomalies_by_date": [],
        "error_kinds": [],
        "top_prefixes": [],
        "by_caller_type": [],
    }
    if not brain_db.is_file():
        return empty

    end_date = datetime.now().date()
    days = min(max(days, 1), 365)
    start_date = end_date - timedelta(days=days - 1)
    start_iso = start_date.isoformat()

    try:
        uri = f"file:{brain_db}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=2.0)
        conn.row_factory = sqlite3.Row
        try:
            if conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='bash_calls'"
            ).fetchone() is None:
                return empty

            bash_call_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info('bash_calls')").fetchall()
            }

            def _sum_expr(column: str, alias: str) -> str:
                if column in bash_call_columns:
                    return f"COALESCE(SUM(COALESCE({column}, 0)), 0) AS {alias}"
                return f"0 AS {alias}"

            usage_errors_expr = (
                "COALESCE(SUM(CASE WHEN LOWER(COALESCE(error_kind, '')) = 'usage_error' "
                "THEN 1 ELSE 0 END), 0) AS usage_errors"
                if "error_kind" in bash_call_columns
                else "0 AS usage_errors"
            )

            by_date_rows = conn.execute(
                """
                SELECT substr(invoked_at, 1, 10) AS date,
                       COUNT(*) AS total,
                       SUM(is_error) AS errors,
                       ROUND(SUM(is_error) * 100.0 / COUNT(*), 1) AS error_rate
                FROM bash_calls
                WHERE substr(invoked_at, 1, 10) >= ?
                GROUP BY substr(invoked_at, 1, 10)
                ORDER BY date ASC
                """,
                (start_iso,),
            ).fetchall()

            summary_row = conn.execute(
                f"""
                SELECT COUNT(*) AS total,
                       COALESCE(SUM(COALESCE(is_error, 0)), 0) AS errors,
                       CASE
                           WHEN COUNT(*) = 0 THEN 0.0
                           ELSE ROUND(COALESCE(SUM(COALESCE(is_error, 0)), 0) * 100.0 / COUNT(*), 1)
                       END AS error_rate,
                       {_sum_expr("is_retry", "retries")},
                       CASE
                           WHEN COUNT(*) = 0 THEN 0.0
                           ELSE ROUND(({ "COALESCE(SUM(COALESCE(is_retry, 0)), 0)" if "is_retry" in bash_call_columns else "0" }) * 100.0 / COUNT(*), 1)
                       END AS retry_rate,
                       {_sum_expr("is_hook_blocked", "hook_blocks")},
                       CASE
                           WHEN COUNT(*) = 0 THEN 0.0
                           ELSE ROUND(({ "COALESCE(SUM(COALESCE(is_hook_blocked, 0)), 0)" if "is_hook_blocked" in bash_call_columns else "0" }) * 100.0 / COUNT(*), 1)
                       END AS hook_block_rate,
                       {_sum_expr("is_auth_error", "auth_errors")},
                       CASE
                           WHEN COUNT(*) = 0 THEN 0.0
                           ELSE ROUND(({ "COALESCE(SUM(COALESCE(is_auth_error, 0)), 0)" if "is_auth_error" in bash_call_columns else "0" }) * 100.0 / COUNT(*), 1)
                       END AS auth_error_rate
                FROM bash_calls
                WHERE substr(invoked_at, 1, 10) >= ?
                """,
                (start_iso,),
            ).fetchone()

            anomalies_rows = conn.execute(
                f"""
                SELECT substr(invoked_at, 1, 10) AS date,
                       {_sum_expr("is_retry", "retries")},
                       {_sum_expr("is_hook_blocked", "hook_blocks")},
                       {_sum_expr("is_auth_error", "auth_errors")},
                       {usage_errors_expr}
                FROM bash_calls
                WHERE substr(invoked_at, 1, 10) >= ?
                GROUP BY substr(invoked_at, 1, 10)
                ORDER BY date ASC
                """,
                (start_iso,),
            ).fetchall()

            error_kind_rows = []
            if "error_kind" in bash_call_columns:
                error_kind_rows = conn.execute(
                    """
                    SELECT error_kind, COUNT(*) AS count
                    FROM bash_calls
                    WHERE substr(invoked_at, 1, 10) >= ?
                      AND COALESCE(error_kind, '') <> ''
                    GROUP BY error_kind
                    ORDER BY count DESC, error_kind ASC
                    LIMIT 10
                    """,
                    (start_iso,),
                ).fetchall()

            top_prefix_rows = []
            if "command_prefix" in bash_call_columns:
                top_prefix_rows = conn.execute(
                    f"""
                    SELECT command_prefix,
                           COUNT(*) AS total,
                           COALESCE(SUM(COALESCE(is_error, 0)), 0) AS errors,
                           {_sum_expr("is_hook_blocked", "hook_blocks")},
                           {_sum_expr("is_auth_error", "auth_errors")}
                    FROM bash_calls
                    WHERE substr(invoked_at, 1, 10) >= ?
                      AND COALESCE(command_prefix, '') <> ''
                    GROUP BY command_prefix
                    ORDER BY total DESC, errors DESC, command_prefix ASC
                    LIMIT 10
                    """,
                    (start_iso,),
                ).fetchall()

            caller_type_rows = []
            if "caller_type" in bash_call_columns:
                caller_type_rows = conn.execute(
                    """
                    SELECT COALESCE(NULLIF(caller_type, ''), 'unknown') AS caller_type,
                           COUNT(*) AS total,
                           COALESCE(SUM(COALESCE(is_error, 0)), 0) AS errors,
                           CASE
                               WHEN COUNT(*) = 0 THEN 0.0
                               ELSE ROUND(COALESCE(SUM(COALESCE(is_error, 0)), 0) * 100.0 / COUNT(*), 1)
                           END AS error_rate
                    FROM bash_calls
                    WHERE substr(invoked_at, 1, 10) >= ?
                    GROUP BY COALESCE(NULLIF(caller_type, ''), 'unknown')
                    ORDER BY total DESC, caller_type ASC
                    """,
                    (start_iso,),
                ).fetchall()

            by_project_rows = conn.execute(
                """
                SELECT substr(invoked_at, 1, 10) AS date,
                       COALESCE(project, 'unknown') AS project,
                       COUNT(*) AS total,
                       SUM(is_error) AS errors,
                       ROUND(SUM(is_error) * 100.0 / COUNT(*), 1) AS error_rate
                FROM bash_calls
                WHERE substr(invoked_at, 1, 10) >= ?
                GROUP BY substr(invoked_at, 1, 10), COALESCE(project, 'unknown')
                ORDER BY date ASC
                """,
                (start_iso,),
            ).fetchall()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("Failed to read bash_calls from brain.db: %s", exc)
        return empty

    date_map = {row["date"]: {"error_rate": row["error_rate"], "total": row["total"], "errors": row["errors"]} for row in by_date_rows}
    by_date = []
    current = start_date
    while current <= end_date:
        ds = current.isoformat()
        entry = date_map.get(ds, {"error_rate": 0.0, "total": 0, "errors": 0})
        by_date.append({"date": ds, **entry})
        current += timedelta(days=1)

    anomaly_map = {
        row["date"]: {
            "retries": row["retries"],
            "hook_blocks": row["hook_blocks"],
            "auth_errors": row["auth_errors"],
            "usage_errors": row["usage_errors"],
        }
        for row in anomalies_rows
    }
    anomalies_by_date = []
    current = start_date
    while current <= end_date:
        ds = current.isoformat()
        entry = anomaly_map.get(
            ds,
            {"retries": 0, "hook_blocks": 0, "auth_errors": 0, "usage_errors": 0},
        )
        anomalies_by_date.append({"date": ds, **entry})
        current += timedelta(days=1)

    projects = sorted({row["project"] for row in by_project_rows})
    by_project = [
        {"date": row["date"], "project": row["project"], "error_rate": row["error_rate"]}
        for row in by_project_rows
    ]

    summary = dict(summary_row) if summary_row else dict(empty_summary)
    summary["error_rate"] = float(summary.get("error_rate", 0.0) or 0.0)
    summary["retry_rate"] = float(summary.get("retry_rate", 0.0) or 0.0)
    summary["hook_block_rate"] = float(summary.get("hook_block_rate", 0.0) or 0.0)
    summary["auth_error_rate"] = float(summary.get("auth_error_rate", 0.0) or 0.0)

    error_kinds = [
        {"error_kind": row["error_kind"], "count": row["count"]}
        for row in error_kind_rows
    ]
    top_prefixes = [
        {
            "command_prefix": row["command_prefix"],
            "total": row["total"],
            "errors": row["errors"],
            "hook_blocks": row["hook_blocks"],
            "auth_errors": row["auth_errors"],
        }
        for row in top_prefix_rows
    ]
    by_caller_type = [
        {
            "caller_type": row["caller_type"],
            "total": row["total"],
            "errors": row["errors"],
            "error_rate": float(row["error_rate"] or 0.0),
        }
        for row in caller_type_rows
    ]

    return {
        "by_date": by_date,
        "by_project": by_project,
        "projects": projects,
        "summary": summary,
        "anomalies_by_date": anomalies_by_date,
        "error_kinds": error_kinds,
        "top_prefixes": top_prefixes,
        "by_caller_type": by_caller_type,
    }


# --- Ideas API Endpoints (Task #4583) ---

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
    except ValueError:
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
    except ValueError:
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
    except ValueError:
        # Re-raise to be caught by error handler
        raise
    except Exception as e:
        logger.error(f"Error deleting idea {idea_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete idea"
        )


# ---------------------------------------------------------------------------
# GitHub API  (#5373)
# ---------------------------------------------------------------------------

_github_cache: Dict = {"data": None, "timestamp": 0}
_GITHUB_CACHE_TTL = 300  # 5 minutes


def _find_gh() -> str:
    """Find gh binary, checking common install locations if not on PATH.

    launchd services have a minimal PATH (/usr/bin:/bin:/usr/sbin:/sbin),
    so shutil.which() alone won't find Homebrew-installed gh.
    """
    found = shutil.which("gh") or os.environ.get("GH_PATH")
    if found:
        return found
    # Check standard install locations (launchd PATH doesn't include these)
    homebrew_paths = [
        os.path.expanduser("~/.local/bin/gh"),
        os.path.join(os.environ.get("HOMEBREW_PREFIX", "/opt/homebrew"), "bin", "gh"),
    ]
    for candidate in homebrew_paths:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return "gh"


_GH_BIN = _find_gh()


def _gh_json(args: List[str], timeout: int = 30) -> any:
    """Run a gh CLI command and return parsed JSON, or None on failure."""
    try:
        result = subprocess.run(
            [_GH_BIN] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            logger.warning(f"gh command failed: gh {' '.join(args)} — {result.stderr.strip()}")
            return None
        return json.loads(result.stdout) if result.stdout.strip() else None
    except FileNotFoundError:
        logger.error("gh CLI not found on PATH")
        return None
    except subprocess.TimeoutExpired:
        logger.warning(f"gh command timed out: gh {' '.join(args)}")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"gh returned non-JSON: {e}")
        return None


def _get_tracked_repo_names() -> List[str]:
    """Get repo names from the kanban board's project list.

    Includes top-level projects and subdirectories of github-repos/.
    Excludes internal prefixes (_tools, __knowledge, etc.).
    """
    try:
        db = DatabaseManager()
        projects = db.get_all_projects()
        names: List[str] = []
        for p in projects:
            pid = p.get("id", "")
            # Skip internal/infrastructure projects
            if pid.startswith("_") or pid.startswith("__"):
                continue
            # github-repos is a container — its children are the actual repos
            if pid == "github-repos":
                github_repos_dir = Path(os.environ.get("PROJECTS_ROOT", str(Path.home() / "projects"))) / "github-repos"
                if github_repos_dir.is_dir():
                    for child in github_repos_dir.iterdir():
                        if child.is_dir() and not child.name.startswith(".") and not child.name.startswith("00_"):
                            names.append(child.name)
                continue
            names.append(pid)
        return sorted(set(names))
    except Exception as e:
        logger.warning(f"Failed to get tracked projects: {e}")
        return []


def _fetch_github_data() -> Dict:
    """Fetch GitHub data for tracked projects only (from kanban board)."""

    # 1. Account info
    user = _gh_json(["api", "/user"])
    if user is None:
        return {"error": "gh CLI not available or not authenticated", "cached": False}

    owner = user.get("login", "")

    # 2. Get repo list from kanban board, then fetch details from GitHub
    tracked_names = _get_tracked_repo_names()
    if not tracked_names:
        return {"error": "No tracked projects found in kanban board", "cached": False}

    repos: List[Dict] = []
    for name in tracked_names:
        repo_info = _gh_json([
            "repo", "view", f"{owner}/{name}",
            "--json", "name,url,pushedAt,defaultBranchRef,isPrivate,description,stargazerCount,forkCount,isArchived",
        ], timeout=10)
        if repo_info:
            repos.append(repo_info)
        else:
            logger.info(f"Skipped tracked project '{name}' — not found on GitHub or fetch failed")

    # 3. Open PRs across tracked repos
    all_prs: List[Dict] = []
    pr_fields = "title,number,url,author,createdAt,statusCheckRollup,reviewDecision,headRefName,baseRefName,isDraft,repository"
    for repo in repos:
        repo_name = repo.get("name", "")
        if repo.get("isArchived"):
            continue
        prs = _gh_json([
            "pr", "list",
            "--repo", f"{owner}/{repo_name}",
            "--json", pr_fields,
            "--state", "open",
            "--limit", "50",
        ], timeout=15)
        if prs:
            all_prs.extend(prs)

    # 4. Recent commits (last 7 days) — only from tracked repos
    seven_days_ago = (datetime.utcnow() - timedelta(days=7)).isoformat() + "Z"
    recent_commits: List[Dict] = []
    for repo in repos:
        pushed = repo.get("pushedAt", "")
        if pushed and pushed >= seven_days_ago and not repo.get("isArchived"):
            repo_name = repo.get("name", "")
            default_branch = (repo.get("defaultBranchRef") or {}).get("name", "main")
            commits = _gh_json([
                "api", f"/repos/{owner}/{repo_name}/commits",
                "-q", ".",
                "--method", "GET",
                "-f", f"since={seven_days_ago}",
                "-f", f"sha={default_branch}",
                "-f", "per_page=20",
            ], timeout=15)
            if commits and isinstance(commits, list):
                for c in commits[:20]:
                    recent_commits.append({
                        "repo": repo_name,
                        "sha": c.get("sha", "")[:7],
                        "message": (c.get("commit", {}).get("message") or "").split("\n")[0],
                        "author": (c.get("commit", {}).get("author") or {}).get("name", ""),
                        "date": (c.get("commit", {}).get("author") or {}).get("date", ""),
                        "url": c.get("html_url", ""),
                    })

    # 5. Workflow runs (CI status) — recent runs across tracked repos
    workflow_runs: List[Dict] = []
    for repo in repos:
        if repo.get("isArchived"):
            continue
        repo_name = repo.get("name", "")
        runs = _gh_json([
            "api", f"/repos/{owner}/{repo_name}/actions/runs",
            "-q", ".",
            "--method", "GET",
            "-f", "per_page=5",
        ], timeout=10)
        if runs and isinstance(runs, dict):
            for run in (runs.get("workflow_runs") or [])[:5]:
                workflow_runs.append({
                    "repo": repo_name,
                    "name": run.get("name", ""),
                    "status": run.get("status", ""),
                    "conclusion": run.get("conclusion"),
                    "branch": run.get("head_branch", ""),
                    "created_at": run.get("created_at", ""),
                    "url": run.get("html_url", ""),
                })

    # 6. Branch info — only tracked repos
    branch_info: List[Dict] = []
    for repo in repos:
        if repo.get("isArchived"):
            continue
        repo_name = repo.get("name", "")
        branches = _gh_json([
            "api", f"/repos/{owner}/{repo_name}/branches",
            "-q", ".",
            "--method", "GET",
            "-f", "per_page=100",
        ], timeout=10)
        if branches and isinstance(branches, list):
            for b in branches:
                branch_info.append({
                    "repo": repo_name,
                    "name": b.get("name", ""),
                    "protected": b.get("protected", False),
                })

    return {
        "user": {
            "login": user.get("login"),
            "name": user.get("name"),
            "avatar_url": user.get("avatar_url"),
            "public_repos": user.get("public_repos"),
            "private_repos": user.get("total_private_repos"),
            "followers": user.get("followers"),
            "following": user.get("following"),
        },
        "repos": repos,
        "tracked_projects": tracked_names,
        "open_pull_requests": all_prs,
        "recent_commits": recent_commits,
        "workflow_runs": workflow_runs,
        "branches": branch_info,
        "summary": {
            "total_repos": len(repos),
            "tracked_projects": len(tracked_names),
            "repos_found_on_github": len(repos),
            "repos_not_on_github": len(tracked_names) - len(repos),
            "archived_repos": sum(1 for r in repos if r.get("isArchived")),
            "open_prs": len(all_prs),
            "draft_prs": sum(1 for p in all_prs if p.get("isDraft")),
            "recent_commit_count": len(recent_commits),
            "repos_with_ci": len(set(r["repo"] for r in workflow_runs)),
            "failing_ci": sum(
                1 for r in workflow_runs
                if r.get("conclusion") == "failure"
                and (r.get("branch") in ("main", "master")
                     or any(pr.get("headRefName") == r.get("branch")
                            and pr.get("repository", {}).get("name") == r.get("repo")
                            for pr in all_prs))
            ),
        },
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "cached": False,
    }


@app.get("/api/github")
async def api_github():
    """Comprehensive GitHub account data via gh CLI.

    Returns repos, open PRs, recent commits, branches, and CI status.
    Cached for 5 minutes to avoid hammering the GitHub API.
    """
    now = _time()
    if (_github_cache["data"] is not None
            and now - _github_cache["timestamp"] < _GITHUB_CACHE_TTL):
        data = _github_cache["data"].copy()
        data["cached"] = True
        return data

    try:
        data = _fetch_github_data()
        if "error" not in data:
            _github_cache["data"] = data
            _github_cache["timestamp"] = _time()
        return data
    except Exception as e:
        logger.error(f"Error fetching GitHub data: {e}", exc_info=True)
        return {"error": str(e), "cached": False}
