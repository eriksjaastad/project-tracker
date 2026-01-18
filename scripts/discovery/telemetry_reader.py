"""
Telemetry Reader for AI Router integration.
Reads telemetry.jsonl and provides stats for the dashboard.
"""
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# AI Router telemetry location (configurable via environment variable)
_default_telemetry = Path(__file__).resolve().parents[3] / "_tools" / "ai_router" / "logs" / "telemetry.jsonl"
TELEMETRY_PATH = Path(os.getenv("TELEMETRY_PATH", str(_default_telemetry)))

# Rough cost estimates per request (USD)
COST_PER_REQUEST = {
    "local": 0.0,
    "cheap": 0.002,   # GPT-4o-mini estimate
    "smart": 0.01,    # GPT-4o estimate
}

# Memory guard - prevent OOM on large telemetry files
MAX_ENTRIES = 10000


def _read_telemetry_entries(days: int = 7) -> list[dict]:
    """
    Read telemetry entries from JSONL file.

    Args:
        days: Only include entries from last N days

    Returns:
        List of telemetry entry dicts
    """
    if not TELEMETRY_PATH.exists():
        logger.warning(f"Telemetry file not found: {TELEMETRY_PATH}")
        return []

    cutoff = datetime.utcnow() - timedelta(days=days)
    entries = []

    try:
        with open(TELEMETRY_PATH, 'r') as f:
            for line in f:
                # Memory guard check
                if len(entries) >= MAX_ENTRIES:
                    logger.warning(f"Telemetry capped at {MAX_ENTRIES} entries")
                    break

                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    # Parse timestamp and filter by date
                    ts_str = entry.get('timestamp', '')
                    if ts_str:
                        # Handle ISO format: 2026-01-05T09:23:14.918438Z
                        ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                        if ts.replace(tzinfo=None) >= cutoff:
                            entries.append(entry)
                except json.JSONDecodeError:
                    logger.debug(f"Skipping malformed line: {line[:50]}...")
                    continue
    except Exception as e:
        logger.error(f"Error reading telemetry: {e}")
        return []

    return entries


def get_telemetry_stats(days: int = 7) -> dict[str, Any]:
    """
    Get aggregated telemetry stats for the dashboard.

    Args:
        days: Number of days to look back (default 7)

    Returns:
        Dict with model usage, durations, costs, etc.
    """
    entries = _read_telemetry_entries(days)

    if not entries:
        return {
            "total_requests": 0,
            "local_requests": 0,
            "cloud_requests": 0,
            "local_pct": 0,
            "avg_duration_local_ms": 0,
            "avg_duration_cloud_ms": 0,
            "error_rate": 0,
            "models": {},
            "period_days": days,
            "estimated_cloud_cost": 0.0,
            "actual_cost": 0.0,
            "savings": 0.0,
            "savings_pct": 0.0
        }

    # Count by provider
    local_entries = [e for e in entries if e.get('provider') == 'local']
    cloud_entries = [e for e in entries if e.get('provider') != 'local']

    # Count by model
    model_counts: dict[str, int] = {}
    for e in entries:
        model = e.get('model', 'unknown')
        model_counts[model] = model_counts.get(model, 0) + 1

    # Average durations
    local_durations = [e.get('duration_ms', 0) for e in local_entries]
    cloud_durations = [e.get('duration_ms', 0) for e in cloud_entries]

    avg_local = sum(local_durations) / len(local_durations) if local_durations else 0
    avg_cloud = sum(cloud_durations) / len(cloud_durations) if cloud_durations else 0

    # Error rate
    errors = [e for e in entries if e.get('error') or e.get('timed_out')]
    error_rate = (len(errors) / len(entries) * 100) if entries else 0

    # Cost calculations
    actual_cost = 0.0
    estimated_cloud_cost = 0.0

    for e in entries:
        tier = e.get('tier', 'local')
        # Actual cost
        actual_cost += COST_PER_REQUEST.get(tier, 0.0)
        # What it would cost if we used cloud for everything (assume cheap tier)
        estimated_cloud_cost += COST_PER_REQUEST.get('cheap', 0.002)

    savings = estimated_cloud_cost - actual_cost

    total = len(entries)
    local_count = len(local_entries)

    return {
        "total_requests": total,
        "local_requests": local_count,
        "cloud_requests": len(cloud_entries),
        "local_pct": round(local_count / total * 100, 1) if total else 0,
        "avg_duration_local_ms": round(avg_local, 0),
        "avg_duration_cloud_ms": round(avg_cloud, 0),
        "error_rate": round(error_rate, 1),
        "models": model_counts,
        "period_days": days,
        "estimated_cloud_cost": round(estimated_cloud_cost, 2),
        "actual_cost": round(actual_cost, 2),
        "savings": round(savings, 2),
        "savings_pct": round(savings / estimated_cloud_cost * 100, 1) if estimated_cloud_cost > 0 else 0,
    }


def get_critical_errors(hours: int = 24) -> list[dict]:
    """
    Get critical errors from last N hours.
    Returns list of error entries for alerting.
    """
    # Use enough days to cover the hours requested
    days_to_read = (hours // 24) + 1
    entries = _read_telemetry_entries(days=days_to_read) 

    cutoff = datetime.utcnow() - timedelta(hours=hours)
    errors = []

    for e in entries:
        if not (e.get('error') or e.get('timed_out')):
            continue

        ts_str = e.get('timestamp', '')
        if ts_str:
            ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            if ts.replace(tzinfo=None) >= cutoff:
                errors.append({
                    'model': e.get('model', 'unknown'),
                    'error': e.get('error') or 'Timeout',
                    'timestamp': ts_str
                })

    return errors


if __name__ == "__main__":
    # Quick test
    stats = get_telemetry_stats(days=30)
    print(f"Total: {stats['total_requests']}")
    print(f"Local: {stats['local_pct']}%")
    print(f"Savings: ${stats['savings']} ({stats['savings_pct']}%)")
    
    errors = get_critical_errors(hours=24)
    print(f"Critical errors in last 24h: {len(errors)}")
