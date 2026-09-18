# Project DoD: dbmed — enforced database boundary (Phase 1)

Cards #7228 (mechanism) and #7219 (project-tracker reference). Umbrella acceptance is #7217.

## Outcomes (What "shipped" looks like)
- [ ] A `_dbmed` service account exists and owns `/usr/local/var/dbmed` at mode 0700
- [ ] `tracker.db`, its `-wal`/`-shm`, `data/backups/` (547 files), `~/.project-tracker/backups/`, and the two stale full copies in `data/` all live under `_dbmed` ownership
- [ ] `dbmedd` runs from `/usr/local/libexec/dbmed` (root:wheel) under a root-owned LaunchDaemon, as `_dbmed`
- [ ] `pt tasks`, `pt info`, `pt backup status`, `pt memory`, and every other common command work unchanged
- [ ] The dashboard serves at `localhost:8000` and `/api/health` returns healthy
- [ ] The calendar poller and the `com.eriksjaastad.pt-backup` LaunchAgent run as clients
- [ ] `EVIDENCE.md` records the runtime/host/operation matrix, including the uncovered paths
- [ ] A rollback script exists and has been run successfully at least once

## Constraints (What must always be true)
- [ ] No SQL, database path, shell command, or caller-supplied code crosses the socket — named operations with parameter schemas only
- [ ] The client module imports no database driver. `grep -E 'sqlite3|libsql|psycopg' scripts/db/manager.py` returns nothing
- [ ] Daemon unavailable ⇒ non-zero exit and a message naming the daemon. Never a fallback to direct access
- [ ] A project absent from the registry is denied, not defaulted
- [ ] `crsqlite.dylib` is loaded only from the root-owned install path, by absolute path
- [ ] No client environment variable changes daemon behaviour — `PT_DB_PATH`, `PT_TEST_MODE`, `PT_ALLOW_FRESH_DB`, `SAFE_MODE`, `ALLOW_BULK_DELETE` are daemon-side config or gone
- [ ] Destructive operations refuse by default, require a daemon-issued token, and verify a timestamped backup exists before mutating
- [ ] Migrations stay additive, and run only from the installed root-owned migrations directory — no `exec_module` on a caller-supplied path
- [ ] Dual backup locations survive (DECISIONS.md), both now outside agent reach
- [ ] The Bash-gate additions are pure-Python with no subprocess, and measured against the 5s timeout that fails open
- [ ] No test opens a live database. `data/` is unchanged after a full `make test`
- [ ] Zero rows lost: counts before and after cutover match

## Non-Goals (Explicitly out of scope for this milestone)
- The other ten database projects (#7218, #7220–#7227) and the reusable template (#7229)
- Mac Mini installation
- Verifying Codex, Cursor, and Grok deny `sudo`
- A Turso or hosted-database migration
- Restricting Erik's own interactive access
- ai-memory's `brain.db`, which `pt` and the dashboard read at eight sites — carded for #7220
- The dashboard's `POST /api/agents/run` shell endpoint — a privilege path, not a database path

## Evidence Required (What proves it)
- [ ] **Denial matrix, every row denied**, against a synthetic fixture behind the same boundary — never live data: `sqlite3` CLI and `/usr/bin/sqlite3`; Python `sqlite3` and `libsql`; Node; `cat`/`head`/`strings`/`xxd`/`dd`; `cp`/`mv`/`rm`/`ln -s` on the file and both journals; the Read tool; `sh -c` and `xargs`; `ssh localhost`; a symlink planted in the repo; `PT_DB_PATH` aimed at the protected path
- [ ] **Guard-tamper probes denied**: editing the plist, editing installed backend code, swapping the dylib, `chmod`/`chown`, `launchctl unload`
- [ ] **Sanctioned success**: every common `pt` command, the dashboard end to end, the poller, the backup job, invalid operations erroring truthfully
- [ ] **Fail-closed proof**: daemon stopped ⇒ `pt tasks` exits non-zero and no file access occurs
- [ ] **Destructive-gate proof**: refusal without a token; with a token, a verified timestamped backup exists before the mutation and an audit record is written
- [ ] **No active instruction teaches direct access**: the `pm` skill's `sqlite3` fallback removed, `PHASE_2_4_RUNBOOK.md` neutralised, `TURSO_SETUP.md:40` fixed
- [ ] **Row-count parity** before and after cutover, via the sanctioned operation
- [ ] **Uncovered paths stated as unfinished**, never as a pass — per #7217, an uncovered path is unfinished work

## Repeatability (How to re-run the proof)
- `uv run pytest tests/boundary/ -v` — the full matrix, self-contained against a daemon-provisioned fixture
- `make test` — suite green, `git status` on `data/` clean
- `sudo launchctl bootout system/com.dbmed` → `./pt tasks` → expect non-zero → `sudo launchctl bootstrap` → expect recovery
- `sudo scripts/dbmed-install/rollback.sh` then `sudo scripts/dbmed-install/install.sh` — round-trips the cutover
