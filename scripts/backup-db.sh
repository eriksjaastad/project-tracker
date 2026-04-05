#!/bin/bash
# Point-in-time backup of tracker.db using SQLite's atomic .backup command.
# Safe during concurrent writes (WAL mode). Zero dependencies beyond sqlite3.
#
# Usage: ./scripts/backup-db.sh
# Cron:  Called by com.eriksjaastad.pt-backup launchd plist

set -euo pipefail

DB="$HOME/projects/project-tracker/data/tracker.db"
BACKUP_DIR="$HOME/.project-tracker/backups"
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
