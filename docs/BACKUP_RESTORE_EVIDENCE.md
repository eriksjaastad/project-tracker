# Backup / restore evidence — #6394

**Date:** 2026-09-19 (America/New_York)  
**Scope:** Prove existing local backup can recover the work queue. Production `data/tracker.db` was never replaced.

## Coverage snapshot (`pt backup status`)

| Check | Result |
|---|---|
| Local full backups | Present under `~/.project-tracker/backups/tracker_*.db` (102 files; retention 30 days via `scripts/backup-db.sh`) |
| LaunchAgent | `com.eriksjaastad.pt-backup` installed, `StartInterval` 21600 (every 6h) |
| Fresh backup | `./scripts/backup-db.sh` succeeded → `tracker_20260919_081953.db` (11 628 544 bytes) |
| Off-machine copy | **Not configured** (`PT_BACKUP_RCLONE_DEST` empty). Tracked separately as #7231 |
| Task safety JSON backups | Stale (last ~147d); not the primary recovery path |

## Restore exercise (isolated)

1. Copied latest prior snapshot `tracker_20260919_004224.db` → disposable `/tmp/pt-restore-6394-*/tracker.db`.
2. `PRAGMA integrity_check` → `ok`.
3. Row counts on disposable copy: `tasks` 2440, `projects` 56.
4. Application read: `PT_DB_PATH=<disposable> PT_SKIP_DOPPLER=1 pt tasks -p project-tracker` listed the board from that snapshot (older than same-day Done moves — expected).
5. Removed the disposable directory afterward. Production path untouched.

## Gaps / decisions

- **No additional Turso destination needed** for recovery: local SQLite atomic `.backup` + 6h LaunchAgent is sufficient for on-machine restore.
- **Off-machine** remains the material gap; do not invent a second cloud path here — use #7231 (rclone → dbmed) once dbmed is healthy.
- **`~/.project-tracker/backups` file sprawl** (~9.9k files, only ~102 `tracker_*.db`) is test junk, not retention failure on `tracker_*.db` (zero `tracker_*.db` older than 30 days). Handled under #7230.

## Conclusion

Current backup coverage is adequate for local recovery. #6394 is satisfied by this evidence; off-machine and junk cleanup stay on their own cards.
