"""
calendar_poller.py — Phase 3 agent hook for the AI-first calendar.

Run modes
---------
1. Standalone (cron, every 5–15 min):
   uv run scripts/hooks/calendar_poller.py [--machine MacBook] [--within 60] [--dry-run]

2. Via pt CLI:
   ./pt calendar poll [--machine MacBook] [--within 60] [--dry-run]

What it does each run
---------------------
1. Calls CalendarManager.get_upcoming_reminders(within_minutes, machine)
2. For each firing event:
   a. Writes a memory entry to open-brain (MCP) if MCP available, else to a
      local append-only NDJSON log at data/calendar_notifications.ndjson
   b. If the event has a `prompt` field, runs it through the Ollama local agent
      (if available) or logs it as a pending prompt for manual followup
   c. Calls CalendarManager.mark_notified(event_id) so it doesn't re-fire
3. Writes a structured run-log entry to data/logs/calendar_poller.ndjson
4. Exits with code 0 (no events or events processed) or 1 (fatal error)

Output
------
- Human: prints a summary table (unless --quiet)
- Machine: --json flag for structured JSON output

Exit codes
----------
0  Normal — whether or not events fired
1  Fatal error (DB unavailable, etc.) — for cron health monitoring
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap path so this runs standalone OR imported from pt.py
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from scripts.db.calendar_manager import CalendarManager

logger = logging.getLogger("calendar_poller")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = _ROOT / "data"
LOG_DIR = DATA_DIR / "logs"
NOTIFICATIONS_LOG = DATA_DIR / "calendar_notifications.ndjson"
POLLER_LOG = LOG_DIR / "calendar_poller.ndjson"


def _detect_machine() -> str:
    """Best-effort machine name from hostname or env."""
    override = os.getenv("PT_MACHINE")
    if override:
        return override
    hostname = socket.gethostname().lower()
    if "mini" in hostname or "openclaw" in hostname:
        return "OpenClaw"
    if "macbook" in hostname or "mac-book" in hostname:
        return "MacBook"
    return hostname


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_ndjson(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _write_brain(event: dict, machine: str) -> bool:
    """Write a memory to open-brain via the brain CLI or MCP subprocess.

    Strategy:
      1. Try the open-brain-mcp server via its Python client if importable.
      2. Fall back to the brain.py CLI script in the ai-memory-replay project.
      3. Fall back to local NDJSON logging (caller handles this case).

    Returns True if an external write succeeded, False otherwise (graceful degradation).
    """
    # Derive agent_family from machine rather than hardcoding 'claude'
    machine_to_family = {
        "MacBook": "claude",
        "OpenClaw": "codex",
        "Both": "claude",
        "web": "claude",
    }
    agent_family = machine_to_family.get(machine, "claude")

    content = (
        f"\U0001f4c5 Calendar event fired on {machine}: "
        f"{event['title']} ({event['event_type']}) \u2014 "
        f"{event['event_date']}"
        + (f" at {event['event_time']}" if event.get("event_time") else "")
        + (f"\nPrompt: {event['prompt']}" if event.get("prompt") else "")
    )

    # Strategy 1: open-brain MCP Python client (when running inside MCP session)
    try:
        from open_brain import brain_write  # type: ignore[import]
        brain_write(
            content=content,
            project=event.get("project_id", ""),
            type="observation",
            scope="shared",
            source_agent="calendar_poller",
            agent_family=agent_family,
        )
        return True
    except ImportError:
        pass  # MCP client not importable — try CLI
    except Exception as exc:
        logger.warning("open-brain Python client failed: %s", exc)

    # Strategy 2: brain CLI subprocess (ai-memory-replay project)
    brain_candidates = [
        _ROOT.parent / "ai-memory-replay" / "brain.py",
        _ROOT.parent / "open-brain" / "brain.py",
    ]
    brain_cli = next((p for p in brain_candidates if p.exists()), None)
    if brain_cli:
        try:
            uv = os.getenv("UV_BIN", str(Path.home() / ".local" / "bin" / "uv"))
            result = subprocess.run(
                [uv, "run", str(brain_cli), "write", content,
                 "--type", "observation",
                 "--scope", "shared",
                 "--source-agent", "calendar_poller",
                 "--agent-family", agent_family,
                 "--project", event.get("project_id", "")],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                return True
            logger.warning("brain CLI exited %d: %s", result.returncode, result.stderr.strip()[:200])
        except subprocess.TimeoutExpired:
            logger.warning("brain CLI timed out")
        except Exception as exc:
            logger.warning("brain CLI error: %s", exc)

    logger.info("open-brain write unavailable for event %d — using local NDJSON fallback", event["id"])
    return False


def _run_agent_prompt(event: dict, dry_run: bool) -> dict:
    """Run the event's agent prompt via Ollama if available.

    Returns a dict with keys: attempted, model, output, error
    """
    prompt = event.get("prompt", "").strip()
    if not prompt:
        return {"attempted": False}

    if dry_run:
        return {"attempted": True, "dry_run": True, "prompt_preview": prompt[:100]}

    # Try to invoke ollama as a subprocess (non-blocking, fire-and-forget)
    try:
        model = os.getenv("PT_AGENT_MODEL", "qwen2.5-coder:7b")
        full_prompt = (
            f"You are an AI agent assistant embedded in the project-tracker ecosystem.\n"
            f"The following calendar event just fired and requires your action:\n\n"
            f"Event: {event['title']}\n"
            f"Type: {event['event_type']}\n"
            f"Date: {event['event_date']}"
            + (f" at {event['event_time']}" if event.get("event_time") else "")
            + "\n\n"
            f"Prompt from event creator:\n{prompt}\n\n"
            f"Please respond with what you would do or any relevant analysis."
        )
        result = subprocess.run(
            ["ollama", "run", model, full_prompt],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return {
            "attempted": True,
            "model": model,
            "exit_code": result.returncode,
            "output": result.stdout.strip()[:2000] if result.stdout else "",
            "error": result.stderr.strip()[:500] if result.stderr else "",
        }
    except FileNotFoundError:
        return {"attempted": True, "error": "ollama not found — prompt logged only"}
    except subprocess.TimeoutExpired:
        return {"attempted": True, "error": "ollama timed out — prompt logged only"}
    except Exception as exc:
        return {"attempted": True, "error": str(exc)}


# ---------------------------------------------------------------------------
# Core poll function
# ---------------------------------------------------------------------------

def poll(
    *,
    machine: str | None = None,
    within_minutes: int = 60,
    dry_run: bool = False,
    quiet: bool = False,
    as_json: bool = False,
) -> dict:
    """Run one poll cycle. Returns a summary dict.

    This function is importable from pt.py and called by the CLI command.
    """
    effective_machine = machine or _detect_machine()
    started_at = _now_iso()

    results = {
        "started_at": started_at,
        "machine": effective_machine,
        "within_minutes": within_minutes,
        "dry_run": dry_run,
        "events_fired": [],
        "events_total": 0,
        "errors": [],
    }

    try:
        cm = CalendarManager()
        cm.ensure_tables()
        events = cm.get_upcoming_reminders(
            within_minutes=within_minutes,
            machine=effective_machine,
        )
    except Exception as exc:
        msg = f"CalendarManager error: {exc}"
        logger.error(msg)
        results["errors"].append(msg)
        _append_ndjson(POLLER_LOG, {**results, "finished_at": _now_iso(), "status": "error"})
        return results

    results["events_total"] = len(events)

    for event in events:
        event_result = {
            "id": event["id"],
            "title": event["title"],
            "event_type": event["event_type"],
            "event_date": event["event_date"],
            "event_time": event.get("event_time"),
            "machine": event.get("machine"),
            "project_id": event.get("project_id"),
            "has_prompt": bool(event.get("prompt")),
            "brain_written": False,
            "agent_result": None,
            "notified": False,
        }

        # 1. Write to open-brain / fallback NDJSON
        brain_ok = _write_brain(event, effective_machine)
        event_result["brain_written"] = brain_ok

        if not brain_ok:
            # Fallback: local notification log
            notification = {
                "timestamp": _now_iso(),
                "machine": effective_machine,
                "event_id": event["id"],
                "event_title": event["title"],
                "event_type": event["event_type"],
                "event_date": event["event_date"],
                "event_time": event.get("event_time"),
                "project_id": event.get("project_id"),
                "prompt": event.get("prompt"),
            }
            if not dry_run:
                _append_ndjson(NOTIFICATIONS_LOG, notification)
            event_result["local_log"] = str(NOTIFICATIONS_LOG)

        # 2. Run agent prompt if present
        agent_result = _run_agent_prompt(event, dry_run)
        event_result["agent_result"] = agent_result

        # If agent ran successfully, log its output too
        if agent_result.get("attempted") and agent_result.get("output") and not dry_run:
            _append_ndjson(NOTIFICATIONS_LOG, {
                "timestamp": _now_iso(),
                "type": "agent_response",
                "event_id": event["id"],
                "model": agent_result.get("model"),
                "output": agent_result.get("output", "")[:2000],
            })

        # 3. Mark notified so it doesn't re-fire
        if not dry_run:
            try:
                cm.mark_notified(event["id"])
                event_result["notified"] = True
            except Exception as exc:
                event_result["notified"] = False
                event_result["notify_error"] = str(exc)
                # Propagate to results.errors so main() exits 1 and cron sees failure
                results["errors"].append(
                    f"mark_notified({event['id']}) failed: {exc} — event may re-fire"
                )
                logger.error("mark_notified(%d) failed: %s", event["id"], exc)

        results["events_fired"].append(event_result)

    results["finished_at"] = _now_iso()
    results["status"] = "ok"

    # Write run log
    if not dry_run:
        _append_ndjson(POLLER_LOG, results)

    # Output
    if as_json:
        print(json.dumps(results, indent=2))
    elif not quiet:
        _print_summary(results)

    return results


def _print_summary(results: dict) -> None:
    total = results["events_total"]
    machine = results["machine"]
    dry = " [DRY RUN]" if results.get("dry_run") else ""
    print(f"\n📅 Calendar poller — {machine}{dry}")
    print(f"   Window: {results['within_minutes']} min  |  Events fired: {total}")

    if total == 0:
        print("   ✓ No events due in this window.\n")
        return

    for ev in results["events_fired"]:
        status = "✓" if ev.get("notified") else ("~" if results.get("dry_run") else "✗")
        brain = "🧠" if ev.get("brain_written") else "📝"
        prompt = "🤖" if ev.get("has_prompt") else "  "
        print(
            f"   {status} {brain}{prompt} [{ev['event_type']:9}] "
            f"{ev['event_date']}"
            + (f" {ev['event_time']}" if ev.get("event_time") else "")
            + f"  {ev['title']}"
            + (f"  ({ev['project_id']})" if ev.get("project_id") else "")
        )

    print()
    if results.get("errors"):
        for err in results["errors"]:
            print(f"   ⚠ {err}")


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Poll calendar events and trigger agent hooks."
    )
    parser.add_argument(
        "--machine",
        default=None,
        help="Machine to filter events for (default: auto-detect from hostname or PT_MACHINE env).",
    )
    parser.add_argument(
        "--within",
        type=int,
        default=60,
        metavar="MINUTES",
        help="Notify events firing within this many minutes (default: 60).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would fire without marking events as notified.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress human-readable output.",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output results as JSON.",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    results = poll(
        machine=args.machine,
        within_minutes=args.within,
        dry_run=args.dry_run,
        quiet=args.quiet,
        as_json=args.as_json,
    )

    return 1 if results.get("errors") else 0


if __name__ == "__main__":
    sys.exit(main())
