#!/bin/bash
# One-shot #7231 offsite setup. Requires env REPO, USER_RCLONE_CONF, RCLONE_BIN.
# Example:
#   sudo env REPO="$PWD" USER_RCLONE_CONF="$HOME/.config/rclone/rclone.conf" \
#     RCLONE_BIN="$(command -v rclone)" bash scripts/dbmed-install/install-offsite.sh
set -euo pipefail

: "${REPO:?Set REPO to the project-tracker checkout}"
: "${USER_RCLONE_CONF:?Set USER_RCLONE_CONF to the user rclone.conf}"
: "${RCLONE_BIN:?Set RCLONE_BIN to the rclone binary path}"

DEST_CONF="${DEST_CONF:-/usr/local/etc/dbmed/rclone.conf}"
REGISTRY="${REGISTRY:-/usr/local/etc/dbmed/registry.d/project-tracker.toml}"
REMOTE_SECTION="${REMOTE_SECTION:-gbackup}"
DEST="${OFFSITE_DEST:-gbackup:db-backups/project-tracker}"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root via sudo env ..." >&2
  exit 1
fi

if [[ ! -f "$USER_RCLONE_CONF" ]]; then
  echo "Missing user rclone config: $USER_RCLONE_CONF" >&2
  exit 1
fi
if [[ ! -x "$RCLONE_BIN" ]]; then
  echo "rclone not executable at $RCLONE_BIN" >&2
  exit 1
fi
if [[ ! -d "$REPO" ]]; then
  echo "Missing repo: $REPO" >&2
  exit 1
fi

mkdir -p "$(dirname "$DEST_CONF")"

python3 - "$USER_RCLONE_CONF" "$DEST_CONF" "$REMOTE_SECTION" <<'PY'
import sys
from pathlib import Path
src, dest, section = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
text = src.read_text()
lines = text.splitlines(keepends=True)
out = []
in_section = False
header = f"[{section}]"
for line in lines:
    if line.startswith("["):
        in_section = line.strip() == header
        if in_section:
            out.append(line)
        continue
    if in_section:
        out.append(line)
if not out:
    raise SystemExit(f"section [{section}] not found in {src}")
dest.write_text("".join(out))
print(f"wrote {dest} ({len(out)} lines) from [{section}]")
PY

chown root:_dbmed "$DEST_CONF"
chmod 640 "$DEST_CONF"

if [[ ! -f "$REGISTRY" ]]; then
  echo "Missing registry: $REGISTRY" >&2
  exit 1
fi

python3 - "$REGISTRY" "$DEST" "$DEST_CONF" "$RCLONE_BIN" <<'PY'
from pathlib import Path
import sys
reg, dest, conf, bin_path = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
text = reg.read_text()
updates = {
    "offsite_rclone_dest": dest,
    "offsite_rclone_config": conf,
    "offsite_rclone_bin": bin_path,
}
lines = text.splitlines(keepends=True)
keys_seen = set()
new_lines = []
for line in lines:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        new_lines.append(line)
        continue
    key = stripped.split("=", 1)[0].strip()
    if key in updates:
        new_lines.append(f'{key} = "{updates[key]}"\n')
        keys_seen.add(key)
    else:
        new_lines.append(line)
for key, val in updates.items():
    if key not in keys_seen:
        new_lines.append(f'{key} = "{val}"\n')
reg.write_text("".join(new_lines))
print(f"updated {reg}")
PY

chown root:wheel "$REGISTRY"
chmod 644 "$REGISTRY"

cp "$REPO/scripts/db/dbmed_ops.py" /usr/local/libexec/dbmed/db/dbmed_ops.py
cp "$REPO/dbmed/registry.py" /usr/local/libexec/dbmed/dbmed/registry.py
chown root:_dbmed /usr/local/libexec/dbmed/db/dbmed_ops.py /usr/local/libexec/dbmed/dbmed/registry.py
chmod 644 /usr/local/libexec/dbmed/db/dbmed_ops.py /usr/local/libexec/dbmed/dbmed/registry.py

launchctl kickstart -k system/com.dbmed
echo "dbmed restarted. As your user (not root): pt backup offsite && pt backup status"
