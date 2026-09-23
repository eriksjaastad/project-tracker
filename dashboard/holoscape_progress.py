"""Read-only, source-labeled progress data for the temporary Holoscape page."""

from __future__ import annotations

import csv
import io
import json
import os
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from dashboard.github_cache import GitHubCache
from scripts.db.manager import DatabaseManager


START = date(2026, 9, 15)
DISPLAY_ZONE = ZoneInfo("America/New_York")
REPO = "eriksjaastad/holoscape"
PR_NUMBER = 173
PR_URL = f"https://github.com/{REPO}/pull/{PR_NUMBER}"
_BOARD_CACHE = GitHubCache(ttl=300, label="Holoscape board")
_GITHUB_CACHE = GitHubCache(ttl=300)
_HERMES_CACHE = GitHubCache(ttl=300, label="Hermes metadata")


def _timestamp_day(value: str | int | float) -> str:
    if isinstance(value, (int, float)):
        moment = datetime.fromtimestamp(value, timezone.utc)
    else:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            # task_history stores machine-local naive timestamps.
            moment = moment.replace(tzinfo=DISPLAY_ZONE)
    return moment.astimezone(DISPLAY_ZONE).date().isoformat()


def _fetched_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_board() -> dict:
    """Read one project's event ledger through the reviewed DB manager."""
    rows = DatabaseManager().task_history_events(START.isoformat(), "holoscape")
    daily: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        day = _timestamp_day(row["timestamp"])
        counts = daily[day]
        if row["event_type"] == "created":
            counts["task_created"] += 1
        if row["event_type"] == "completed" or row["new_status"] == "Done":
            counts["task_completed"] += 1
        if row["old_status"] == "In Progress" and row["new_status"] == "Review":
            counts["review_entries"] += 1
        if row["old_status"] == "Review" and row["new_status"] == "In Progress":
            counts["review_bounces"] += 1
    return {
        "daily": dict(daily), "fetched_at": _fetched_at(), "events": len(rows),
        "coverage": "Holoscape task creation, completion, and review transitions in Project Tracker.",
    }


def _gha_binary() -> str:
    found = shutil.which("gha")
    if found:
        return found
    fallback = Path.home() / "bin" / "gha"
    if fallback.is_file() and os.access(fallback, os.X_OK):
        return str(fallback)
    raise RuntimeError("Managed GitHub CLI unavailable")


