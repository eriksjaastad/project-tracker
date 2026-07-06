#!/usr/bin/env bash
# Run the portfolio alert digest via Doppler so RESEND_API_KEY is injected.
# Used by the launchd plist: com.eriksjaastad.alert-digest (fires 7:00 AM local).
#
# Secrets live in the synth-insight-labs project (prd config), NOT project-tracker's
# own doppler.yaml — hence the explicit --project/--config here.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# launchd has a minimal PATH — put brew (doppler) and the venv on it.
BREW_PREFIX="$(brew --prefix 2>/dev/null || echo /opt/homebrew)"
export PATH="$HOME/.local/bin:$BREW_PREFIX/bin:$PATH"

exec doppler run --project synth-insight-labs --config prd -- \
  "$PROJECT_DIR/venv/bin/python3" "$SCRIPT_DIR/alert_digest.py" "$@"
