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

# The ~/projects rules repo (projects_root()) has no git remote, so it goes to
# the same destination as projects.bundle, a `git bundle --all` overwritten each
# run. Restore: `git clone projects.bundle <dir>`. Logged as one rules_copy line;
# a failure here never touches the local DB backup.
if RULES_OUT="$({
  BUNDLE_DIR="$(mktemp -d)" && trap 'rm -rf "$BUNDLE_DIR"' EXIT &&
  SETTINGS="$("$HOME/.local/bin/uv" run --no-project python -c '
from scripts.backup_config import rclone_config_path, rclone_destination
from scripts.config import projects_root
print(rclone_destination(), rclone_config_path(), projects_root(), sep="\n")')" &&
  { read -r DEST; read -r CONFIG; read -r RULES_REPO; } <<<"$SETTINGS" &&
  { [ -n "$DEST" ] || { echo "Set PT_BACKUP_RCLONE_DEST"; false; }; } &&
  git -C "$RULES_REPO" bundle create -q "$BUNDLE_DIR/projects.bundle" --all &&
  rclone copyto "$BUNDLE_DIR/projects.bundle" "${DEST%/}/projects.bundle" \
    --config "$CONFIG" --checksum --retries 3 &&
  echo "projects.bundle -> ${DEST%/}/projects.bundle"
} 2>&1)"; then
  echo "$(date -Iseconds) | rules_copy | ok | ${RULES_OUT//[$'\r\n']/ }"
else
  echo "$(date -Iseconds) | rules_copy | failed | ${RULES_OUT//[$'\r\n']/ }"
fi

# Retention last, logged the same way; a failure leaves the files in place.
if PRUNE_OUT="$(./pt backup prune 2>&1)"; then
  echo "$(date -Iseconds) | prune | ok | ${PRUNE_OUT}"
else
  echo "$(date -Iseconds) | prune | failed | ${PRUNE_OUT}"
fi
