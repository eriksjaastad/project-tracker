#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["libsql"]
# ///
"""
One-time migration: dump all data from Turso → local SQLite.

Usage:
    doppler run -p openclaw -c dev -- uv run scripts/turso_to_local.py

    Or with env vars set directly:
    TURSO_KANBAN_URL=... TURSO_KANBAN_TOKEN=... uv run scripts/turso_to_local.py

    Dry run (shows counts, writes nothing):
    doppler run -p openclaw -c dev -- uv run scripts/turso_to_local.py --dry-run

This script:
1. Connects to Turso and reads all rows from every table
2. Backs up the existing local tracker.db
3. Writes all Turso data into local SQLite (INSERT OR REPLACE)
4. Verifies row counts match

Safe to run multiple times — uses INSERT OR REPLACE.
"""

import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
LOCAL_DB = PROJECT_ROOT / "data" / "tracker.db"
BACKUP_DIR = PROJECT_ROOT / "data" / "backups"

# Tables to migrate (in dependency order for foreign keys)
TABLES = [
    "projects",
    "tasks",
    "calendar_events",
]


def connect_turso():
    """Connect to Turso using env vars."""
    import libsql
    url = os.environ.get("TURSO_KANBAN_URL", "")
    token = os.environ.get("TURSO_KANBAN_TOKEN", "")
    if not url or not token:
        print("ERROR: TURSO_KANBAN_URL and TURSO_KANBAN_TOKEN must be set.")
        print("Run with: doppler run -p openclaw -c dev -- uv run scripts/turso_to_local.py")
        sys.exit(1)
    return libsql.connect(url, auth_token=token)


def get_table_columns(conn, table: str) -> list[str]:
    """Get column names for a table."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cursor.fetchall()]


def dump_table(turso_conn, table: str) -> tuple[list[str], list[tuple]]:
    """Read all rows from a Turso table. Returns (columns, rows)."""
    columns = get_table_columns(turso_conn, table)
    if not columns:
        return [], []
    cursor = turso_conn.execute(f"SELECT * FROM {table}")
    rows = cursor.fetchall()
    return columns, rows


def main():
    dry_run = "--dry-run" in sys.argv

    print("=" * 60)
    print("Turso → Local SQLite Migration")
    print("=" * 60)

    if dry_run:
        print("DRY RUN — no data will be written\n")

    # Connect to Turso
    print("Connecting to Turso...")
    turso = connect_turso()
    print("Connected.\n")

    # Read all data from Turso
    turso_data = {}
    for table in TABLES:
        columns, rows = dump_table(turso, table)
        turso_data[table] = (columns, rows)
        print(f"  {table}: {len(rows)} rows, {len(columns)} columns")

    print()

    if dry_run:
        print("DRY RUN complete. No changes made.")
        return

    # Backup existing local DB
    if LOCAL_DB.exists() and LOCAL_DB.stat().st_size > 0:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = BACKUP_DIR / f"tracker_pre_turso_migration_{timestamp}.db"
        shutil.copy2(LOCAL_DB, backup_path)
        print(f"Backed up local DB to: {backup_path}")
        print(f"  (size: {backup_path.stat().st_size:,} bytes)\n")

    # Write to local SQLite
    print("Writing to local SQLite...")
    LOCAL_DB.parent.mkdir(parents=True, exist_ok=True)

    local = sqlite3.connect(str(LOCAL_DB))
    local.execute("PRAGMA foreign_keys = OFF")  # Temporarily disable for bulk insert
    local.execute("PRAGMA journal_mode = WAL")

    # Ensure schema exists (run the schema setup)
    sys.path.insert(0, str(SCRIPT_DIR))
    from db.schema import ensure_schema
    cursor = local.cursor()
    ensure_schema(cursor)
    local.commit()

    for table in TABLES:
        columns, rows = turso_data[table]
        if not columns:
            print(f"  {table}: skipped (no columns found in Turso)")
            continue

        # Check which columns exist in local schema
        local_columns = [row[1] for row in local.execute(f"PRAGMA table_info({table})").fetchall()]
        # Only insert columns that exist in both
        common_columns = [c for c in columns if c in local_columns]
        if not common_columns:
            print(f"  {table}: skipped (no common columns)")
            continue

        # Map Turso rows to only common columns
        col_indices = [columns.index(c) for c in common_columns]
        placeholders = ",".join(["?"] * len(common_columns))
        col_names = ",".join(common_columns)
        sql = f"INSERT OR REPLACE INTO {table} ({col_names}) VALUES ({placeholders})"

        mapped_rows = [tuple(row[i] for i in col_indices) for row in rows]
        local.executemany(sql, mapped_rows)
        print(f"  {table}: wrote {len(mapped_rows)} rows")

    local.execute("PRAGMA foreign_keys = ON")
    local.commit()
    local.close()
    print()

    # Verify
    print("Verifying...")
    verify = sqlite3.connect(str(LOCAL_DB))
    for table in TABLES:
        _, turso_rows = turso_data[table]
        local_count = verify.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        status = "OK" if local_count >= len(turso_rows) else "MISMATCH"
        print(f"  {table}: Turso={len(turso_rows)}, Local={local_count} [{status}]")
    verify.close()

    print(f"\nMigration complete. Local DB: {LOCAL_DB}")
    print(f"Size: {LOCAL_DB.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
