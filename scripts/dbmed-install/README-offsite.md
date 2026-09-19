# Offsite backup via dbmed (#7231)

Local snapshots already run inside `com.dbmed`. Off-machine copy must too,
because backup files live under `_dbmed` mode `0700` and cannot be read by
an agent-owned LaunchAgent/`rclone` process.

## One-time setup (human + sudo)

1. Create a root-owned rclone config that contains **only** the offsite remote
   (do not copy your full personal `~/.config/rclone/rclone.conf`):

```bash
sudo mkdir -p /usr/local/etc/dbmed
# Example: extract the [gbackup] section into this file, then:
sudo chown root:_dbmed /usr/local/etc/dbmed/rclone.conf
sudo chmod 640 /usr/local/etc/dbmed/rclone.conf
```

2. Add registry fields to `/usr/local/etc/dbmed/registry.d/project-tracker.toml`:

```toml
offsite_rclone_dest = "gbackup:project-tracker/db-backups"
offsite_rclone_config = "/usr/local/etc/dbmed/rclone.conf"
```

3. Redeploy daemon code if needed, then restart:

```bash
sudo launchctl kickstart -k system/com.dbmed
pt backup offsite
```

`scripts/backup-db.sh` (LaunchAgent) calls `pt backup create` then
`pt backup offsite`. Offsite failures are logged but do not fail the local backup.
