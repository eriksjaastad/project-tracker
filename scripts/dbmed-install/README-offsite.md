# Offsite backup via dbmed (#7231)

Local snapshots already run inside `com.dbmed`. Off-machine copy must too,
because backup files live under `_dbmed` mode `0700` and cannot be read by
an agent-owned LaunchAgent/`rclone` process.

## One-time setup (human + sudo)

From the project-tracker repo root:

```bash
sudo env \
  REPO="$PWD" \
  USER_RCLONE_CONF="$HOME/.config/rclone/rclone.conf" \
  RCLONE_BIN="$(command -v rclone)" \
  OFFSITE_DEST="gbackup:project-tracker/db-backups" \
  bash scripts/dbmed-install/install-offsite.sh
```

Then as yourself (not root):

```bash
pt backup offsite
pt backup status
```

The installer:

1. Writes a root-owned rclone config with **only** the `gbackup` remote section
2. Adds `offsite_rclone_dest`, `offsite_rclone_config`, and `offsite_rclone_bin`
   to the project-tracker registry entry
3. Copies updated `dbmed_ops.py` + `registry.py` into the installed libexec tree
4. Kickstarts `com.dbmed`

`scripts/backup-db.sh` (LaunchAgent) calls `pt backup create` then
`pt backup offsite`. Offsite failures are logged but do not fail the local backup.

Override `OFFSITE_DEST` if you want another remote/path. Override `REMOTE_SECTION`
(default `gbackup`) if the rclone remote name differs.
