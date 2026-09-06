#!/usr/bin/env bash
# Launch dashboard via Doppler so all secrets are injected at runtime.
# Used by the launchd plist: com.eriksjaastad.project-tracker
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# ── Log rotation for the launchd-owned stdout/stderr files (#6750) ──
# uvicorn and launchd write these two files through an inherited fd, bypassing
# Python logging entirely — RotatingFileHandler in scripts/logger.py cannot
# touch them, and nothing else in the repo caps them. They had reached 23MB and
# 10MB with no rotation anywhere. With launchd KeepAlive on, a crash loop
# restarts this script constantly, so a startup check fires in exactly the
# failure case that grows them fastest.
#
# Copy-truncate, not rename: launchd opens these files and hands the fd to this
# script before it runs. Renaming leaves the fd pointing at the renamed inode,
# so the "current" log would sit empty while the backup kept growing.
# Truncating in place keeps the inode the open fd refers to.
LOG_DIR="${PT_DASHBOARD_LOG_DIR:-$PROJECT_DIR/logs}"
LOG_MAX_BYTES="${PT_DASHBOARD_LOG_MAX_BYTES:-10485760}"   # 10MB
LOG_BACKUPS="${PT_DASHBOARD_LOG_BACKUPS:-2}"              # -> ~30MB per stream

file_size() {
  stat -f%z "$1" 2>/dev/null || stat -c%s "$1" 2>/dev/null || echo 0
}

rotate_if_large() {
  local target="$1"
  local size i prev

  if [ ! -f "$target" ]; then
    return 0
  fi

  size="$(file_size "$target")"
  if [ "$size" -le "$LOG_MAX_BYTES" ]; then
    return 0
  fi

  # Shift existing backups down: .1 -> .2 -> ... -> .$LOG_BACKUPS (oldest drops).
  i="$LOG_BACKUPS"
  while [ "$i" -gt 1 ]; do
    prev=$((i - 1))
    if [ -f "$target.$prev" ]; then
      mv -f "$target.$prev" "$target.$i"
    fi
    i="$prev"
  done

  if [ "$LOG_BACKUPS" -ge 1 ]; then
    cp "$target" "$target.1"
  fi
  : > "$target"

  echo "rotated $target ($size bytes > $LOG_MAX_BYTES)" >&2
}

rotate_dashboard_logs() {
  rotate_if_large "$LOG_DIR/dashboard.stderr.log"
  rotate_if_large "$LOG_DIR/dashboard.stdout.log"
}

# Sourced (tests exercise rotate_dashboard_logs directly) — define and stop.
if [ "${BASH_SOURCE[0]}" != "${0}" ]; then
  return 0
fi

rotate_dashboard_logs

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
