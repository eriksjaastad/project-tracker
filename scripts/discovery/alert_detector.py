"""Alert detection for project tracker."""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any

from .cron_monitor import check_cron_health
from .agent_config_health import build_empty_agent_config_health, get_agent_config_health
from .code_review_parser import parse_code_review
from .telemetry_reader import get_telemetry_stats, get_critical_errors
from .cron_health import get_stale_crons

# Add parent directory to path for logger import
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.logger import get_logger

logger = get_logger(__name__)


def detect_stalled_projects(projects: List[Dict[str, Any]], days_threshold: int = 60) -> List[Dict[str, Any]]:
    """Detect projects with no work in X days (default 60 for less noise)."""
    alerts = []
    
    for project in projects:
        if project.get("last_modified"):
            try:
                last_mod = datetime.fromisoformat(project["last_modified"].replace('Z', '+00:00'))
                # Use timezone-aware now if last_mod has timezone info
                now = datetime.now(last_mod.tzinfo) if last_mod.tzinfo else datetime.now()
                cutoff_date = now - timedelta(days=days_threshold)
                
                if last_mod < cutoff_date:
                    days_ago = (now - last_mod).days
                    alerts.append({
                        "project_id": project["id"],
                        "project_name": project["name"],
                        "type": "stalled",
                        "severity": "warning",
                        "message": f"No work in {days_ago} days",
                        "details": f"Last modified: {project['last_modified'].split('T')[0]}"
                    })
            except Exception as e:
                logger.debug(f"Failed to parse last_modified for {project.get('name', 'unknown')}: {e}")
    
    return alerts


def detect_cron_failures(projects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect cron job failures and issues.

    Expects projects pre-enriched with ``cron_jobs`` key via _bulk_enrich.
    """
    alerts = []
    if projects and "cron_jobs" not in projects[0]:
        logger.warning("detect_cron_failures: projects missing cron_jobs key — was _bulk_enrich called?")
        return alerts

    for project in projects:
        cron_jobs = project.get("cron_jobs", [])
        if not cron_jobs:
            continue
        
        # Check each cron job's health
        issues = check_cron_health(
            project["id"],
            cron_jobs,
            project["path"]
        )
        
        for issue in issues:
            severity = "critical" if issue["type"] in ["execution_error", "missed_run"] else "warning"
            
            alerts.append({
                "project_id": project["id"],
                "project_name": project["name"],
                "type": f"cron_{issue['type']}",
                "severity": severity,
                "message": issue["message"],
                "details": f"{issue.get('description', issue.get('command', ''))}"
            })
    
    return alerts


def detect_stale_cron_heartbeats() -> List[Dict[str, Any]]:
    """Detect known cron jobs that haven't produced a log heartbeat recently."""
    alerts = []
    try:
        stale_names = get_stale_crons(threshold_hours=48)
        for name in stale_names:
            alerts.append({
                "project_id": "system", # Global/System alert
                "project_name": "CRON",
                "type": "stale_heartbeat",
                "severity": "critical",
                "message": f"Heartbeat lost: {name}",
                "details": f"No log updates detected in over 48 hours for {name}"
            })
    except Exception as e:
        logger.error(f"Failed to detect stale crons: {e}")
    return alerts


def detect_code_reviews(projects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect projects with pending code reviews."""
    alerts = []
    
    for project in projects:
        review_path = Path(project["path"]) / "CODE_REVIEW.md"
        if review_path.exists():
            review_data = parse_code_review(review_path)
            if review_data:
                verdict = review_data.get("verdict", "Unknown")
                reviewer = review_data.get("reviewer", "Unknown")
                
                # Determine severity based on verdict
                severity = "warning"
                if "production" in verdict.lower() or "approved" in verdict.lower():
                    severity = "info"
                elif "delete" in verdict.lower() or "refactor" in verdict.lower():
                    severity = "warning"
                
                # Create alert message
                message = f"Code review: {verdict}"
                details = f"Reviewer: {reviewer}"
                if review_data.get("summary"):
                    details += f" | {review_data['summary'][:80]}..."
                
                alerts.append({
                    "project_id": project["id"],
                    "project_name": project["name"],
                    "type": "code_review",
                    "severity": severity,
                    "message": message,
                    "details": details
                })
    
    return alerts


def detect_missing_index(projects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect projects missing index files.

    Note: 00_Index files were removed (Librarian system deleted).
    This function now returns an empty list — index file checks
    are no longer applicable.
    """
    return []


def detect_agent_config_health(projects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect projects whose agent config files have health warnings."""
    alerts = []

    for project in projects:
        project_path = Path(project.get("path", "")) if project.get("path") else None
        health = project.get("agent_config_health")
        if health is None:
            if project_path and project_path.exists():
                health = get_agent_config_health(project_path)
            else:
                health = build_empty_agent_config_health(project.get("name", project.get("id", "")))

        warning_count = health.get("warning_count", 0)
        if warning_count <= 0:
            continue

        first_warning = next(
            (
                f"{file_health['path']}: {warning}"
                for file_health in health.get("files", [])
                for warning in file_health.get("warnings", [])
            ),
            "Agent config health warnings detected",
        )
        message = first_warning
        if warning_count > 1:
            message = f"{warning_count} agent config warnings — {first_warning}"

        alerts.append({
            "project_id": project["id"],
            "project_name": project["name"],
            "type": "agent_config_health",
            "severity": "warning",
            "message": message,
            "details": first_warning,
        })

    return alerts


def detect_invalid_frontmatter(projects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect projects with invalid frontmatter using audit check.

    Note: 00_Index files were removed (Librarian system deleted).
    This function now returns an empty list — frontmatter validation
    is no longer applicable without index files.
    """
    return []


def detect_telemetry_errors() -> List[Dict[str, Any]]:
    """Detect high error rates or critical failures in AI Router."""
    alerts = []
    try:
        stats = get_telemetry_stats(days=1)
        # Flag if error rate > 10% OR if there are more than 5 specific error entries in last 24h
        if stats.get("error_rate", 0) > 10 or len(get_critical_errors(hours=24)) > 5:
            alerts.append({
                "project_id": "project-tracker", # Global alert
                "project_name": "SYSTEM",
                "type": "telemetry_error",
                "severity": "critical",
                "message": f"AI Router error rate: {stats.get('error_rate')}%",
                "details": f"High failure rate detected in last 24h. Total requests: {stats.get('total_requests')}"
            })
    except Exception as e:
        logger.error(f"Failed to detect telemetry errors: {e}")
    return alerts


def get_all_alerts(projects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Get all alerts for all projects."""
    all_alerts = []
    
    # Detect different types of issues
    all_alerts.extend(detect_telemetry_errors())
    all_alerts.extend(detect_stale_cron_heartbeats())

    all_alerts.extend(detect_code_reviews(projects))
    all_alerts.extend(detect_cron_failures(projects))
    all_alerts.extend(detect_stalled_projects(projects))
    all_alerts.extend(detect_missing_index(projects))  # Only missing, not incomplete
    all_alerts.extend(detect_agent_config_health(projects))
    # Sort by severity (critical first, then warning, then info)
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    all_alerts.sort(key=lambda x: (severity_order.get(x["severity"], 3), x["project_name"]))
    
    return all_alerts
