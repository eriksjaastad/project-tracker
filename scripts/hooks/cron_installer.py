"""
cron_installer.py — Install / remove the calendar_poller cron job.

Usage (via pt CLI):
    ./pt calendar install-poll-cron [--machine MacBook] [--interval 10] [--remove]

What it does
------------
- Generates a crontab entry that runs calendar_poller.py every N minutes
  using `uv run` (ecosystem standard) with output logged to data/logs/poller.log
- Installs it idempotently: removes any existing pt-calendar-poller lines first
- Supports --remove to cleanly uninstall
- On --dry-run just prints the crontab line, doesn't touch crontab

The installed entry is tagged with a sentinel comment so it can be found
and updated without touching the rest of the user's crontab.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

SENTINEL = "# pt-calendar-poller"
LOG_PATH = _ROOT / "data" / "logs" / "poller.log"
POLLER_SCRIPT = _ROOT / "scripts" / "hooks" / "calendar_poller.py"

# Allowlist used to validate machine before shell interpolation
_VALID_MACHINES = {"MacBook", "OpenClaw", "Both", "web"}


def _get_crontab() -> str:
    try:
        result = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return result.stdout
    except subprocess.TimeoutExpired:
        raise RuntimeError("crontab -l timed out (>10s)")
    # No crontab yet (exit 1 on most systems)
    return ""


def _set_crontab(content: str) -> None:
    try:
        proc = subprocess.run(
            ["crontab", "-"], input=content, text=True,
            capture_output=True, timeout=10
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("crontab write timed out (>10s)")
    if proc.returncode != 0:
        raise RuntimeError(f"crontab write failed: {proc.stderr.strip()}")


def _build_cron_line(
    interval: int,
    machine: str | None,
    within: int,
) -> str:
    """Build the crontab line."""
    # Validate machine against allowlist before shell interpolation
    if machine is not None and machine not in _VALID_MACHINES:
        raise ValueError(
            f"Invalid machine '{machine}'. Must be one of: {', '.join(sorted(_VALID_MACHINES))}"
        )
    machine_flag = f" --machine {machine}" if machine else ""
    # uv run is the ecosystem standard for Python script execution
    script = str(POLLER_SCRIPT)
    log = str(LOG_PATH)
    cmd = (
        f"$HOME/.local/bin/uv run {script}"
        f"{machine_flag} --within {within} --quiet"
        f" >> {log} 2>&1"
    )
    cron_expr = f"*/{interval} * * * *"
    return f"{cron_expr} {cmd} {SENTINEL}"


def install(
    interval: int = 10,
    machine: str | None = None,
    within: int = 60,
    dry_run: bool = False,
    remove: bool = False,
) -> dict:
    """Install or remove the calendar poller cron job.

    Returns a dict with keys: action, line, previous_lines_removed, dry_run
    """
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    existing = _get_crontab()
    lines = existing.splitlines(keepends=True)

    # Remove any existing pt-calendar-poller lines
    cleaned = [l for l in lines if SENTINEL not in l]
    removed_count = len(lines) - len(cleaned)

    if remove:
        if not dry_run:
            _set_crontab("".join(cleaned))
        return {
            "action": "removed",
            "previous_lines_removed": removed_count,
            "dry_run": dry_run,
        }

    new_line = _build_cron_line(interval, machine, within)

    # Append the new line
    new_crontab = "".join(cleaned)
    if not new_crontab.endswith("\n") and new_crontab:
        new_crontab += "\n"
    new_crontab += new_line + "\n"

    if not dry_run:
        _set_crontab(new_crontab)

    return {
        "action": "installed",
        "line": new_line,
        "interval_minutes": interval,
        "within_minutes": within,
        "machine": machine,
        "log_path": str(LOG_PATH),
        "previous_lines_removed": removed_count,
        "dry_run": dry_run,
    }


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--interval", type=int, default=10)
    p.add_argument("--machine", default=None)
    p.add_argument("--within", type=int, default=60)
    p.add_argument("--remove", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    result = install(
        interval=a.interval,
        machine=a.machine,
        within=a.within,
        dry_run=a.dry_run,
        remove=a.remove,
    )
    import json
    print(json.dumps(result, indent=2))
    sys.exit(0)
