#!/usr/bin/env python3
"""Rewrite display IDs stored in `tasks.blocked_by` to canonical PKs (#6747).

`pt tasks create/update --blocked-by` ran a raw `int()` over the tokens and
stored them verbatim, with no resolution and no existence check. Display IDs
are what the board prints and what every other command accepts, so operators
typed them — and they landed in the column matching no `tasks.id`.

Why that matters
----------------
`get_blocking_tasks` resolves each stored ID with `get_task` and silently drops
the misses. With every ID missing, `is_blocked` answers `(False, [])` and the
card reports itself unblocked while it is genuinely blocked. The CLI even
printed "Blocked by: (all resolved)". This script repairs the rows that were
written before the CLI fix landed.

What it does, and what it refuses to do
---------------------------------------
- A stored value that is already a live `tasks.id` is left alone. Correct rows
  are not touched.
- A stored value that is not live but IS a `task_display_ids.display_id` is
  rewritten to that row's `task_id`. This is a lookup, not a guess.
- A stored value that is neither is LEFT IN PLACE and the row is reported as
  `partial`. Guessing at an ID that matches nothing is how you invent a
  dependency that never existed.
- Resolution can produce duplicates (two display IDs pointing at one card);
  the result is deduplicated, order preserved.
- Rows whose resolved list equals the stored list are skipped — no write.
- Malformed JSON (or a non-list value) is reported and skipped, never
  rewritten.

Safety
------
- UPDATE-only, one column, and only on rows that actually change.
- `--dry-run` prints the full before/after per row and writes nothing.
- `--apply` takes a WAL-safe backup via sqlite's backup API first. A plain
  `cp` of tracker.db misses the -wal file and can silently omit recent writes.
- `tasks` is a CRR table, so its update trigger calls
  `crsql_internal_sync_bit()`. Without crsqlite.dylib loaded every write fails
  with "no such function"; `connect()` loads it and refuses to run on a
  CRR-ified DB when the dylib is missing.

Usage
-----
    uv run scripts/backfill_blocked_by.py --dry-run
    uv run scripts/backfill_blocked_by.py --apply
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def default_db_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "tracker.db"


def connect(db_path: Path) -> sqlite3.Connection:
    """Open the DB with cr-sqlite loaded.

    `tasks` is a CRR table, so its update trigger calls
    `crsql_internal_sync_bit()`. A plain `sqlite3.connect` cannot execute that
    and every UPDATE fails with "no such function" — the same trap #6870 hit
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
            # Refuse rather than fail mid-update. A fresh database that was
            # never through crsql_as_crr has no such trigger and is fine.
            raise RuntimeError(
                "tasks is CRR-ified but crsqlite.dylib was not found. Its "
                "update trigger needs the extension; refusing to run."
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
    dest = db_path.parent / "backups" / f"tracker_pre_6747_backfill_{stamp}.db"
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(dest)
    with dst:
        src.backup(dst)
    dst.close()
    src.close()
    return dest


def plan_backfill(conn: sqlite3.Connection) -> dict:
    """Work out the rewrite for every row that carries a blocked_by value."""
    live_ids = {r[0] for r in conn.execute("SELECT id FROM tasks")}
    display_to_pk = {
        r[0]: r[1]
        for r in conn.execute("SELECT display_id, task_id FROM task_display_ids")
    }
    pk_to_display = {v: k for k, v in display_to_pk.items()}

    rewrites: list[dict] = []
    partial: list[dict] = []
    malformed: list[dict] = []
    already_correct = 0

    rows = conn.execute(
        "SELECT id, project_id, status, text, blocked_by FROM tasks "
        "WHERE blocked_by IS NOT NULL AND blocked_by != '' "
        "ORDER BY id"
    ).fetchall()

    for task_id, project_id, status, text, raw in rows:
        try:
            stored = json.loads(raw)
        except (TypeError, ValueError):
            malformed.append(
                {"task_id": task_id, "project_id": project_id, "raw": raw}
            )
            continue
        if not isinstance(stored, list):
            malformed.append(
                {"task_id": task_id, "project_id": project_id, "raw": raw}
            )
            continue

        resolved: list = []
        unresolved: list = []
        for token in stored:
            # NOTE: this checks live PKs before display IDs, the opposite order
            # from `DatabaseManager.resolve_task_id`, which tries display_id
            # first. The two cannot currently disagree: migration 009 gave
            # legacy tasks `display_id == id` and allocates newer display_ids
            # only above the max legacy id, while Snowflake `tasks.id` values
            # are all >= 10**12 — so the ranges the two orderings would rank
            # differently never overlap. If either allocation scheme changes,
            # this and `resolve_task_id` must be reconciled deliberately.
            if token in live_ids:
                resolved.append(token)
            elif isinstance(token, int) and token in display_to_pk:
                target = display_to_pk[token]
                if target in live_ids:
                    resolved.append(target)
                else:
                    # display_ids row points at a task that no longer exists.
                    unresolved.append(token)
                    resolved.append(token)
            else:
                unresolved.append(token)
                resolved.append(token)

        # Dedupe, order preserved. Two display IDs can point at one card.
        deduped: list = []
        for value in resolved:
            if value not in deduped:
                deduped.append(value)

        if deduped == stored:
            already_correct += 1
            continue

        entry = {
            "task_id": task_id,
            "display_id": pk_to_display.get(task_id),
            "project_id": project_id,
            "status": status,
            "text": text or "",
            "before": stored,
            "after": deduped,
            "unresolved": unresolved,
        }
        rewrites.append(entry)
        if unresolved:
            partial.append(entry)

    return {
        "rewrites": rewrites,
        "partial": partial,
        "malformed": malformed,
        "already_correct": already_correct,
        "total_rows": len(rows),
    }


def apply_backfill(conn: sqlite3.Connection, rewrites: list[dict]) -> int:
    updated = 0
    with conn:
        for entry in rewrites:
            conn.execute(
                "UPDATE tasks SET blocked_by = ? WHERE id = ?",
                (json.dumps(entry["after"]), entry["task_id"]),
            )
            updated += 1
    return updated


def print_plan(plan: dict, db_path: Path) -> None:
    print(f"database: {db_path}")
    print(f"rows with blocked_by set: {plan['total_rows']}")
    print(f"  already correct (no write): {plan['already_correct']}")
    print(f"  to rewrite: {len(plan['rewrites'])}")
    print(f"  of those, still carrying unresolvable IDs: {len(plan['partial'])}")
    print(f"  malformed blocked_by (skipped): {len(plan['malformed'])}")

    for entry in plan["malformed"]:
        print(
            f"    MALFORMED #{entry['task_id']} [{entry['project_id']}]: "
            f"{entry['raw']!r}"
        )

    if plan["rewrites"]:
        print()
        for entry in plan["rewrites"]:
            label = (
                f"#{entry['display_id']} (pk {entry['task_id']})"
                if entry["display_id"] is not None
                else f"pk {entry['task_id']}"
            )
            print(f"{label} [{entry['project_id']}/{entry['status']}]")
            print(f"    {entry['text'][:70]}")
            print(f"    before: {entry['before']}")
            print(f"    after:  {entry['after']}")
            if entry["unresolved"]:
                print(
                    f"    LEFT AS-IS (no such task, not guessed): "
                    f"{entry['unresolved']}"
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="report only")
    group.add_argument("--apply", action="store_true", help="write the rows")
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args()

    db_path = args.db or default_db_path()
    if not db_path.exists():
        print(f"database not found: {db_path}", file=sys.stderr)
        return 1

    conn = connect(db_path)
    plan = plan_backfill(conn)
    print_plan(plan, db_path)

    if args.dry_run:
        print("\ndry run — nothing written")
        return 0

    if not plan["rewrites"]:
        print("\nnothing to write")
        return 0

    backup = backup_database(db_path)
    print(f"\nbackup: {backup}")
    updated = apply_backfill(conn, plan["rewrites"])
    print(f"rewrote blocked_by on {updated} row(s)")

    verify = plan_backfill(conn)
    if verify["rewrites"]:
        print(
            f"VERIFY FAILED — {len(verify['rewrites'])} row(s) still need a "
            f"rewrite; investigate before trusting this run",
            file=sys.stderr,
        )
        return 1
    print("verified: no rows left needing a rewrite")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
