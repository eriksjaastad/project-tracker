#!/usr/bin/env python3
"""Restore Done cards that the old portfolio-wide trim hard-deleted (#6871).

Until #6870, `pt tasks done` called `trim_done_tasks(keep=75)`, which counted
Done cards across ALL projects and DELETEd everything past 75. Busy projects
evicted quiet ones. `delete_audit_log` captured each row's full JSON before
deletion, so the cards are recoverable even though the rows are gone.

What this restores, and what it cannot
--------------------------------------
The audit log snapshots the task row only — 11 columns:

    id, text, status, project_id, priority, created_at, updated_at,
    completed_at, parent_id, blocked_by, sequence_order

Everything else the tasks table has since grown (`title`, `notes`, `prompt`,
`commit_sha`, `category`, `task_type`, `created_by`, `definition_of_done`, …)
was never captured and is NOT recoverable. Neither is `task_history`: the
delete cascaded to it, so a restored card has its text and dates but no event
trail. Restored cards are the record that the work happened, not a full
reconstruction of it.

Restored rows land as `status='Done'` with `archived_at` set, so they are a
queryable record without flooding any board. `pt tasks --archived` shows them.

Safety
------
- Idempotent. A card whose id is already present is skipped, so re-running
  adds nothing.
- INSERT-only. Nothing is updated or deleted, so it needs no DB safety gate.
- Deduplicated: the audit log can hold several entries for one id (a card
  deleted, recreated, deleted again). The LATEST entry per id wins.
- Skips ids already live. Verified at time of writing: the Done set has zero
  such collisions, but 11 exist among Backlog/Review entries, where the id was
  reused by a completely different card. Restoring one of those over a live row
  would be a second data-loss incident, so the check is unconditional.
- Skips projects no longer in the `projects` table unless --include-dead-projects
  is passed. Those projects were removed deliberately (Smart-Invoice, for one,
  was purged on purpose); resurrecting their cards would undo that.
- Nulls `parent_id` / `blocked_by` that point at ids which will not exist after
  the restore, rather than writing dangling references.

Usage
-----
    uv run scripts/restore_deleted_tasks.py --dry-run
    uv run scripts/restore_deleted_tasks.py --apply
"""

from __future__ import annotations

import argparse
import collections
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# The columns delete_audit_log actually captured. Anything outside this set was
# never snapshotted and cannot be restored.
BACKUP_COLUMNS = (
    "id",
    "text",
    "status",
    "project_id",
    "priority",
    "created_at",
    "updated_at",
    "completed_at",
    "parent_id",
    "blocked_by",
    "sequence_order",
)


def default_db_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "tracker.db"


def connect(db_path: Path) -> sqlite3.Connection:
    """Open the DB with cr-sqlite loaded.

    `tasks` is a CRR table, so its insert trigger calls
    `crsql_internal_sync_bit()`. A plain `sqlite3.connect` cannot execute that
    and every INSERT fails with "no such function" — the same trap #6870 hit
    when `pt db migrate` tried to ALTER without the extension.
    """
    conn = sqlite3.connect(db_path)
    crr_ified = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks__crsql_clock'"
    ).fetchone()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from db.pt_id import _find_crsqlite_dylib

    dylib = _find_crsqlite_dylib()
    if not dylib:
        if crr_ified:
            # Refuse rather than fail mid-insert. A fresh database that was
            # never through crsql_as_crr has no such trigger and is fine.
            raise RuntimeError(
                "tasks is CRR-ified but crsqlite.dylib was not found. Its "
                "insert trigger needs the extension; refusing to run."
            )
        return conn

    conn.enable_load_extension(True)
    conn.load_extension(str(dylib), entrypoint="sqlite3_crsqlite_init")
    conn.enable_load_extension(False)
    return conn


