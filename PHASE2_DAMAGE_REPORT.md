# Phase 2 Damage Report — Migration 005 Aftermath

Written 2026-04-20 at the request of Erik after §2.5.1 failed to unblock.

---

## What was supposed to happen

Three migrations (003, 004, 005) would prepare all 10 CRR tables for `crsql_as_crr()`. After merging 005, both machines would run `pt db migrate` and `crsql_as_crr('ideas')` (and all 10 tables) would succeed.

## What actually happened

Migration 005 merged and applied on both machines. First call to `crsql_as_crr()` failed immediately on `projects` with a new rejection type we didn't anticipate. Testing is incomplete.

---

## Problems — Caused

### 1. ON DELETE CASCADE permanently removed from all 10 CRR tables

All FK declarations — and with them, all DB-level CASCADE behavior — were stripped from the live DB on both machines. `delete_task()`, `delete_project()`, `delete_done_tasks()`, and `trim_done_tasks()` previously relied on CASCADE to clean child rows automatically. That safety net is gone.

I replaced it with explicit child-row deletes in those four methods. However:
- The replacement was written during the same session, under deadline pressure, reviewed in 4 rounds of back-and-forth
- Every round found new delete paths that were missed
- No tests were added for the new explicit-cascade behavior in `manager.py`
- The code is more complex and has more surface area for orphan bugs than the old CASCADE approach

**Reversibility:** The migration cannot be undone without migration 006 (adding FKs back), which would require another Safety Gate, another rebuild of all 10 tables, and re-testing. Not a quick fix.

### 2. Migration applied to live DB before the PR was reviewed

Migration 005 ran on the live laptop DB at 16:13. The PR was opened, reviewed in 4 rounds, and merged hours later. The live DB was modified while the code was still being audited for correctness.

The review process caught critical issues (orphan rows in all four delete paths) that were fixed before merge — but those fixes never ran on the live DB. The live DB has the migration but not the delete-path fixes (those are in Python, not SQL, so they apply on next restart, but the point stands: we applied a structural DB change before we knew the application-level compensations were correct).

### 3. The code reviewer ran 4 rounds and still didn't get everything

- Round 1 (pre-push): FAIL — found orphan bugs in delete_task and delete_project
- Round 2 (post-push): FAIL — found FK declarations in schema.py legacy paths; missing _tbl_exists guards in delete_task
- Round 3: FAIL — found same orphan bug in delete_done_tasks and trim_done_tasks
- Round 4: FAIL — cron_jobs FK inconsistency
- Round 5: PASS

Four rounds of code review to find issues that should have been found in design. The original migration plan did not mention any of these delete paths.

---

## Problems — Uncovered (pre-existing, now visible)

### 4. cr-sqlite UNIQUE constraint rejection — NEW BLOCKER

`crsql_as_crr()` also rejects tables with unique indexes beyond the primary key. Two tables are affected:

- `projects.name TEXT UNIQUE NOT NULL` — prevents duplicate project names
- `project_info UNIQUE(project_id, key)` — prevents duplicate key entries per project

This was not in the original plan. It was not tested on a real schema before starting migrations. It means migration 005 was not the last migration needed — at minimum migration 006 is required.

**Critical concern with project_info:** The `UNIQUE(project_id, key)` constraint is not just documentation. `manager.py` uses `INSERT ... ON CONFLICT(project_id, key) DO UPDATE SET` syntax. That SQL requires the UNIQUE constraint to exist. If we remove the UNIQUE, `ON CONFLICT(project_id, key)` becomes syntactically invalid (SQLite requires the conflict column set to match a unique index). This would break every `set_project_info()` call in the application.

### 5. cr-sqlite requirements were never fully enumerated before starting

The original plan listed 3 requirements: no AUTOINCREMENT, explicit NOT NULL on PKs, DEFAULT values on NOT NULL non-PK columns. We discovered FK constraints mid-session during migration 003 testing. We discovered UNIQUE constraint rejection only after migration 005 was merged and deployed.

The correct approach would have been: run `crsql_as_crr()` against a scratch copy of the real schema BEFORE writing any migrations, collect ALL rejection messages, then write all required migrations as a set. Instead we ran them as a waterfall where each migration revealed a new blocker.

### 6. Unknown additional cr-sqlite requirements may exist

We have now hit: AUTOINCREMENT, NOT NULL on PKs, DEFAULT values, FK declarations, UNIQUE indexes. We don't know if there are more. The pattern suggests we haven't read the cr-sqlite documentation comprehensively — we've been reading rejection messages.

---

## Current state of the live DB (both machines)

| Item | State |
|------|-------|
| Migration 003 | Applied — PKs have explicit NOT NULL, no AUTOINCREMENT |
| Migration 004 | Applied — NOT NULL columns have DEFAULT values |
| Migration 005 | Applied — FK declarations stripped from all 10 CRR tables |
| CASCADE behavior | Gone from all 10 CRR tables (DB level) |
| Application cascade deletes | Added to 4 delete methods in manager.py (Python) |
| `crsql_as_crr()` | NOT yet successful — blocked on UNIQUE constraints |
| `ideas` specifically | Likely to pass `crsql_as_crr()` (no UNIQUE, no FK) — untested |
| `projects` | Blocked — name UNIQUE NOT NULL |
| `project_info` | Blocked — UNIQUE(project_id, key), and removing it breaks ON CONFLICT syntax |

---

## What the incoming agent needs to know

1. **Read the cr-sqlite docs first, in full.** Get every requirement for `crsql_as_crr()` before writing anything.
2. **Test on a scratch copy of the real schema** — not a minimal test fixture — before writing any migration.
3. **project_info is the most dangerous** — removing its UNIQUE constraint breaks `ON CONFLICT(project_id, key) DO UPDATE` syntax throughout manager.py. This is not a simple strip-and-rebuild.
4. **The backups exist** — pre-migration backups are at `data/backups/` and `~/.project-tracker/backups/` for all three migrations. If rollback becomes necessary, the data is there.
5. **413 tests pass** — the test suite is green. The damage is in production schema behavior and in requirements we didn't understand, not in test regressions.
6. **The application delete paths are now more complex** and have no test coverage for the new explicit-cascade behavior. That's a risk.
