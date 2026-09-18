#!/bin/bash
#
# dbmed rollback — puts the database back in the repo and stops the daemon.
#
#     sudo ./scripts/dbmed-install/rollback.sh
#
# This is the "the boundary is in the way and I need to work right now" escape
# hatch, and it is Erik's, not an agent's. It moves the data back to where the
# pre-dbmed code expects it and unloads the daemon. It does not delete
# anything: the install tree, the registry and the service account all stay,
# so `install.sh` can put everything back.
#
# Running this removes the boundary. After it, any process on the machine can
# read and write tracker.db again. That is the point of it — but say so out
# loud rather than letting it be a quiet side effect.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

SERVICE_USER="_dbmed"
DATA_ROOT="/usr/local/var/dbmed"
PROJECT="project-tracker"
PROJECT_DATA="${DATA_ROOT}/${PROJECT}"
PLIST="/Library/LaunchDaemons/com.dbmed.plist"

say()  { printf '\033[0;34m==>\033[0m %s\n' "$1"; }
ok()   { printf '\033[0;32m  ✓\033[0m %s\n' "$1"; }
warn() { printf '\033[0;33m  !\033[0m %s\n' "$1"; }
die()  { printf '\033[0;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "must run as root: sudo $0"
REAL_USER="${SUDO_USER:-}"
[ -n "$REAL_USER" ] || die "run via sudo so ownership can be handed back"
REAL_GROUP="$(id -gn "$REAL_USER")"
REAL_HOME="$(dscl . -read "/Users/${REAL_USER}" NFSHomeDirectory | awk '{print $2}')"

printf '\033[0;33m'
printf 'This removes the database boundary. After it runs, every process on\n'
printf 'this machine — including any agent — can read and write tracker.db\n'
printf 'directly again.\n'
printf '\033[0m'
read -r -p "Type 'remove the boundary' to continue: " CONFIRM
[ "$CONFIRM" = "remove the boundary" ] || die "cancelled"

# --------------------------------------------------------------------------
say "1. Stopping the daemon"

launchctl bootout system/com.dbmed 2>/dev/null || warn "daemon was not loaded"
if [ -f "$PLIST" ]; then
  # Disabled by renaming, not deleting, so `install.sh` can compare against it.
  mv "$PLIST" "${PLIST}.disabled-$(date +%Y%m%dT%H%M%S)"
  ok "LaunchDaemon plist moved aside"
fi

# --------------------------------------------------------------------------
say "2. Moving data back into the repo"

install -d -o "$REAL_USER" -g "$REAL_GROUP" -m 0755 \
  "$REPO_DIR/data" "$REPO_DIR/data/backups" "${REAL_HOME}/.project-tracker/backups"

move_out() {
  local src="$1" dest="$2"
  [ -e "$src" ] || return 0
  if [ -e "$dest" ]; then
    warn "$(basename "$dest") already exists in the repo; leaving the protected copy at ${src}"
    return 0
  fi
  mv "$src" "$dest"
  chown "$REAL_USER:$REAL_GROUP" "$dest"
  chmod 0644 "$dest"
  ok "restored $(basename "$dest")"
}

move_out "$PROJECT_DATA/tracker.db"     "$REPO_DIR/data/tracker.db"
move_out "$PROJECT_DATA/tracker.db-wal" "$REPO_DIR/data/tracker.db-wal"
move_out "$PROJECT_DATA/tracker.db-shm" "$REPO_DIR/data/tracker.db-shm"

move_tree_out() {
  local src="$1" dest="$2" label="$3"
  [ -d "$src" ] || return 0
  local moved=0
  for item in "$src"/*; do
    [ -e "$item" ] || continue
    local base; base="$(basename "$item")"
    [ -e "${dest}/${base}" ] && continue
    mv "$item" "${dest}/${base}"
    moved=$((moved + 1))
  done
  chown -R "$REAL_USER:$REAL_GROUP" "$dest"
  ok "restored ${moved} file(s) to ${label}"
}

move_tree_out "$PROJECT_DATA/backups" "$REPO_DIR/data/backups" "data/backups"
move_tree_out "${DATA_ROOT}/external/${PROJECT}" \
              "${REAL_HOME}/.project-tracker/backups" "~/.project-tracker/backups"
move_tree_out "$PROJECT_DATA/attic" "$REPO_DIR/data" "data/ (stale copies)"

printf '\n\033[0;33mThe boundary is removed.\033[0m\n\n'
printf 'The code still expects it: scripts/db/manager.py is the dbmed client,\n'
printf 'so `pt` will now report the service as unavailable rather than opening\n'
printf 'the file. That is the fail-closed behaviour working as designed.\n\n'
printf 'To get a working `pt` back, either:\n'
printf '  - re-run  sudo %s/scripts/dbmed-install/install.sh\n' "$REPO_DIR"
printf '  - or check out a commit from before the dbmed branch landed.\n\n'
printf 'Nothing was deleted. The install tree, registry and %s account remain.\n\n' "$SERVICE_USER"
