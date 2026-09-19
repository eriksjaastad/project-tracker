#!/bin/bash
# Point-in-time backup of tracker.db, via the dbmed database service.
#
# Usage: ./scripts/backup-db.sh
# Cron:  Called by the com.eriksjaastad.pt-backup launchd plist
#
# Local snapshot + verification + retention happen inside dbmed.
# Off-machine copy is also a dbmed operation (#7231): the daemon reads the
# protected snapshot and runs rclone with a root-owned config/destination
# from the registry. PT_BACKUP_RCLONE_DEST is ignored on purpose — an agent
# must not be able to redirect offsite copies via the environment.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

OUTPUT="$(./pt backup create)"
echo "$(date -Iseconds) | backup | ${OUTPUT}"

# Best-effort offsite. Local success must not be undone by a cloud failure.
if OFFSITE_OUT="$(./pt backup offsite 2>&1)"; then
  echo "$(date -Iseconds) | cloud_copy | ok | ${OFFSITE_OUT}"
else
  echo "$(date -Iseconds) | cloud_copy | failed | ${OFFSITE_OUT}"
fi
