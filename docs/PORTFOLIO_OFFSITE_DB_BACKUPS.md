# Portfolio offsite database backups

**Convention (locked 2026-09-19):** every project's database snapshots go to

```text
gbackup:db-backups/<project-name>/
```

Same remote (`gbackup`), same folder tree, no per-project snowflake remotes or
`PT_BACKUP_RCLONE_DEST` hacks. Agents never run rclone against live DB files;
copies run inside **dbmed** (or that project's sanctioned DB tool once it owns
the file).

Reference implementation: project-tracker `#7231`
(`scripts/dbmed-install/README-offsite.md`, `install-offsite.sh`).

## Who this is for

Any project with a real SQLite (or similar) database that matters if it is lost.
If the project is not yet behind dbmed / a project-owned DB tool, do that first
(portfolio security cards under `#7217`), then come back here.

## Prerequisites

1. Live DB is owned by dbmed (or equivalent), not world-writable in the repo.
2. Local snapshots already work through the project tool (e.g. `pt backup create`).
3. Human has rclone remote `gbackup` working in `~/.config/rclone/rclone.conf`.

## One-time setup (human + sudo)

From the project that ships dbmed (today: project-tracker), reuse the shared
installer pattern:

```bash
# From the project-tracker checkout (ships the shared installer today):
cd "$PROJECTS_ROOT/project-tracker"   # or your local clone path
sudo env \
  REPO="$PWD" \
  USER_RCLONE_CONF="$HOME/.config/rclone/rclone.conf" \
  RCLONE_BIN="$(command -v rclone)" \
  OFFSITE_DEST="gbackup:db-backups/<project-name>" \
  bash scripts/dbmed-install/install-offsite.sh
```

For a **new** project's registry entry, set at least:

```toml
offsite_rclone_dest = "gbackup:db-backups/<project-name>"
offsite_rclone_config = "/usr/local/etc/dbmed/rclone.conf"
# com.dbmed has no PATH — set offsite_rclone_bin to `command -v rclone` on that machine
offsite_rclone_bin = "<absolute path from: command -v rclone>"
```

The root-owned rclone config under `/usr/local/etc/dbmed/rclone.conf` should
contain **only** the `gbackup` remote (not a full personal rclone.conf).

## Smoke test

```bash
# project tool — names vary; project-tracker example:
pt backup create
pt backup offsite
pt backup status
```

Expect a file under `gbackup:db-backups/<project-name>/` and status that records
a successful off-machine copy. Wire the project's LaunchAgent/cron to create
then offsite (offsite failure must not undo a good local snapshot).

## Special case: ai-memory

ai-memory already has an **encrypted** geographic backup to
`gbackup:ai-memory-encrypted` (crypt + Doppler). Do **not** flatten that into
plain `gbackup:db-backups/ai-memory/` without an explicit decision. Align docs
and ops so agents know which path is canonical; keep encryption unless Erik
says otherwise.

## Non-goals

- image-workflow / flo-fi rclone for media or pods (not DB offsite).
- Windows `Thumbs.db` or Swift `.build/build.db` artifacts.
- Agents copying backup files with user-owned rclone after dbmed owns them.
