#!/bin/bash
#
# dbmed installer — creates the database boundary. RUN BY A HUMAN, WITH sudo.
#
#     sudo ./scripts/dbmed-install/install.sh
#
# No agent can run this: `sudo` is denied in the agent runtimes, and that
# denial is load-bearing. If an agent could run this script it could also
# uninstall the boundary, and there would be no boundary.
#
# What it does, in order:
#
#   1. Creates the `_dbmed` service account, which will own the data.
#   2. Creates the install, config and data trees with root ownership.
#   3. Copies the backend code and vendors cr-sqlite root-owned.
#   4. Writes the registry entry for project-tracker.
#   5. MOVES the live database and every real-data copy behind the boundary.
#   6. Installs and starts the LaunchDaemon.
#
# Step 5 is the only irreversible-feeling one, and it is a move, not a copy
# followed by a delete — the bytes are never duplicated and never removed.
# `rollback.sh` moves them back.
#
# Nothing here deletes anything outside /tmp. A previous install tree is
# archived with a timestamp rather than removed, so a bad deploy can be
# inspected afterwards instead of being gone.
#
# Re-running is safe. Every step checks for its own result first.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

SERVICE_USER="_dbmed"
SERVICE_GROUP="_dbmed"
CLIENT_GROUP="staff"

INSTALL_DIR="/usr/local/libexec/dbmed"
CONFIG_DIR="/usr/local/etc/dbmed"
DATA_ROOT="/usr/local/var/dbmed"
RUN_DIR="/usr/local/var/run"
SOCKET="${RUN_DIR}/dbmed.sock"
PLIST="/Library/LaunchDaemons/com.dbmed.plist"

PROJECT="project-tracker"
PROJECT_DATA="${DATA_ROOT}/${PROJECT}"

STAMP="$(date +%Y%m%dT%H%M%S)"

