#!/bin/bash
# Create a consistent local snapshot, then copy it offsite with rclone.
# PT_BACKUP_RCLONE_DEST names the existing offsite destination.
# User-owned scheduled job; no database mediation service is required.

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