def _gha_json(args: list[str], *, paginated: bool = False, page_key: str | None = None) -> object:
    cmd = [_gha_binary(), "api"]
    if paginated:
        cmd.extend(["--paginate", "--slurp"])
    cmd.extend(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("GitHub source unavailable") from exc
    if result.returncode != 0:
        # CLI stderr may include auth material. Do not return or log it.
        raise RuntimeError("GitHub source unavailable")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GitHub source returned invalid JSON") from exc
    if paginated:
        if not isinstance(payload, list):
            raise RuntimeError("GitHub source returned invalid pages")
        pages = [page.get(page_key) if isinstance(page, dict) else None
                 for page in payload] if page_key else payload
        if any(not isinstance(page, list) for page in pages):
            raise RuntimeError("GitHub source returned invalid pages")
        return [item for page in pages for item in page]
    return payload


def fetch_github() -> dict:
    """Collect complete dated activity for PRs active in the observation window."""
    pr = _gha_json([f"repos/{REPO}/pulls/{PR_NUMBER}"])
    pull_requests = _gha_json([f"repos/{REPO}/pulls?state=all&per_page=100"], paginated=True)
    if not isinstance(pr, dict) or not all(isinstance(x, dict) for x in pull_requests):
        raise RuntimeError("GitHub source returned invalid records")

    daily: dict[str, Counter] = defaultdict(Counter)
    cohort = [pull for pull in pull_requests if (
        pull.get("created_at") and _timestamp_day(pull["created_at"]) >= START.isoformat()
    ) or (
        pull.get("merged_at") and _timestamp_day(pull["merged_at"]) >= START.isoformat()
    )]
    if not any(pull.get("number") == PR_NUMBER for pull in cohort):
        raise RuntimeError("Experimental PR missing from complete GitHub history")

    seen_commits: set[str] = set()
    seen_runs: set[int] = set()
    workflow_names: set[str] = set()
    experimental_commits = 0
    experimental_reviews = 0
    for pull in cohort:
        number = pull.get("number")
        branch = (pull.get("head") or {}).get("ref")
        if not isinstance(number, int) or not isinstance(branch, str) or not branch:
            raise RuntimeError("GitHub PR history lacks a source identity")
        commits = _gha_json([f"repos/{REPO}/pulls/{number}/commits?per_page=100"], paginated=True)
        reviews = _gha_json([f"repos/{REPO}/pulls/{number}/reviews?per_page=100"], paginated=True)
        branch_arg = quote(branch, safe="")
        runs = _gha_json(
            [f"repos/{REPO}/actions/runs?branch={branch_arg}&per_page=100"],
            paginated=True, page_key="workflow_runs",
        )
        if not all(isinstance(x, dict) for x in commits + reviews + runs):
            raise RuntimeError("GitHub source returned invalid records")
        if number == PR_NUMBER:
            experimental_commits = len(commits)
            experimental_reviews = len(reviews)
        for commit in commits:
            sha = commit.get("sha")
            stamp = (commit.get("commit") or {}).get("committer") or {}
            if sha and sha not in seen_commits and stamp.get("date"):
                seen_commits.add(sha)
                daily[_timestamp_day(stamp["date"])]["commits"] += 1
        for review in reviews:
            if review.get("submitted_at") and review.get("state") != "PENDING":
                daily[_timestamp_day(review["submitted_at"])]["github_reviews"] += 1
        for run in runs:
            run_id = run.get("id")
            if not isinstance(run_id, int) or run_id in seen_runs:
                continue
            seen_runs.add(run_id)
            if run.get("name"):
                workflow_names.add(run["name"])
            if not run.get("created_at"):
                continue
            day = _timestamp_day(run["created_at"])
            if run.get("status") != "completed":
                daily[day]["ci_pending"] += 1
            elif run.get("conclusion") == "success":
                daily[day]["ci_success"] += 1
            elif run.get("conclusion") == "failure":
                daily[day]["ci_failure"] += 1
            else:
                daily[day]["ci_other"] += 1

    for pull in cohort:
        if pull.get("created_at") and _timestamp_day(pull["created_at"]) >= START.isoformat():
            daily[_timestamp_day(pull["created_at"])]["prs_opened"] += 1
        if pull.get("merged_at") and _timestamp_day(pull["merged_at"]) >= START.isoformat():
            daily[_timestamp_day(pull["merged_at"])]["prs_merged"] += 1
    return {
        "daily": dict(daily),
        "fetched_at": _fetched_at(),
        "coverage": "Holoscape PRs opened or merged since September 15; check runs are scoped by PR head branch.",
        "pr": {
            "url": PR_URL,
            "state": pr.get("state"),
            "merged": bool(pr.get("merged")),
            "head_sha": (pr.get("head") or {}).get("sha"),
            "created_at": pr.get("created_at"),
            "merged_at": pr.get("merged_at"),
            "commits": experimental_commits,
            "reviews": experimental_reviews,
            "cohort_pull_requests": len(cohort),
            "workflow_names": sorted(workflow_names),
        },
    }


# These are the two observed Holoscape worker cron IDs, not all Hermes runs.
# A new worker job needs explicit source verification before it enters the chart.
_HERMES_SQL = """
WITH parents AS (
  SELECT id FROM sessions
  WHERE id GLOB 'cron_9bfc0297fa83_*' OR id GLOB 'cron_c42ebb138993_*'
), rows AS (
  SELECT 'manager' kind, started_at occurred_at, ended_at, model,
    billing_provider provider, cost_status, input_tokens, output_tokens,
    cache_read_tokens, cache_write_tokens, 0 tool_references
  FROM sessions WHERE id IN parents
  UNION ALL
  SELECT 'delegate', started_at, ended_at, model, billing_provider,
    cost_status, input_tokens, output_tokens, cache_read_tokens,
    cache_write_tokens, 0
  FROM sessions WHERE parent_session_id IN parents
  UNION ALL
  SELECT 'deepseek_cli', started_at, ended_at, model, billing_provider,
    cost_status, input_tokens, output_tokens, cache_read_tokens,
    cache_write_tokens, 0
  FROM sessions
  WHERE source = 'cli' AND cwd LIKE '%/holoscape-deepseek-worker'
  UNION ALL
  SELECT 'worktree_reference', m.timestamp, NULL, NULL, NULL, NULL,
    0, 0, 0, 0, COUNT(*)
  FROM parents p JOIN messages m ON m.session_id = p.id
  JOIN json_each(CASE WHEN json_valid(m.tool_calls) THEN m.tool_calls ELSE '[]' END) j
  WHERE m.role = 'assistant'
    AND CAST(json_extract(j.value, '$.function.arguments') AS TEXT)
      LIKE '%holoscape-deepseek-worker%'
  GROUP BY m.id
)
SELECT kind, occurred_at, ended_at, model, provider, cost_status,
  input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
  tool_references FROM rows ORDER BY occurred_at;
"""


def fetch_hermes() -> dict:
    """Read only whitelisted aggregate metadata from the Mini; no messages leave it."""
    host = os.environ.get("PT_MINI_HOST", "eriks-mac-mini")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", host):
        raise RuntimeError("Mini host setting is invalid")
    remote = (
        'sqlite3 -readonly -header -csv -cmd ".timeout 3000" '
        '-cmd "PRAGMA query_only=ON" "$HOME/.hermes/state.db"'
    )
    try:
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host, remote],
            input=_HERMES_SQL, capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Hermes metadata source unavailable") from exc
    if result.returncode != 0:
        raise RuntimeError("Hermes metadata source unavailable")

    daily: dict[str, Counter] = defaultdict(Counter)
    models: Counter = Counter()
    unknown_cost_sessions = 0
    row_count = 0
    try:
        reader = csv.DictReader(io.StringIO(result.stdout))
        expected = {"kind", "occurred_at", "model", "cost_status", "input_tokens",
                    "output_tokens", "cache_read_tokens", "tool_references"}
        if not reader.fieldnames or not expected.issubset(reader.fieldnames):
            raise ValueError("Missing metadata columns")
        for row in reader:
            row_count += 1
            day = _timestamp_day(float(row["occurred_at"]))
            counts = daily[day]
            kind = row["kind"]
            if kind == "worktree_reference":
                counts["worktree_references"] += int(row["tool_references"] or 0)
                continue
            if kind not in {"manager", "delegate", "deepseek_cli"}:
                raise ValueError("Unknown metadata kind")
            counts[f"{kind}_sessions"] += 1
            counts[f"{kind}_input_tokens"] += int(row["input_tokens"] or 0)
            counts[f"{kind}_output_tokens"] += int(row["output_tokens"] or 0)
            counts[f"{kind}_cache_read_tokens"] += int(row["cache_read_tokens"] or 0)
            if row["ended_at"]:
                counts[f"{kind}_session_minutes"] += max(
                    0.0, (float(row["ended_at"]) - float(row["occurred_at"])) / 60.0
                )
            models[f"{kind}:{row['model'] or 'unknown'}"] += 1
            if kind == "deepseek_cli" and row["cost_status"] != "known":
                unknown_cost_sessions += 1
    except (ValueError, TypeError, OverflowError) as exc:
        raise RuntimeError("Hermes metadata source returned invalid records") from exc
    return {
        "daily": dict(daily), "fetched_at": _fetched_at(), "records": row_count,
        "models": dict(models), "deepseek_cost_unknown_sessions": unknown_cost_sessions,
        "coverage": "Two verified Holoscape cron IDs, linked delegates, and CLI sessions in the worker worktree. Session-minutes sum durations; worktree references count only matching tool calls.",
    }


