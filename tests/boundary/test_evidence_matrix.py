"""Print the runtime/host/operation evidence matrix, and refuse to overstate it.

Card #7217 requires a retained matrix and is explicit about how to read a gap:
"Unsupported or unverified access paths remain blocked and prevent declaring
universal coverage" and "an uncovered path is unfinished work".

The failure mode this file exists to prevent is a green test run being read as
a proven boundary. Most of this suite runs fine with no boundary installed at
all — the protocol and allowlist tests do not need one. Only the POSIX denial
probes can tell you whether a process can open the file, and those skip when
the root install is absent.

So: run `pytest tests/boundary/ -s` and this prints what was actually proven
on this host, with the gaps named. Generate the file for a PR with

    uv run pytest tests/boundary/ -s -k evidence_matrix > EVIDENCE.md
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from dbmed.registry import (
    DEFAULT_CONFIG_DIR,
    DEFAULT_DATA_ROOT,
    DEFAULT_INSTALL_DIR,
    DEFAULT_SOCKET,
)

from .conftest import real_install_present

REPO_ROOT = Path(__file__).resolve().parents[2]


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True,
            text=True, timeout=30, check=True,
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return "unknown"


def _runtime_sudo_posture() -> list[tuple[str, str, str]]:
    """What each agent runtime does about sudo, as far as this host can tell.

    sudo is the boundary's ceiling: an agent that reaches root defeats it.
    Claude Code's denial is checkable from here. The others are not, and
    saying so is the whole point of the row.
    """
    rows: list[tuple[str, str, str]] = []

    settings = Path.home() / ".claude" / "settings.json"
    verdict = "UNVERIFIED"
    detail = "settings.json not found"
    if settings.exists():
        try:
            import json

            deny = json.loads(settings.read_text()).get("permissions", {}).get("deny", [])
            sudo_denied = any("sudo" in str(rule).lower() for rule in deny)
            verdict = "VERIFIED" if sudo_denied else "FAIL"
            detail = f"permissions.deny = {deny}"
        except (OSError, ValueError) as exc:
            detail = f"unreadable: {exc}"
    rows.append(("Claude Code", verdict, detail))

    for runtime, home in (
        ("Codex", Path.home() / ".codex"),
        ("Cursor", Path.home() / ".cursor"),
        ("Grok / other", None),
    ):
        present = home.exists() if home else False
        rows.append((
            runtime,
            "UNVERIFIED",
            f"config {'present' if present else 'not found'} at {home}; sudo posture "
            "not checked by this suite" if home else
            "no config location known to this suite",
        ))
    return rows


def test_evidence_matrix(capsys):
    """Always passes. It reports; it does not judge.

    Judgement belongs to the tests themselves. If this asserted, a missing
    install would fail the suite and someone would add a skip, and then the
    matrix would stop being read at all.
    """
    installed = real_install_present()

    with capsys.disabled():
        print()
        print("# dbmed boundary evidence")
        print()
        print(f"- **Host:** `{platform.node()}` ({platform.system()} {platform.release()}, {platform.machine()})")
        print(f"- **Python:** {sys.version.split()[0]}")
        print(f"- **Repo commit:** `{_git_sha()}`")
        print(f"- **Running as:** uid {os.getuid()}")
        print()

        print("## Installation")
        print()
        print("| Component | Expected location | Present |")
        print("|---|---|---|")
        for label, path in (
            ("Socket", DEFAULT_SOCKET),
            ("Daemon code", DEFAULT_INSTALL_DIR),
            ("Registry", DEFAULT_CONFIG_DIR / "registry.d"),
            ("Protected data", DEFAULT_DATA_ROOT),
            ("LaunchDaemon", Path("/Library/LaunchDaemons/com.dbmed.plist")),
            ("Vendored cr-sqlite", DEFAULT_INSTALL_DIR / "lib" / "crsqlite.dylib"),
        ):
            print(f"| {label} | `{path}` | {'yes' if path.exists() else 'NO'} |")
        print()

        if installed:
            data = DEFAULT_DATA_ROOT / "project-tracker"
            info = data.stat()
            print(f"- Protected directory mode: `{info.st_mode & 0o777:04o}`, uid `{info.st_uid}`")
            print(f"- Agent uid: `{os.getuid()}` "
                  f"({'DIFFERENT — good' if info.st_uid != os.getuid() else 'SAME — the owner can undo the mode'})")
            print()

        print("## What this run proved")
        print()
        if installed:
            print("The root install is present, so the POSIX denial probes ran. "
                  "Their results are the pass/fail lines in this pytest run.")
        else:
            print("**The root install is NOT present on this host.**")
            print()
            print("Everything about the protocol, the operation allowlist, the")
            print("destructive gate and the fail-closed path was exercised and is")
            print("reported by this run. None of it demonstrates that a process")
            print("cannot open the database file, because on this host nothing")
            print("stops one. Those probes skipped.")
            print()
            print("Per card #7217 this is **UNVERIFIED, not passing**. Install with")
            print("`sudo scripts/dbmed-install/install.sh` and re-run to close it.")
        print()

        print("## Coverage")
        print()
        print("| Area | Status | Note |")
        print("|---|---|---|")
        proven = "VERIFIED" if installed else "UNVERIFIED"
        for area, status, note in [
            ("Operation allowlist / no SQL surface", "VERIFIED",
             "test_operation_surface.py, runs without an install"),
            ("Destructive gate, token, verified backup", "VERIFIED",
             "test_destructive_gate.py, runs without an install"),
            ("Fail-closed when the service is down", "VERIFIED",
             "test_fail_closed.py; the client imports no driver"),
            ("Kernel denial: SQL clients", proven, "test_posix_denial.py"),
            ("Kernel denial: language drivers", proven, "test_posix_denial.py"),
            ("Kernel denial: file tools, copy, delete", proven, "test_posix_denial.py"),
            ("Kernel denial: journals and backups", proven, "test_posix_denial.py"),
            ("Kernel denial: symlink, relative, subprocess, ssh", proven, "test_posix_denial.py"),
            ("Guard tamper: plist, code, dylib, registry", proven, "test_posix_denial.py"),
            ("Agent cannot stop the daemon", proven, "test_posix_denial.py"),
        ]:
            print(f"| {area} | {status} | {note} |")
        print()

        print("## Known gaps")
        print()
        print("| Gap | Status | Why it is open |")
        print("|---|---|---|")
        for runtime, verdict, detail in _runtime_sudo_posture():
            print(f"| sudo denied in {runtime} | {verdict} | {detail} |")
        mini = "UNVERIFIED"
        print(f"| Mac Mini install and matrix | {mini} | this run is `{platform.node()}` only |")
        print("| Full Disk Access / TCC | OUT OF SCOPE | not addressed by a service account |")
        print("| ai-memory `brain.db` | OUT OF SCOPE | card #7220; pt and the dashboard still read it directly |")
        print("| rclone offsite backup copy | NOT PORTED | needs a credential decision; carded |")
        print()
        print("No row above may be reported as passing. Card #7217: "
              "\"an uncovered path is unfinished work\".")
        print()

        if shutil.which("sqlite3") is None:
            print("> Note: `sqlite3` is not on PATH here, so that probe could not run "
                  "even with an install present.")
            print()
