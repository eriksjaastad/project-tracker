"""
Cron Health Monitor - Check if scheduled jobs are running.
"""
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Projects root (configurable via environment variable)
PROJECTS_ROOT = Path(os.getenv("PROJECTS_ROOT", str(Path.home() / "projects")))

# Known cron job log files (configurable via environment variables)
CRON_LOG_PATHS = {
    "Trading Arena": Path(os.getenv(
        "CRON_TRADING_LOG",
        str(PROJECTS_ROOT / "Trading Projects" / "logs" / "arena.log")
    )),
    "Cortana Daily": Path(os.getenv(
        "CRON_CORTANA_LOG",
        str(PROJECTS_ROOT / "Cortana personal AI" / "logs" / "daily.log")
    )),
}


def get_cron_health() -> list[dict[str, Any]]:
    """
    Check health of known cron jobs based on log file freshness.

    Returns:
        List of dicts with name, status, last_updated
    """
    results = []
    now = datetime.now()

    for name, log_path in CRON_LOG_PATHS.items():
        if not log_path.exists():
            results.append({
                "name": name,
                "status": "unknown",
                "status_color": "secondary",
                "last_updated": None,
                "message": "Log file not found"
            })
            continue

        # Get last modified time
        mtime = datetime.fromtimestamp(log_path.stat().st_mtime)
        age = now - mtime

        if age < timedelta(hours=24):
            status = "healthy"
            color = "success"
        elif age < timedelta(hours=72):
            status = "warning"
            color = "warning"
        else:
            status = "stale"
            color = "danger"

        results.append({
            "name": name,
            "status": status,
            "status_color": color,
            "last_updated": mtime.isoformat(),
            "age_hours": round(age.total_seconds() / 3600, 1)
        })

    return results


def get_stale_crons(threshold_hours: int = 48) -> list[str]:
    """Get list of cron jobs that haven't run recently."""
    health = get_cron_health()
    return [c["name"] for c in health if c.get("age_hours", 999) > threshold_hours]


if __name__ == "__main__":
    # Quick test
    health = get_cron_health()
    for h in health:
        print(f"{h['name']}: {h['status']} ({h.get('age_hours', '?')}h)")
    stale = get_stale_crons()
    print(f"Stale crons: {stale}")