def backup_database(db_path: Path) -> Path:
    """WAL-safe copy via sqlite's backup API.

    A plain `cp` of tracker.db misses the -wal file, so the copy can be missing
    recent writes entirely. Use the backup API, which checkpoints for us.
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = db_path.parent / "backups" / f"tracker_pre_6871_restore_{stamp}.db"
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(dest)
    with dst:
        src.backup(dst)
    dst.close()
    src.close()
    return dest


def latest_deleted_rows(conn: sqlite3.Connection) -> dict[int, dict]:
    """Newest audit-log entry per task id."""
    latest: dict[int, dict] = {}
    for _, payload in conn.execute(
        "SELECT deleted_at, deleted_data FROM delete_audit_log "
        "WHERE table_name='tasks' ORDER BY deleted_at"
    ):
        row = json.loads(payload)
        latest[row["id"]] = row
    return latest


def plan_restore(conn: sqlite3.Connection, include_dead_projects: bool) -> dict:
    latest = latest_deleted_rows(conn)
    live_ids = {r[0] for r in conn.execute("SELECT id FROM tasks")}
    live_projects = {r[0] for r in conn.execute("SELECT id FROM projects")}

    candidates = {i: r for i, r in latest.items() if r.get("status") == "Done"}

    skipped_live = sorted(i for i in candidates if i in live_ids)
    remaining = {i: r for i, r in candidates.items() if i not in live_ids}

    skipped_projects: collections.Counter[str] = collections.Counter()
    if not include_dead_projects:
        for i, row in list(remaining.items()):
            if row["project_id"] not in live_projects:
                skipped_projects[row["project_id"]] += 1
                del remaining[i]

    # Anything that will exist once the restore commits.
    will_exist = live_ids | set(remaining)
    dangling = {"parent_id": 0, "blocked_by": 0}
    for row in remaining.values():
        for field in ("parent_id", "blocked_by"):
            if row.get(field) and row[field] not in will_exist:
                dangling[field] += 1
                row[field] = None

    return {
        "restore": remaining,
        "skipped_live_id": skipped_live,
        "skipped_dead_projects": skipped_projects,
        "dangling_nulled": dangling,
        "by_project": collections.Counter(r["project_id"] for r in remaining.values()),
    }


def apply_restore(conn: sqlite3.Connection, rows: dict[int, dict]) -> int:
    archived_at = datetime.now(timezone.utc).isoformat()
    columns = list(BACKUP_COLUMNS) + ["archived_at"]
    placeholders = ",".join("?" for _ in columns)
    statement = (
        f"INSERT INTO tasks ({','.join(columns)}) VALUES ({placeholders})"
    )
    inserted = 0
    with conn:
        for row in rows.values():
            values = [row.get(column) for column in BACKUP_COLUMNS] + [archived_at]
            conn.execute(statement, values)
            inserted += 1
    return inserted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="report only")
    group.add_argument("--apply", action="store_true", help="write the rows")
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument(
        "--include-dead-projects",
        action="store_true",
        help="also restore cards whose project is no longer in the projects table",
    )
    args = parser.parse_args()

    db_path = args.db or default_db_path()
    if not db_path.exists():
        print(f"database not found: {db_path}", file=sys.stderr)
        return 1

    conn = connect(db_path)
    plan = plan_restore(conn, args.include_dead_projects)
    rows = plan["restore"]

    print(f"database: {db_path}")
    print(f"cards to restore: {len(rows)}")
    if plan["skipped_live_id"]:
        print(
            f"  skipped, id already live: {len(plan['skipped_live_id'])} "
            f"({plan['skipped_live_id'][:8]}...)"
        )
    if plan["skipped_dead_projects"]:
        total = sum(plan["skipped_dead_projects"].values())
        print(f"  skipped, project no longer exists: {total}")
        for project, count in plan["skipped_dead_projects"].most_common():
            print(f"      {project}: {count}")
    print(
        f"  dangling refs nulled: parent_id={plan['dangling_nulled']['parent_id']}, "
        f"blocked_by={plan['dangling_nulled']['blocked_by']}"
    )
    print("  by project:")
    for project, count in plan["by_project"].most_common():
        print(f"      {project}: {count}")

    if args.dry_run:
        print("\ndry run — nothing written")
        return 0

    before = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    backup = backup_database(db_path)
    print(f"\nbackup: {backup}")
    inserted = apply_restore(conn, rows)
    after = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    print(f"restored {inserted} cards; tasks rows {before} -> {after}")
    if after - before != inserted:
        print("ROW COUNT MISMATCH — investigate before trusting this run", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
