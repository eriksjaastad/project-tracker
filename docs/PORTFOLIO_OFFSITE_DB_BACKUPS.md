# Portfolio offsite database backups

Erik cancelled the dbmed rollout on 2026-09-20 and reconfirmed removal on
2026-09-22. Backups are the chosen control. Projects need no mediation daemon,
service account, registry, or storage gate to adopt this convention.

Create a transactionally consistent local snapshot with SQLite's backup API
(or the database's native backup tool), then upload that snapshot with rclone.
Copying a live SQLite file without its WAL is not a valid backup.

Use the existing `gbackup` remote and `db-backups/<project-name>/` destination.
Keep credentials and recoverable encryption keys in Doppler. The existing
rclone provider configuration is used at runtime; do not print credentials or
commit a provider configuration to the repository.

For Project Tracker, set `PT_BACKUP_RCLONE_DEST=gbackup:db-backups/project-tracker`
in the scheduled backup job's environment. The optional `RCLONE_CONFIG` selects
an existing configuration file; otherwise rclone's normal user config is used.
Then run:

```bash
pt backup create
pt backup offsite
pt backup prune
pt backup status
```

The scheduled job runs `scripts/backup-db.sh`, which runs create, offsite and
prune in that order. Local snapshots remain available when upload fails; the job logs the
offsite and prune results separately. Snapshot history lives in `data/backups/`
and `~/.project-tracker/backups/`; `pt backup prune` keeps the newest backups of
each kind there and moves the rest to the Trash (`pt backup prune --help` gives
the counts; `--dry-run` lists what would move). A successful upload
alone is not proof of recovery: download a snapshot into an isolated directory,
check database integrity, and verify representative data through the project
application. Never test recovery by replacing production data.

For each other project, use its native database tool to create snapshots and
its existing scheduler to run snapshot creation followed by rclone copy.
Confirm both local and offsite results and prove an isolated restore.
Backup cards #7304–#7312 carry this scope; cancelled lockdown cards are not
prerequisites.

## ai-memory encryption

Keep `gbackup:ai-memory-encrypted`, its crypt settings, and the Doppler recovery
bundle. Do not migrate it to a plain `db-backups/ai-memory` folder. Its thoughts
JSON export is useful but is not automatically a full-database recovery path;
record and test those two forms of coverage separately.
