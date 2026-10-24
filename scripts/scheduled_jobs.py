"""Everything scheduled to run on this Mac (#8377).

Why: Erik wants one place that answers "what runs on this Mac?", including jobs
that are installed but switched off. ``alert_digest.py`` shares the
``launchctl list`` parser below instead of keeping its own copy, so this module
imports no project modules: it loads the same way as ``scripts.scheduled_jobs``
and as a sibling of the digest script. (``mini_scan.py`` keeps its own copy
because it is piped over ssh as a standalone script.)
"""

import subprocess

# Each external read (launchctl, crontab) gets this long before it is reported
# as failed.
SOURCE_TIMEOUT_S = 15


def parse_launchctl_list(stdout: str) -> list[dict]:
    """Rows of `launchctl list`: columns are PID, last-exit-status, Label.

    A numeric PID means currently running; the status is that of the previous
    run, and "-" means none. A malformed status becomes None, so one odd line
    cannot hide every other job.
    """
    rows = []
    for line in stdout.splitlines()[1:]:  # skip header
        parts = line.split(None, 2)
        if len(parts) != 3:
            continue
        pid_s, status_s, label = parts
        try:
            last_exit = None if status_s == "-" else int(status_s)
        except ValueError:
            last_exit = None
        rows.append({"label": label, "pid": None if pid_s == "-" else pid_s, "last_exit": last_exit})
    return rows


def launchctl_list() -> list[dict]:
    """Run `launchctl list`. Raises on a nonzero exit or timeout; the caller decides."""
    proc = subprocess.run(
        ["launchctl", "list"], capture_output=True, text=True, timeout=SOURCE_TIMEOUT_S, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(f"launchctl exit {proc.returncode}: {proc.stderr[:200]}")
    return parse_launchctl_list(proc.stdout)