say()  { printf '\033[0;34m==>\033[0m %s\n' "$1"; }
ok()   { printf '\033[0;32m  ✓\033[0m %s\n' "$1"; }
warn() { printf '\033[0;33m  !\033[0m %s\n' "$1"; }
die()  { printf '\033[0;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "must run as root: sudo $0"
[ "$(uname -s)" = "Darwin" ] || die "this installer is macOS-only"

# The invoking human, not root — they need to be able to talk to the socket.
REAL_USER="${SUDO_USER:-}"
[ -n "$REAL_USER" ] || die "run via sudo so the installer knows which account to authorise"
REAL_HOME="$(dscl . -read "/Users/${REAL_USER}" NFSHomeDirectory | awk '{print $2}')"
CRSQLITE_SOURCE="${CRSQLITE_SOURCE:-${REAL_HOME}/.local/lib/crsqlite/crsqlite.dylib}"

# --------------------------------------------------------------------------
say "1. Service account"

if dscl . -read "/Users/${SERVICE_USER}" >/dev/null 2>&1; then
  ok "${SERVICE_USER} already exists"
else
  # Pick a free uid/gid below 500 so macOS hides the account from the login
  # window. Scanning for a gap beats hardcoding a number that may be taken.
  NEW_ID=$(dscl . -list /Users UniqueID | awk '$2 < 500 {print $2}' | sort -n | awk '
    BEGIN { candidate = 300 }
    { if ($1 == candidate) candidate++ }
    END { print candidate }')
  [ "$NEW_ID" -lt 500 ] || die "no free system uid below 500"

  dscl . -create "/Groups/${SERVICE_GROUP}"
  dscl . -create "/Groups/${SERVICE_GROUP}" PrimaryGroupID "$NEW_ID"
  dscl . -create "/Groups/${SERVICE_GROUP}" RealName "dbmed database service"

  dscl . -create "/Users/${SERVICE_USER}"
  dscl . -create "/Users/${SERVICE_USER}" UniqueID "$NEW_ID"
  dscl . -create "/Users/${SERVICE_USER}" PrimaryGroupID "$NEW_ID"
  dscl . -create "/Users/${SERVICE_USER}" RealName "dbmed database service"
  # No login shell and no home directory: this account exists to own files and
  # run one daemon. Nothing should ever log in as it.
  dscl . -create "/Users/${SERVICE_USER}" UserShell /usr/bin/false
  dscl . -create "/Users/${SERVICE_USER}" NFSHomeDirectory /var/empty
  dscl . -create "/Users/${SERVICE_USER}" IsHidden 1
  ok "created ${SERVICE_USER} (uid ${NEW_ID})"
fi

# --------------------------------------------------------------------------
say "2. Directory tree"

install -d -o root -g wheel -m 0755 \
  "$CONFIG_DIR" "$CONFIG_DIR/registry.d" "$DATA_ROOT" "$RUN_DIR"
ok "root-owned: ${CONFIG_DIR}, ${DATA_ROOT}"

# 0700 on the project data dir is the boundary. An agent running as the
# invoking user cannot traverse this directory, so it cannot open, stat, copy,
# rename or delete anything inside it — no matter which tool it reaches for.
install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0700 \
  "$PROJECT_DATA" "$PROJECT_DATA/backups" "$PROJECT_DATA/attic" \
  "$PROJECT_DATA/fixtures" "${DATA_ROOT}/external/${PROJECT}"
install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0750 "${DATA_ROOT}/audit"
ok "service-owned at 0700: ${PROJECT_DATA}"

# --------------------------------------------------------------------------
say "3. Backend code"

# Staged in /tmp, then moved into place, so a half-copied tree is never what
# the daemon loads. /tmp is on the same volume as /usr/local, so the move is a
# rename rather than a copy.
STAGING="$(mktemp -d /tmp/dbmed-install.XXXXXX)"
trap 'rm -rf "$STAGING"' EXIT

mkdir -p "$STAGING/dbmed" "$STAGING/scripts/utils" "$STAGING/lib"
cp "$REPO_DIR"/dbmed/*.py         "$STAGING/dbmed/"
cp "$REPO_DIR"/scripts/utils/*.py "$STAGING/scripts/utils/"
cp "$REPO_DIR"/scripts/config.py "$REPO_DIR"/scripts/logger.py "$STAGING/scripts/"
touch "$STAGING/scripts/__init__.py"

# The backend db package, assembled file by file rather than copied wholesale.
#
# `scripts/db/manager.py` in the repo is the CLIENT shim, and it must never
# reach the daemon's import path — an RPC proxy there would make the daemon
# call itself. Copying the directory and deleting the shim afterwards would
# also work, but one missed delete is a very quiet failure. Naming the files
# means it cannot happen.
#
# Every other module keeps its repo filename, so the installed tree and the
# repo are the same layout. The test suite therefore exercises the same import
# graph the daemon runs, which is the only way its evidence means anything.
stage_db_package() {
  local dest="$1"
  mkdir -p "$dest"
  for module in __init__ backend_manager backend_restore_db schema pt_id \
                calendar_manager crr_manifest migration_runner sync_state \
                sync_checks sync_http sync_daemon dbmed_ops; do
    cp "$REPO_DIR/scripts/db/${module}.py" "$dest/${module}.py"
  done
  cp -R "$REPO_DIR/scripts/db/migrations" "$dest/migrations"
}

# Importable both as `db.*` (what the backend modules use) and as
# `scripts.db.*` (what a couple of call sites use).
stage_db_package "$STAGING/db"
stage_db_package "$STAGING/scripts/db"

if [ -f "$CRSQLITE_SOURCE" ]; then
  cp "$CRSQLITE_SOURCE" "$STAGING/lib/crsqlite.dylib"
  ok "vendored cr-sqlite from ${CRSQLITE_SOURCE}"
else
  warn "cr-sqlite not found at ${CRSQLITE_SOURCE}"
  warn "migrations that bracket CRR tables will refuse to run until it is vendored"
fi

chown -R root:wheel "$STAGING"
find "$STAGING" -type d -exec chmod 0755 {} +
find "$STAGING" -type f -exec chmod 0644 {} +

mkdir -p "$INSTALL_DIR"
chown root:wheel "$INSTALL_DIR"
chmod 0755 "$INSTALL_DIR"

# Swap. The previous tree is archived, not removed: if a deploy turns out to
# be bad, the thing that was working is still on disk to compare against.
if [ -d "$INSTALL_DIR" ] && [ "$(ls -A "$INSTALL_DIR")" ]; then
  ARCHIVE="${DATA_ROOT}/attic/install-${STAMP}"
  install -d -o root -g wheel -m 0700 "${DATA_ROOT}/attic"
  mv "$INSTALL_DIR"/* "$ARCHIVE"
  ok "archived the previous install at ${ARCHIVE}"
fi
mv "$STAGING"/* "$INSTALL_DIR"
trap - EXIT
chown root:wheel "$INSTALL_DIR"
chmod 0755 "$INSTALL_DIR"
ok "installed root-owned backend at ${INSTALL_DIR}"

# --------------------------------------------------------------------------
say "4. Registry"

cat > "${CONFIG_DIR}/registry.d/${PROJECT}.toml" <<REGEOF
# dbmed registry entry. Root-owned: the daemon refuses to parse this file if
# it is writable by anyone else, because whoever can edit it chooses which
# database each project talks to.
project = "${PROJECT}"
db_path = "${PROJECT_DATA}/tracker.db"
data_root = "${DATA_ROOT}"
backup_dir = "${PROJECT_DATA}/backups"
external_backup_dir = "${DATA_ROOT}/external/${PROJECT}"
fixture_root = "${PROJECT_DATA}/fixtures"
ops_module = "db.dbmed_ops"
# The vendored, root-owned copy. A SQLite extension is native code inside the
# daemon, so this must never point anywhere an agent can write.
crsqlite_path = "${INSTALL_DIR}/lib/crsqlite.dylib"
allowed_users = ["${REAL_USER}"]
REGEOF
chown root:wheel "${CONFIG_DIR}/registry.d/${PROJECT}.toml"
chmod 0644 "${CONFIG_DIR}/registry.d/${PROJECT}.toml"
ok "registered ${PROJECT} for user ${REAL_USER}"

# --------------------------------------------------------------------------
say "5. Moving data behind the boundary"

move_in() {
  local src="$1" dest="$2"
  [ -e "$src" ] || return 0
  if [ -e "$dest" ]; then
    warn "$(basename "$src") is already behind the boundary; leaving ${src} in place for you to review"
    return 0
  fi
  mv "$src" "$dest"
  chown "$SERVICE_USER:$SERVICE_GROUP" "$dest"
  chmod 0600 "$dest"
  ok "moved $(basename "$src")"
}

# The live database and its journals. The -wal in particular holds committed
# transactions that are not yet in the main file, so moving the database
# without it would lose data.
move_in "$REPO_DIR/data/tracker.db"     "$PROJECT_DATA/tracker.db"
move_in "$REPO_DIR/data/tracker.db-wal" "$PROJECT_DATA/tracker.db-wal"
move_in "$REPO_DIR/data/tracker.db-shm" "$PROJECT_DATA/tracker.db-shm"

# Stale full copies. Real rows, so they are protected, never deleted.
for stray in "$REPO_DIR"/data/tracker_pre_router_migration.db* \
             "$REPO_DIR"/data/tracker.db.empty_backup_*; do
  [ -e "$stray" ] && move_in "$stray" "$PROJECT_DATA/attic/$(basename "$stray")"
done

move_tree() {
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
  chown -R "$SERVICE_USER:$SERVICE_GROUP" "$dest"
  chmod -R go-rwx "$dest"
  ok "moved ${moved} file(s) from ${label}"
}

# data/backups holds full .db snapshots and JSON dumps of task rows. Both are
# real data: an agent that can read a JSON dump of the tasks table has read
# the tasks table.
move_tree "$REPO_DIR/data/backups" "$PROJECT_DATA/backups" "data/backups"

# The second backup location DECISIONS.md requires. It lived in the user's
# home, where an agent could read it or delete it.
move_tree "${REAL_HOME}/.project-tracker/backups" \
          "${DATA_ROOT}/external/${PROJECT}" "~/.project-tracker/backups"

# --------------------------------------------------------------------------
say "6. LaunchDaemon"

PYTHON_BIN="${DBMED_PYTHON:-$(command -v python3.13 || command -v python3)}"
[ -x "$PYTHON_BIN" ] || die "no python3 found; set DBMED_PYTHON to an interpreter path"

cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.dbmed</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_BIN}</string>
        <string>-m</string>
        <string>dbmed.daemon</string>
        <string>--socket</string><string>${SOCKET}</string>
        <string>--config-dir</string><string>${CONFIG_DIR}</string>
        <string>--install-dir</string><string>${INSTALL_DIR}</string>
        <string>--data-root</string><string>${DATA_ROOT}</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${INSTALL_DIR}</string>

    <!-- The daemon runs as the service account, never as root. It needs to
         read the data it owns, and nothing more. -->
    <key>UserName</key>
    <string>${SERVICE_USER}</string>
    <key>GroupName</key>
    <string>${SERVICE_GROUP}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>${INSTALL_DIR}:${INSTALL_DIR}/scripts</string>
        <!-- scripts/config.py resolves these at import into module constants
             that would otherwise point inside the install tree. Setting them
             here means root chooses them, not a caller's environment. The
             non-canonical-path warning config.py prints on startup is
             expected and correct: the canonical path is no longer where the
             database lives. -->
        <key>PT_DB_PATH</key>
        <string>${PROJECT_DATA}/tracker.db</string>
        <key>PT_EXTERNAL_BACKUP_DIR</key>
        <string>${DATA_ROOT}/external/${PROJECT}</string>
        <!-- SAFE_MODE used to be read from the agent's own shell. It is the
             daemon's now, which is the whole point: exporting SAFE_MODE=0 in
             a terminal no longer unlocks deletes. -->
        <key>SAFE_MODE</key>
        <string>1</string>
        <key>PYTHONDONTWRITEBYTECODE</key>
        <string>1</string>
    </dict>

    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>

    <key>StandardOutPath</key>
    <string>${DATA_ROOT}/audit/dbmedd.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${DATA_ROOT}/audit/dbmedd.stderr.log</string>
</dict>
</plist>
PLISTEOF
chown root:wheel "$PLIST"
chmod 0644 "$PLIST"
ok "wrote ${PLIST}"

launchctl bootout system/com.dbmed 2>/dev/null || true
launchctl bootstrap system "$PLIST"
ok "daemon bootstrapped"

# The socket is created by the daemon; wait for it rather than racing.
for _ in $(seq 1 40); do
  [ -S "$SOCKET" ] && break
  sleep 0.25
done
[ -S "$SOCKET" ] || die "daemon did not create ${SOCKET}; see ${DATA_ROOT}/audit/dbmedd.stderr.log"

chgrp "$CLIENT_GROUP" "$SOCKET"
chmod 0660 "$SOCKET"
ok "socket ready at ${SOCKET}"

printf '\n\033[0;32mInstalled.\033[0m Verify with:\n\n'
printf '    cd %s && ./pt tasks | head\n' "$REPO_DIR"
printf '    ls -ld %s     # expect drwx------  %s\n' "$PROJECT_DATA" "$SERVICE_USER"
printf '    sudo -u %s cat %s/tracker.db   # expect Permission denied\n\n' "$REAL_USER" "$PROJECT_DATA"
printf 'Then run the boundary evidence suite:\n\n'
printf '    cd %s && uv run pytest tests/boundary/ -v\n\n' "$REPO_DIR"
