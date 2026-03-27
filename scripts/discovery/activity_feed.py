"""Query GitHub activity events from the Turso activity database.

This connects to a *separate* Turso database that stores GitHub webhook
events synced by the github-activity-feed service.  Environment variables:

    TURSO_ACTIVITY_URL   – libsql URL  (required)
    TURSO_ACTIVITY_TOKEN – auth token   (required)

If either is missing the feed is silently empty so the dashboard still loads.
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

def _connect() -> Optional[Any]:
    """Return a libsql connection to the activity DB, or None."""
    url = os.environ.get("TURSO_ACTIVITY_URL") or os.environ.get("TURSO_KANBAN_URL", "")
    token = os.environ.get("TURSO_ACTIVITY_TOKEN") or os.environ.get("TURSO_KANBAN_TOKEN", "")
    if not url or not token:
        return None
    try:
        import libsql
        return libsql.connect(url, auth_token=token)
    except Exception:
        return None


def get_activity_feed(limit_per_repo: int = 4) -> List[Dict[str, Any]]:
    """Return per-repo activity summaries for the dashboard.

    Each entry:
        repo_slug, last_active (ISO str), idle_hours (float),
        events: [{event_type, actor, title, url, occurred_at}, ...]
    """
    conn = _connect()
    if conn is None:
        return []

    try:
        cur = conn.cursor()

        # Single query: rank events per repo, keep top N using a window function.
        # libsql/SQLite supports ROW_NUMBER().
        cur.execute(
            "SELECT repo_slug, event_type, actor, title, url, occurred_at "
            "FROM ("
            "  SELECT *, ROW_NUMBER() OVER "
            "    (PARTITION BY repo_slug ORDER BY occurred_at DESC) AS rn "
            "  FROM activity_events"
            ") WHERE rn <= ? "
            "ORDER BY repo_slug, occurred_at DESC",
            (limit_per_repo,),
        )
        rows = cur.fetchall()

        now = datetime.now(timezone.utc)
        repos_map: Dict[str, Dict[str, Any]] = {}

        for r in rows:
            slug = r[0]
            event = {
                "event_type": r[1],
                "actor": r[2],
                "title": r[3],
                "url": r[4],
                "occurred_at": r[5],
            }
            if slug not in repos_map:
                last_active_str = event["occurred_at"] or ""
                try:
                    last_dt = datetime.fromisoformat(last_active_str.replace("Z", "+00:00"))
                    idle_hours = (now - last_dt).total_seconds() / 3600
                except (ValueError, TypeError):
                    idle_hours = -1
                repos_map[slug] = {
                    "repo_slug": slug,
                    "last_active": last_active_str,
                    "idle_hours": round(idle_hours, 1),
                    "events": [],
                }
            repos_map[slug]["events"].append(event)

        feed = list(repos_map.values())
        feed.sort(key=lambda r: r["last_active"] or "", reverse=True)
        return feed

    except Exception:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass
