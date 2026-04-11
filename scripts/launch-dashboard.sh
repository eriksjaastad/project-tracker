#!/usr/bin/env bash
# Launch dashboard via Doppler so all secrets are injected at runtime.
# Used by the launchd plist: com.eriksjaastad.project-tracker
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# ── Ensure PATH includes brew and doppler (launchd has minimal PATH) ──
# shellcheck disable=SC2155
BREW_PREFIX="$(brew --prefix 2>/dev/null || echo /opt/homebrew)"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$BREW_PREFIX/bin:$PATH"

exec doppler run -- \
  "$PROJECT_DIR/venv/bin/python" \
  -m uvicorn dashboard.app:app --host 0.0.0.0 --port 8000
