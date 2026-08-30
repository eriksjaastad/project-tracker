#!/usr/bin/env bash
#
# install-hooks.sh — wire Agent Chat hooks into this machine's settings.json.
#
# settings.json is deliberately machine-local (it is not synced with the rest
# of ~/.claude), so hook wiring cannot ship in a PR. Run this once per machine.
#
# Idempotent: re-running it does nothing if the hooks are already wired.
#
#   ./agent-chat/install-hooks.sh          # wire
#   ./agent-chat/install-hooks.sh --check  # report status, change nothing

set -euo pipefail

SETTINGS="$HOME/.claude/settings.json"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SESSION_HOOK='$HOME/projects/project-tracker/agent-chat/hooks/session_identity.py'
CHECK_HOOK='bash $HOME/projects/project-tracker/agent-chat/hooks/check_chat.sh'

CHECK_ONLY=0
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1

if [[ ! -f "$SETTINGS" ]]; then
    echo "No settings.json at $SETTINGS" >&2
    exit 1
fi

PYTHON="$REPO_ROOT/venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"

"$PYTHON" - "$SETTINGS" "$SESSION_HOOK" "$CHECK_HOOK" "$CHECK_ONLY" <<'PY'
import json
import shutil
import sys

settings_path, session_hook, check_hook, check_only = sys.argv[1:5]
check_only = check_only == "1"

with open(settings_path) as fh:
    settings = json.load(fh)

hooks = settings.setdefault("hooks", {})


def wired(event, needle):
    for matcher in hooks.get(event, []):
        for hook in matcher.get("hooks", []):
            if needle in hook.get("command", ""):
                return True
    return False


have_session = wired("SessionStart", "session_identity.py")
have_check = wired("PreToolUse", "check_chat.sh")

print(f"SessionStart identity hook: {'wired' if have_session else 'MISSING'}")
print(f"PreToolUse check_chat hook: {'wired' if have_check else 'MISSING'}")

if check_only:
    sys.exit(0 if (have_session and have_check) else 1)

if have_session and have_check:
    print("Nothing to do.")
    sys.exit(0)

backup = settings_path + ".bak-agent-chat"
shutil.copy(settings_path, backup)

added = []
if not have_session:
    hooks.setdefault("SessionStart", []).append(
        {"hooks": [{"type": "command", "command": session_hook}]}
    )
    added.append("SessionStart identity")

# Reporting this as MISSING without wiring it would leave a fresh machine
# looking installed while it never polls for messages at all.
if not have_check:
    hooks.setdefault("PreToolUse", []).append(
        {"matcher": "Bash", "hooks": [{"type": "command", "command": check_hook}]}
    )
    added.append("PreToolUse check_chat")

with open(settings_path, "w") as fh:
    json.dump(settings, fh, indent=2)

print(f"Wired: {', '.join(added)}. Backup: {backup}")
print("Identity resolves on the NEXT session start, not this one.")
PY
