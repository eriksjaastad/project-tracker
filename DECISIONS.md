# Decisions

Deliberate architectural choices. Read before changing anything structural.
To revisit a decision, don't edit — add a new entry that supersedes it.

## One schema path: generated schema.sql plus migrations, one ledger
**Accepted 2026-10-12 (Erik's plan mark on #8093, item 4.5).**

A fresh database is built from `scripts/db/schema.sql` and its
`schema_migrations` ledger is marked for every migration that file contains;
every change after that is a numbered migration. The file is generated
(`make schema`) from create_database plus all migrations, never hand-written,
and a test fails until it is regenerated, so the two can't drift. This
replaced `ensure_schema` (742 lines that recreated, ALTERed and rebuilt
tables), the runtime DDL in the calendar and attachment managers, and the
`schema_version` ledger, which had been frozen at 9 since April and only gated
whether ensure_schema ran.

Trade-off, accepted: a database that has tables but no `schema_migrations`
ledger (anything older than April 2026) is refused instead of upgraded in
place, because upgrading it would replay table rebuilds over real data.
Restore a newer backup instead.

The `.db-fingerprint` sidecar is now only a marker: its existence tells the
fresh-database guard that a database with data lived here, which survives the
file being replaced. Its uuid was also matched against a copy in `_metadata`,
but that check could only run at creation on an empty database, so it never
fired; keeping two copies in sync was the only source of creation races, so
the copy and the check are gone.

The dead `schema_version` and
`schema_migration_announcements` tables are left in existing databases;
dropping them would need the DB gate for no benefit.

---

## Retire card_factory_grok instead of fixing its dependency path
**Accepted 2026-10-08 (Erik, #8050).**

`scripts/card_factory_grok.py` and its test are removed. It was a shadow
experiment to judge grok-build-0.1's tool use before wiring it into Auxesis,
and Auxesis is canceled. In its life it had one shadow run (2026-06-24,
muffinpanrecipes) and never created a card, yet it was patched four times
(worktree-safe projects root, OpenRouter routing, acceptance criteria, a
dependency-path fix in #7974), and a second path fix was in flight after
synth-insight-labs renamed its cost-tracker client. Erik's
direction going forward: build less infrastructure that serves every project,
because it is unmaintainable and generates work nobody follows through on.
Nothing in this repo now reads `OPENROUTER_API_KEY` or `XAI_API_KEY`; both
were left in Doppler. To trial a model this way again, start from git history
(last version at 3048f60) and depend on `api-cost-tracker` from PyPI.

---

## Retire doc_audit_v2 instead of redesigning its cache
**Accepted 2026-10-05 (Erik, via Architect, #7975).**

`scripts/doc_audit_v2.py`, its wrapper `scripts/doc_audit_daily.sh` and the
`com.eriksjaastad.doc-audit` launchd template are removed. The launchd job was
never installed and nothing consumed the output. Its pipeline reused cached
batches, atlas entries and clusters without checking they were current, and
fixing that properly would mean redesigning the cache around what each stage
consumes. #7973 had just moved it to OpenRouter. Retiring it is cheaper than
that redesign. The older prompt-only `scripts/doc_audit.py` is not affected (it was cut
later in #8093; last version at b1a138a).
To bring document auditing back, start from git history (last version at the
#7973 merge, 4d5f637) and design cache invalidation first.

---

## Retire dbmed; use consistent snapshots and rclone
**Accepted 2026-09-22; supersedes the 2026-09-17 database lockdown initiative.**

Erik cancelled the rollout and explicitly requested removal of the installed
service. Project Tracker returns to its existing in-process database operations.
Backups use the SQLite backup API and the existing rclone destination; preserve
backup history, destructive-operation confirmation, and SAFE_MODE. No replacement
storage gate is planned. The root-owned installation was retired the same day
(runbook `docs/DBMED_RETIREMENT.md`, removed in #8093; see git history).

Snapshot with SQLite's backup API (copying a live file without its WAL is not a
backup), then rclone the snapshot to `gbackup:db-backups/<project>/`; rclone
credentials stay in the user's rclone config. An upload is not proof of
recovery: restore a downloaded copy into an isolated directory, never over
production. ai-memory keeps its encrypted `gbackup:ai-memory-encrypted`
destination, and its thoughts export is not a full-database recovery path.
(Folded from `docs/PORTFOLIO_OFFSITE_DB_BACKUPS.md`, removed in #8093.)

---

## Dual-Interface Architecture (CLI + Web Dashboard)
**Accepted 2026-04-04**

**Context:** Agents need parseable output they can pipe and grep. Humans need a visual Kanban board. A single interface cannot serve both.

**Decision:** The CLI (`pt`, Click) outputs strict plain-text format (`#<id> [markers] | [<project> |] <status> | <priority> | <text>`, where the markers are `[!P]`/`[~P]` for a missing or incomplete prompt and `[B:…]` for blockers, and the project column appears without `-p`) for agent parsing. A separate React/FastAPI web dashboard provides visual UX. Both share the same data layer. The CLI output format is a contract — changing it is a breaking change for all agent workflows.

| Alternative | Why rejected |
|-------------|-------------|
| API-only (JSON) | Agents can't easily pipe raw JSON without jq gymnastics |
| GUI-only | Agents can't drive a browser-based UI |
| Rich CLI formatting | Breaks agent parsing — invisible characters, variable-width columns |

**Consequences:** Two interfaces to maintain, each optimized for its audience. CLI format must be treated as a stable API.

---

## Optional Cloud Database with Automatic Fallback (Turso + Local SQLite)
**Accepted 2026-04-04. Superseded 2026-10-09 by "Turso code removed (#8093)".**

**Context:** Production use requires cross-machine sync. But agents and developers must work offline without friction — no config, no errors, no mode flags.

**Decision:** When `TURSO_KANBAN_URL` and `TURSO_KANBAN_TOKEN` env vars are set, connect to remote Turso (libsql). When either is missing, silently fall back to local SQLite. No flags, no prompts — env var presence is the only switch.

| Alternative | Why rejected |
|-------------|-------------|
| Cloud-only (Turso always) | Breaks offline workflows, CI without credentials |
| Local-only (SQLite always) | No cross-machine sync |
| Explicit mode flag (`--remote`) | Adds friction, agents forget flags |

**Consequences:** Offline-first with optional cloud. Local and cloud databases can diverge if machines work offline simultaneously — sync conflicts must be managed externally.

---

## Safety-First Database Operations (Multi-Layer Backups)
**Accepted 2026-04-04**

**Context:** On 2026-01-27, an auto-migration dropped 94 tasks. The database is critical state. One backup location is not enough if the project directory itself is deleted.

**Decision:** Three rules, no exceptions: (1) No destructive SQL (DROP TABLE, DELETE FROM) without explicit user approval. (2) Schema changes are numbered migrations applied only by `pt db migrate`, which takes and verifies a backup first; one that rebuilds or drops a table also needs the DB gate in CLAUDE.md. (3) Automatic backups to TWO locations — `data/backups/` (inside project) and `~/.project-tracker/backups/` (outside project).

| Alternative | Why rejected |
|-------------|-------------|
| Single backup location | The 2026-01-27 incident proved one location can be lost with the project |
| Allow destructive migrations with backups | Backups can fail silently |
| No backups (trust version control) | Database is not in git; binary files don't diff well |

**Consequences:** Schema changes are slower. Disk usage increases from dual backups. But task data is protected — recovery from any single point of failure is guaranteed.

---

## Handoffs are LOCAL_ONLY by design
**Accepted 2026-05-06. Moot since migration 018 (2026-10-09): no table replicates.**

**Context:** Phase D of the locked-project hygiene workflow introduces a `handoffs` table that records structured "unfinished work" / non-PR exit records. Reviewer asked whether this table should replicate cross-machine via CRR.

**Decision:** `handoffs` is classified `LOCAL_ONLY`. A handoff exists *because* there is uncommitted local work in a dirty tree. That dirty tree is, by definition, machine-local — it has not been pushed. If the handoff replicated cross-machine, an agent on Machine B would read "your branch X has dirty work" but the dirty tree itself would still be on Machine A with no way to access it. The handoff would be a tease, not a resume point. Keeping handoffs LOCAL_ONLY makes the contract honest: a handoff record is only meaningful on the machine that produced it.

| Alternative | Why rejected |
|-------------|-------------|
| CRR (replicate cross-machine) | Replicates a pointer to dirty work that doesn't exist on the receiving machine — misleading |
| CONTROL_PLANE | Not a sync coordination primitive; nothing depends on its replication |

**Consequences:** Cross-machine resumption of unfinished work is not supported through `pt handoff`. To carry work across machines an agent must commit (even a WIP commit) and push the branch — at which point the work is no longer "unfinished local" and a Phase C PR-style record is appropriate instead.

---

## 2026-04-20 — what the cr-sqlite prep migrations left behind
**Recorded 2026-10-12 (#8093), from `PHASE2_DAMAGE_REPORT.md`, removed in #8093; see git history.**

**Context:** Migrations 003–008 rebuilt tables to satisfy `crsql_as_crr()`, finding its rejections one at a time. Migration 005 ran on the live database before its PR was reviewed, and its UNIQUE-constraint rejection was found only after it had merged.

**Decision:** None of this is rolled back now that cr-sqlite is gone (018). `projects.name` and `project_info(project_id, key)` still carry no UNIQUE constraint in `schema.sql`; restoring one is a table rebuild and needs the DB gate. Lesson: collect every requirement of a storage dependency against a scratch copy of the real schema before writing migrations, and never apply a migration to the live database before its PR is reviewed.

---

## 2026-10-09 — Turso code removed (#8093)
**Accepted 2026-10-09**

**Context:** Turso has been off since 2026-04-05 (local SQLite; Turso added about 2.5s per query for no benefit), and `ProjectTrackerOps` already refused to run with it on, so the libsql path could not execute.

**Decision:** Delete the libsql wrappers, connection pool, `_USE_TURSO` branches, `turso_to_local.py`, `TURSO_SETUP.md`, the `libsql` dependency and the `.turso-config.json` gate in the skills reader. The `pt` launcher no longer wraps in Doppler: its only skip condition was that config file, and nothing in `pt` needs a secret. This supersedes "Optional Cloud Database with Automatic Fallback".

---

## 2026-10-09 — sync stack removed (#8093)
**Accepted 2026-10-09**

**Context:** The cr-sqlite sync daemon (`sync_daemon`, `sync_http`, `sync_state`, `sync_checks`), `pt sync` and the `com.pt.sync-daemon` / `com.pt.tailscale-up` LaunchAgent templates were never installed; the daemon's exchange was a stub and the last sync was April 2026. The tailscale-up login job failed on every login.

**Decision:** Delete the stack, `pt sync`, its tests, `scripts/log_rotation.py` (the daemon's only caller), `scripts/launchd/install.sh` and two uninstalled job templates (`complexity-scan.plist`, `com.user.ecosystem_maintenance.plist`). Migration `002_add_sync_ledgers` and the CRR manifest stay: cr-sqlite goes in its own PR.

---

## 2026-10-09 — cr-sqlite removed (#8093, D2)
**Accepted 2026-10-09 (Erik, D2).**

**Context:** With the sync stack gone, cr-sqlite only added cost: 30 triggers, 20 clock and pk tables (136,974 clock rows on 2026-10-09), a dylib loaded on every connection, and a `crsql_finalize()` workaround for leaked descriptors (#6482).

**Decision:** Migration `018_drop_cr_sqlite` drops the triggers, `__crsql_clock` / `__crsql_pks` tables and the three `crsql_*` metadata tables, after writing the machine id the old code derived from `crsql_site_id()` into `_metadata['pt.machine_id']` so ID machine bits stay continuous. No connection loads the extension any more; `crr_manifest.py` and the runner's alter bracketing are deleted. A database still carrying `__crsql_` triggers (a restored pre-018 backup) can be read, but its writes fail with SQLite's own "no such function: crsql_internal_sync_bit" until `pt db migrate` runs; pt's pending-migrations notice names the fix. `pt db migrate` runs 018's cleanup first, as one transaction, whenever cr-sqlite objects remain, so any older backup upgrades cleanly. Run the migration right after merge, since code without the extension cannot write to a database with the triggers.
