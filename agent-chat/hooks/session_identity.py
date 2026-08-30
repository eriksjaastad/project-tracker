#!/usr/bin/env python3
"""SessionStart hook — resolve and freeze this session's Agent Chat address.

Runs once per session. Resolves the project name from the session's launch
directory and stores it, so every later consumer (check_chat.sh, `pt message`)
reads a fixed answer instead of re-deriving from the current directory.

Hard rule, same as every other hook here: NEVER block Claude. Any failure
exits 0 with empty JSON. But unlike the old chat hooks, a failure is written
to a drop log rather than vanishing — silent exits are the reason Agent Chat
went unnoticed for five weeks.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

AGENT_CHAT_ROOT = Path(__file__).resolve().parent.parent
DROP_LOG = Path.home() / ".claude" / "open-brain" / "agent_chat_drops.log"


def _drop(reason: str, detail: str = "") -> None:
    """Record why identity resolution failed. Best-effort, never raises."""
    try:
        DROP_LOG.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with DROP_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{stamp}\tsession_identity\t{reason}\t{detail[:200]}\n")
    except OSError:
        pass


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        _drop("payload_parse_error")
        print(json.dumps({}))
        return

    session_id = payload.get("session_id") or os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    cwd = payload.get("cwd") or os.getcwd()

    if not session_id:
        _drop("no_session_id", str(cwd))
        print(json.dumps({}))
        return

    sys.path.insert(0, str(AGENT_CHAT_ROOT))
    try:
        import identity
    except ImportError as exc:
        _drop(f"import_error:{exc}")
        print(json.dumps({}))
        return

    try:
        # Cache the machine qualifier so check_chat.sh can request
        # `for_machine=` without paying a Python start-up per Bash call.
        identity.write_machine()
    except Exception as exc:  # noqa: BLE001
        _drop(f"machine_cache_error:{type(exc).__name__}", str(exc))

    try:
        address = identity.resolve_for_session(session_id, cwd)
    except Exception as exc:  # noqa: BLE001 - a hook must never take down a session
        _drop(f"resolve_error:{type(exc).__name__}", str(exc))
        print(json.dumps({}))
        return

    if address is None:
        # Outside any project. Legitimate (a scratch dir, $HOME), so this is
        # not an error — but record it, because an agent with no address
        # silently receives nothing.
        _drop("no_project_for_cwd", str(cwd))

    print(json.dumps({}))


if __name__ == "__main__":
    main()
