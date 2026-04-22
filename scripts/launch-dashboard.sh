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

HOST="${PT_DASHBOARD_HOST:-127.0.0.1}"
PORT="${PT_DASHBOARD_PORT:-8000}"

exec doppler run -- \
  uv run --project "$PROJECT_DIR" \
  uvicorn dashboard.app:app --host "$HOST" --port "$PORT"
