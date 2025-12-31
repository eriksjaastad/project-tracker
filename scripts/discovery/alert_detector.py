"""Alert detection for project tracker."""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any

from .cron_monitor import check_cron_health
from .code_review_parser import parse_code_review
from scripts.db.manager import DatabaseManager

# Add parent directory to path for logger import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from logger import get_logger

logger = get_logger(__name__)



def detect_stalled_projects(projects: List[Dict[str, Any]], days_threshold: int = 60) -> List[Dict[str, Any]]:
    """Detect projects with no work in X days (default 60 for less noise)."""
    alerts = []
    cutoff_date = datetime.now() - timedelta(days=days_threshold)
    
    for project in projects:
        if project.get("last_modified"):
            try:
                last_mod = datetime.fromisoformat(project["last_modified"].replace('Z', '+00:00'))
                if last_mod < cutoff_date:
                    days_ago = (datetime.now() - last_mod).days
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


def detect_missing_todo(projects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect projects with no TODO.md or unknown status."""
    alerts = []
    
    for project in projects:
        if project.get("status") == "unknown":
            todo_path = Path(project["path"]) / "TODO.md"
            if not todo_path.exists():
                alerts.append({
                    "project_id": project["id"],
                    "project_name": project["name"],
                    "type": "missing_todo",
                    "severity": "info",
                    "message": "No TODO.md file",
                    "details": "Consider adding TODO.md to track project status"
                })
            else:
                alerts.append({
                    "project_id": project["id"],
                    "project_name": project["name"],
                    "type": "unknown_status",
                    "severity": "info",
                    "message": "Status unknown",
                    "details": "TODO.md exists but status not detected"
                })
    
    return alerts


def detect_blocked_projects(projects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect projects with blockers mentioned in TODO.md."""
    alerts = []
    
    for project in projects:
        todo_path = Path(project["path"]) / "TODO.md"
        if todo_path.exists():
            try:
                content = todo_path.read_text()
                
                # Look for blocker indicators
                blocker_sections = [
                    "### Blockers",
                    "## Blockers",
                    "### What's Missing",
                    "## What's Missing"
                ]
                
                for section in blocker_sections:
                    if section in content:
                        # Extract content after the section
                        section_start = content.find(section)
                        section_end = content.find("\n##", section_start + len(section))
                        if section_end == -1:
                            section_content = content[section_start:]
                        else:
                            section_content = content[section_start:section_end]
                        
                        # Count non-empty lines (ignoring headers and empty lines)
                        lines = [line.strip() for line in section_content.split('\n') 
                                if line.strip() and not line.strip().startswith('#')]
                        
                        if len(lines) > 0:
                            # Extract first blocker as preview
                            first_blocker = lines[0][:100]
                            if first_blocker.startswith('- '):
                                first_blocker = first_blocker[2:]
                            
                            alerts.append({
                                "project_id": project["id"],
                                "project_name": project["name"],
                                "type": "blocked",
                                "severity": "critical",
                                "message": f"Project blocked",
                                "details": first_blocker
                            })
                            break  # Only report once per project
            except Exception as e:
                logger.warning(f"Failed to detect blockers for {project.get('name', 'unknown')}: {e}")
    
    return alerts


def detect_cron_failures(projects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect cron job failures and issues."""
    alerts = []
    db = DatabaseManager()
    
    for project in projects:
        # Fetch cron jobs from database
        cron_jobs = db.get_cron_jobs(project["id"])
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


def detect_code_reviews(projects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect projects with pending code reviews."""
    alerts = []
    
    for project in projects:
        review_path = Path(project["path"]) / "CODE_REVIEW.md"
        if review_path.exists():
            review_data = parse_code_review(review_path)
            if review_data:
                status = review_data.get("status", "pending")
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


def get_all_alerts(projects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Get all alerts for all projects."""
    all_alerts = []
    
    # Detect different types of issues
    all_alerts.extend(detect_blocked_projects(projects))
    all_alerts.extend(detect_code_reviews(projects))  # Add code review detection
    all_alerts.extend(detect_cron_failures(projects))
    all_alerts.extend(detect_stalled_projects(projects))
    all_alerts.extend(detect_missing_todo(projects))
    
    # Sort by severity (critical first, then warning, then info)
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    all_alerts.sort(key=lambda x: (severity_order.get(x["severity"], 3), x["project_name"]))
    
    return all_alerts

