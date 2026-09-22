# Migration Manifests


Append-only log of `pt migration` sessions. Each section records the paths touched between `start` and `finish` for a named bulk operation.


## daisy-studios-collection — 2026-08-07T05:04:20Z

- started_at:  `2026-08-07T05:03:31Z`
- finished_at: `2026-08-07T05:04:20Z`
- baseline_head: `31b424c58a11a2dde98f4e1c9507ef8e1c5418dc`
- action: `manifest-only`

### New paths (introduced during session)
- _(none)_

### Modified paths (status changed during session)
- _(none)_

---

## card-factory-librarian-auth — 2026-08-14T23:28:23Z

- started_at:  `2026-08-14T23:08:14Z`
- finished_at: `2026-08-14T23:28:23Z`
- baseline_head: `31b424c58a11a2dde98f4e1c9507ef8e1c5418dc`
- action: `manifest-only`

### New paths (introduced during session)
- _(none)_

### Modified paths (status changed during session)
- _(none)_

---

## van-zero-business-use — 2026-09-01T17:20:32Z

- started_at:  `2026-09-01T17:17:44Z`
- finished_at: `2026-09-01T17:20:32Z`
- baseline_head: `a74cc081ab56f4a46ec7d6f4ec454e0a5995f981`
- action: `manifest-only`

### New paths (introduced during session)
- _(none)_

### Modified paths (status changed during session)
- _(none)_

---

## root-cleanup-2026-09-04 — 2026-09-04T19:08:41Z

- started_at:  `2026-09-04T19:07:10Z`
- finished_at: `2026-09-04T19:08:41Z`
- baseline_head: `a74cc081ab56f4a46ec7d6f4ec454e0a5995f981`
- action: `manifest-only`

### New paths (introduced during session)
- _(none)_

### Modified paths (status changed during session)
- _(none)_

---

## docs-consolidation-2026-09-04 — 2026-09-04T19:27:55Z

- started_at:  `2026-09-04T19:27:17Z`
- finished_at: `2026-09-04T19:27:55Z`
- baseline_head: `a74cc081ab56f4a46ec7d6f4ec454e0a5995f981`
- action: `manifest-only`

### New paths (introduced during session)
- _(none)_

### Modified paths (status changed during session)
- _(none)_

---

## pr189-test-boundary-repair — 2026-09-19T22:57:07Z

- started_at:  `2026-09-19T22:36:05Z`
- finished_at: `2026-09-19T22:57:07Z`
- baseline_head: `d9d3254f133881d52bea55fe795a26f1bd0c014b`
- action: `manifest-only`

### New paths (introduced during session)
- `[dirty]` `conftest.py`
- `[dirty]` `scripts/db/dbmed_ops.py`
- `[dirty]` `scripts/pt.py`
- `[dirty]` `tests/boundary/README.md`
- `[dirty]` `tests/boundary/test_evidence_matrix.py`
- `[dirty]` `tests/boundary/test_posix_denial.py`
- `[dirty]` `tests/test_agentic_summary.py`
- `[dirty]` `tests/test_backup_reader.py`
- `[dirty]` `tests/test_blocked_by_resolution.py`
- `[dirty]` `tests/test_dashboard_health.py`
- `[dirty]` `tests/test_db_connection_leak.py`
- `[dirty]` `tests/test_kanban_breakdown_api.py`
- `[dirty]` `tests/test_pt_db_migrate.py`
- `[dirty]` `tests/test_pt_sync_cli.py`
- `[dirty]` `tests/test_retire_project.py`
- `[dirty]` `tests/test_scan_safety.py`
- `[dirty]` `tests/test_schema_backup_safety.py`
- `[dirty]` `tests/test_subtasks_dependencies.py`
- `[untracked]` `tests/boundary/test_calendar_client.py`
- `[untracked]` `tests/boundary/test_fixture_provisioning.py`

### Modified paths (status changed during session)
- _(none)_

---

## dbmed-retirement-7422 — 2026-09-22T18:12:32Z

- started_at:  `2026-09-22T18:11:40Z`
- finished_at: `2026-09-22T18:12:32Z`
- baseline_head: `cc647719193d9b1cfe059ad1bd4cef2a0f76dbdb`
- action: `committed`
- WARNING: HEAD drifted from baseline cc647719193d to 9784d063f2e9; revert will restore against current HEAD

### New paths (introduced during session)
- _(none)_

### Modified paths (status changed during session)
- _(none)_

---

Audit note: recording began after the working-tree edits were prepared. The
implementation commit is 9784d063f2e9fc783bf84ebb6eb6cbd0af745a6f; its diff
against 17d49b661a37bf728dfb11e23090c7946c474380 is the authoritative change list.
The rebase excluded unrelated, unmerged monitoring changes from the source
checkout. No live installation or production database was moved during this audit.
