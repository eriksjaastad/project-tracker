#!/usr/bin/env bash
# Launch dashboard via Doppler so all secrets are injected at runtime.
# Used by the launchd plist: com.eriksjaastad.project-tracker
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

exec "$(brew --prefix)/bin/doppler" run -- \
  "$PROJECT_DIR/venv/bin/python" \
  -m uvicorn dashboard.app:app --host 0.0.0.0 --port 8000
