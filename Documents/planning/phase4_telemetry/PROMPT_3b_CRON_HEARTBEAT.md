# Worker Task 3b: Add Cron Health Sentinel

**Worker Model:** Qwen 2.5 Coder
**Objective:** Add visual "heartbeat" indicator for cron job health.

---

## 🎯 [ACCEPTANCE CRITERIA]

- [x] **Check Log Timestamps:** Read last modified time of known log files
- [x] **Heartbeat Status:** Green if updated <24h, Yellow if <72h, Red if stale
- [x] **Dashboard Display:** Show heartbeat indicator per cron job
- [x] **Alert if Stale:** Add alert if any cron hasn't run in >48h

---

## CONSTRAINTS (READ FIRST)

- USE existing cron_monitor.py patterns if they exist
- CHECK log file modification times (don't parse log contents)
- KEEP list of known log paths in config

---

## Reference: Known Cron Log Locations

```python
CRON_LOG_PATHS = {
    "Trading Arena": Path("/Users/eriksjaastad/projects/Trading Projects/logs/arena.log"),
    "Cortana Daily": Path("/Users/eriksjaastad/projects/Cortana personal AI/logs/daily.log"),
    # Add others as discovered
}
```

---

## Reference Code Snippet

Create `scripts/discovery/cron_health.py`:

```python
"""
Cron Health Monitor - Check if scheduled jobs are running.
"""
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Known cron job log files
CRON_LOG_PATHS = {
    "Trading Arena": Path("/Users/eriksjaastad/projects/Trading Projects/logs/arena.log"),
    # Add more as needed
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
```

---

## Verification

```bash
cd /Users/eriksjaastad/projects/project-tracker
python -c "
from scripts.discovery.cron_health import get_cron_health, get_stale_crons
health = get_cron_health()
for h in health:
    print(f'{h[\"name\"]}: {h[\"status\"]} ({h.get(\"age_hours\", \"?\")}h)')
stale = get_stale_crons()
print(f'Stale crons: {stale}')
"
```
