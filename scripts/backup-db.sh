#!/bin/bash
# Point-in-time backup of tracker.db using SQLite's atomic .backup command.
# Safe during concurrent writes (WAL mode). Zero dependencies beyond sqlite3.
#
# Usage: ./scripts/backup-db.sh
# Cron:  Called by com.eriksjaastad.pt-backup launchd plist

set -euo pipefail

DB="${PT_BACKUP_DB_PATH:-$HOME/projects/project-tracker/data/tracker.db}"
BACKUP_DIR="${PT_FULL_BACKUP_DIR:-$HOME/.project-tracker/backups}"
RCLONE_DEST="${PT_BACKUP_RCLONE_DEST:-}"
RETENTION_DAYS=30

# Bail if DB doesn't exist
if [ ! -f "$DB" ]; then
  echo "ERROR: Database not found at $DB" >&2
  exit 1
fi

# Ensure backup dir exists
mkdir -p "$BACKUP_DIR"

# Create timestamped backup using SQLite's atomic .backup
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/tracker_${TIMESTAMP}.db"

sqlite3 "$DB" ".backup '$BACKUP_FILE'"

# Verify the backup is non-empty
BACKUP_SIZE=$(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat -c%s "$BACKUP_FILE" 2>/dev/null)
if [ "$BACKUP_SIZE" -lt 1024 ]; then
  echo "ERROR: Backup suspiciously small (${BACKUP_SIZE} bytes)" >&2
  exit 1
fi

# Rotate: delete backups older than RETENTION_DAYS
find "$BACKUP_DIR" -name "tracker_*.db" -mtime +"$RETENTION_DAYS" -delete 2>/dev/null || true

# Log success (one line, parseable)
echo "$(date -Iseconds) | backup | ${BACKUP_SIZE} bytes | ${BACKUP_FILE}"

# Optional: copy one successful full backup off-machine once per day.
# This is best-effort and must never suppress the local backup success.
if [ -n "$RCLONE_DEST" ]; then
  CLOUD_STATE_FILE="${PT_BACKUP_CLOUD_STATE_FILE:-$BACKUP_DIR/.cloud-copy-last-success}"
  TODAY="$(date +%F)"
  LAST_CLOUD_DAY=""
  if [ -f "$CLOUD_STATE_FILE" ]; then
    LAST_CLOUD_DAY="$(cat "$CLOUD_STATE_FILE" 2>/dev/null || true)"
  fi

  if [ "$LAST_CLOUD_DAY" != "$TODAY" ]; then
    REMOTE_FILE="${RCLONE_DEST%/}/tracker_daily_$(date +%Y%m%d).db"
    if ! command -v rclone >/dev/null 2>&1; then
      echo "$(date -Iseconds) | cloud_copy | failure | ${REMOTE_FILE} | rclone_not_found"
    elif rclone copyto "$BACKUP_FILE" "$REMOTE_FILE"; then
      printf '%s' "$TODAY" > "$CLOUD_STATE_FILE" || true
      echo "$(date -Iseconds) | cloud_copy | success | ${REMOTE_FILE}"
    else
      CLOUD_EXIT=$?
      echo "$(date -Iseconds) | cloud_copy | failure | ${REMOTE_FILE} | exit=${CLOUD_EXIT}"
    fi
  fi
fi
