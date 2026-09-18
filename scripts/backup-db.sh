#!/bin/bash
# Point-in-time backup of tracker.db, via the dbmed database service.
#
# Usage: ./scripts/backup-db.sh
# Cron:  Called by the com.eriksjaastad.pt-backup launchd plist
#
# This used to shell out to the `sqlite3` binary directly:
#
#     sqlite3 "$DB" ".backup '$BACKUP_FILE'"
#
# Two problems with that. It opened the database from a script an agent can
# edit, which is exactly the access the boundary exists to remove. And it built
# the dot-command by interpolating an environment-controlled path into a
# single-quoted string, so a path containing a quote broke out of the command.
#
# The snapshot, its verification, the second copy and the retention sweep all
# happen inside the service now. PT_BACKUP_DB_PATH and PT_FULL_BACKUP_DIR are
# gone with them: the paths come from the root-owned registry, because a
# backup job that can be pointed somewhere else by an environment variable is
# a backup job an agent can redirect.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RCLONE_DEST="${PT_BACKUP_RCLONE_DEST:-}"

cd "$REPO_DIR"

# `pt backup create` exits non-zero if the snapshot fails verification, so
# `set -e` is doing real work here — a failed backup must not be logged as a
# success.
OUTPUT="$(./pt backup create)"
echo "$(date -Iseconds) | backup | ${OUTPUT}"

# Optional: copy one successful snapshot off-machine once per day.
# Best-effort, and it must never suppress the local backup success above.
if [ -n "$RCLONE_DEST" ]; then
  echo "$(date -Iseconds) | cloud_copy | skipped | offsite copy is not yet a dbmed operation (card filed)"
fi
