#!/usr/bin/env bash
#
# Dashboard health watchdog. Restarts the project-tracker dashboard if its
# /api/alerts endpoint is unhealthy.
#
# Why this exists: launchd KeepAlive only restarts a process that has DIED. The
# dashboard has twice (2026-07-06, 2026-07-08) gone "alive but broken" — the
# process stays up but its SQLite connection rots and every request 500s with
# "unable to open database file" (suspected tracker.db handle leak; see the
# root-cause card). KeepAlive can't see that; this watchdog can. When the
# dashboard is down, the 7am alert digest degrades — this keeps it healthy.
#
# Installed as com.eriksjaastad.dashboard-watchdog (StartInterval 300s).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG="$PROJECT_DIR/logs/dashboard_watchdog.log"

URL="${PT_DASHBOARD_URL:-http://localhost:8000/api/alerts}"
LABEL="com.eriksjaastad.project-tracker"

ts() { date '+%Y-%m-%dT%H:%M:%S'; }

# Three tries, 5s apart, before declaring the dashboard unhealthy — avoids
# restarting over a single transient blip (e.g. a slow GC pause).
code=000
for attempt in 1 2 3; do
  # curl -w always prints a status (000 on connect failure); guard only the
  # curl-missing case so the logged code stays a single clean value.
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$URL" 2>/dev/null)"
  [ -z "$code" ] && code=000
  if [ "$code" = "200" ]; then
    exit 0
  fi
  # Back off between attempts, but don't stall after the last one.
  [ "$attempt" -lt 3 ] && sleep 5
done

echo "$(ts) UNHEALTHY (last HTTP=$code) — restarting $LABEL" >> "$LOG"
if launchctl kickstart -k "gui/$(id -u)/$LABEL" >> "$LOG" 2>&1; then
  echo "$(ts) kickstart issued" >> "$LOG"
else
  echo "$(ts) kickstart FAILED (exit $?)" >> "$LOG"
fi
