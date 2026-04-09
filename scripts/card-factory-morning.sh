#!/usr/bin/env bash
#
# card-factory-morning.sh — Daily Card Factory run on MacBook startup
#
# Called by launchd (RunAtLoad). Checks a daily lock to avoid re-running
# on every wake/unlock throughout the day. Outputs go to logs/ for review.
#
# Install:
#   launchctl load ~/Library/LaunchAgents/com.eriksjaastad.card-factory.plist
#
# Uninstall:
#   launchctl unload ~/Library/LaunchAgents/com.eriksjaastad.card-factory.plist
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOCK_FILE="$PROJECT_ROOT/logs/.card-factory-last-run"
TODAY=$(date +%Y-%m-%d)

# ── Daily lock: only run once per calendar day ──
if [[ -f "$LOCK_FILE" ]] && [[ "$(cat "$LOCK_FILE")" == "$TODAY" ]]; then
    echo "$(date -Iseconds) Card Factory already ran today ($TODAY). Skipping."
    exit 0
fi

echo "$(date -Iseconds) Starting Card Factory morning scan..."

# ── Ensure PATH includes claude and uv ──
# shellcheck disable=SC2155
BREW_PREFIX="$(brew --prefix 2>/dev/null || echo /opt/homebrew)"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$BREW_PREFIX/bin:$PATH"

# ── Verify claude is available ──
if ! command -v claude &>/dev/null; then
    echo "ERROR: claude CLI not found in PATH" >&2
    exit 1
fi

# ── Run Card Factory across all projects ──
"$SCRIPT_DIR/card-factory.sh" --all

# ── Write lock file on success ──
echo "$TODAY" > "$LOCK_FILE"
echo "$(date -Iseconds) Card Factory morning scan complete."