_FIELDS = {
    "board": ("task_created", "task_completed", "review_entries", "review_bounces"),
    "github": ("commits", "github_reviews", "prs_opened", "prs_merged",
               "ci_success", "ci_failure", "ci_pending", "ci_other"),
    "hermes": (
        "manager_sessions", "delegate_sessions", "deepseek_cli_sessions",
        "worktree_references", "manager_session_minutes", "delegate_session_minutes",
        "deepseek_cli_session_minutes", "manager_input_tokens", "manager_output_tokens",
        "delegate_input_tokens", "delegate_output_tokens", "deepseek_cli_input_tokens",
        "deepseek_cli_output_tokens", "deepseek_cli_cache_read_tokens",
    ),
}


def progress_snapshot() -> dict:
    """Return a fast cached response, preserving per-source stale snapshots."""
    snapshots = {
        "board": _BOARD_CACHE.read(fetch_board),
        "github": _GITHUB_CACHE.read(fetch_github),
        "hermes": _HERMES_CACHE.read(fetch_hermes),
    }
    observed_through = {
        name: _timestamp_day(snap["fetched_at"]) if snap.get("fetched_at") else None
        for name, snap in snapshots.items()
    }
    sources = {}
    for name, snap in snapshots.items():
        has_data = "daily" in snap
        sources[name] = {
            "status": "stale" if has_data and snap["stale"] else
                      "ok" if has_data else "loading" if snap["refreshing"] else "unavailable",
            "fetched_at": snap.get("fetched_at"),
            "refreshing": snap["refreshing"],
            "refresh_error": snap["refresh_error"],
            "coverage": snap.get("coverage"),
        }
    sources["billing"] = {
        "status": "unavailable", "fetched_at": None,
        "coverage": "No verified Holoscape DeepSeek charges; token counts are not dollars.",
    }

    series = []
    today = datetime.now(DISPLAY_ZONE).date()
    current = START
    while current <= today:
        day = current.isoformat()
        item: dict = {"date": day}
        for name, snap in snapshots.items():
            counts = snap.get("daily", {}).get(day, {})
            for field in _FIELDS[name]:
                if "daily" not in snap or observed_through[name] is None or day > observed_through[name]:
                    item[field] = None
                elif field.endswith("_minutes"):
                    item[field] = round(float(counts.get(field, 0)), 1)
                else:
                    item[field] = int(counts.get(field, 0))
        series.append(item)
        current += timedelta(days=1)

    return {
        "window": {"start": START.isoformat(), "end": today.isoformat(),
                   "timezone": str(DISPLAY_ZONE)},
        "series": series, "sources": sources,
        "pr": snapshots["github"].get("pr"),
        "models": snapshots["hermes"].get("models"),
        "deepseek_cost_usd": None,
    }
