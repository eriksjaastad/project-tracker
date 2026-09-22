# Retire dbmed — #7422 / #7393

The 2026-09-22 decision removes dbmed and keeps database snapshots plus rclone.
This cutover is laptop-only: the original installation was Phase 1 on the
laptop. Do not run it on another host without an installed dbmed database.

The code now opens `data/tracker.db` through the existing project operations.
The CLI and dashboard retain task/calendar operations, migration commands,
backup/restore, SAFE_MODE, and destructive-operation confirmation and backups.

## Cutover

1. Finish PR review and deploy this commit into the normal Project Tracker
   checkout. Stop the dashboard and scheduled Project Tracker callers during
   the maintenance window; the old service still holds the authoritative DB.
2. Run the reviewed retirement script as the workstation owner through sudo:

   ```bash
   sudo python3 scripts/retire_dbmed.py --repo "$PWD"
   ```

   Use Python 3.11 or newer. The script checks that the replacement manager is
   deployed, refuses existing target DB/WAL/SHM files, stops and verifies the
   old service, and creates a consistent snapshot. Integrity and every ordinary
   table's row count must match. Existing backup histories are copied without
   overwriting different files. A verified independent pre-cutover snapshot
   and JSON receipt remain in `data/dbmed-retirement-*`.

   It then publishes the database, archives the old database, configuration,
   code, runtime and LaunchDaemon plist under `/usr/local/var/dbmed-retired/`,
   and removes the dedicated `_dbmed` account and group. It does not delete
   database rows, old backups, or the shared `/usr/local/var/run` directory.
   If copying fails before publication, the original service is restarted.
   After publication, any failure is reported for inspection; it never starts
   two writable database copies automatically.
3. Restart the dashboard and scheduled callers. Verify `pt tasks --json`,
   `pt calendar list`, and `/api/health`; the reported database path must be
   the normal checkout's `data/tracker.db`. Compare the receipt's counts and
   check `pt backup list` includes the preserved history.
4. Configure the existing scheduled backup job with
   `PT_BACKUP_RCLONE_DEST=gbackup:db-backups/project-tracker` in its plist
   `EnvironmentVariables`. Manual runs and status also read those persisted
   settings; explicit process environment overrides them. `RCLONE_CONFIG` and
   `PT_EXTERNAL_BACKUP_DIR` use the same precedence when customized. Run
   `pt backup create`, `pt backup offsite`, and `pt backup status`. Download the
   uploaded snapshot and prove an isolated restore before recording offsite
   success. The original user rclone config remains in place; credentials stay
   in Doppler and must not be copied into repository files.
5. Verify `launchctl print system/com.dbmed` no longer finds the service.
   Complete #7422 and #7393 only after live checks; cancel #7412 as superseded.

Project Tracker uses local SQLite throughout. If the shared Turso switch is
enabled, it refuses startup before opening either database; it must never back
up a local file and then mutate a remote database. This retirement does not
change that shared switch or any ai-memory backend configuration.

## Recovery

The script prints the receipt and archive paths. Both the original database
(including its old journals) and an independent consistent snapshot are
preserved. If the local application fails, stop its writers before restoring
from a verified copy; never mix the old database with another copy's WAL/SHM.
Restoring the old service additionally requires its archived runtime, config,
service identity, and the previous code revision. Inspect the receipt and
actual state before attempting recovery; do not blindly rerun the old installer.

## Verification limits

Tests use synthetic SQLite fixtures and verify copy conflicts, WAL snapshots,
backup/restore, and application operations without a dbmed socket. They do not
prove a root-owned macOS installation has been removed. Record the live
cutover, scheduler, upload, and isolated-restore results on the cards.
