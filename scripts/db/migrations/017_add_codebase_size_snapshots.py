"""Add the codebase_size_snapshots table for #8083.

Dated runs measuring how much code and documentation each repo under the
projects root carries, plus the single imported 2026-10-08 baseline run, so
`pt size` can score how much leaner a repo has become.

Classification: LOCAL_ONLY. Snapshots are measured from the laptop's own
checkouts; the Mini has no use for them and replicating them would only create
conflicting copies. The same DDL lives in schema.py for fresh databases;
IF NOT EXISTS makes this migration safe after either creation path.

The table is append-only: triggers abort any UPDATE or DELETE, so a stored
measurement can never be lost or altered. Each run is one complete scan under
its own run_id. The baseline is immutable at the database level: baseline
rows must be dated 2026-10-08, a trigger refuses any baseline row from a
second run, and the partial unique index allows one baseline row per project.
"""

from __future__ import annotations

import sqlite3

CRR_TABLES: frozenset[str] = frozenset()

DDL = (
    """
    CREATE TABLE IF NOT EXISTS codebase_size_snapshots (
        id            INTEGER PRIMARY KEY NOT NULL,
        run_id        TEXT NOT NULL,
        kind          TEXT NOT NULL CHECK(kind IN ('baseline', 'scan')),
        snapshot_date TEXT NOT NULL CHECK(kind <> 'baseline' OR snapshot_date = '2026-10-08'),
        project       TEXT NOT NULL,
        code_lines    INTEGER NOT NULL,
        test_lines    INTEGER NOT NULL,
        doc_files     INTEGER NOT NULL,
        doc_lines     INTEGER NOT NULL,
        last_commit   TEXT,
        commits_90d   INTEGER,
        scanned_at    TEXT NOT NULL,
        UNIQUE(run_id, project)
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_codebase_size_one_baseline
    ON codebase_size_snapshots(project) WHERE kind = 'baseline'
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_codebase_size_kind_id
    ON codebase_size_snapshots(kind, id)
    """,
    """
    CREATE TRIGGER IF NOT EXISTS codebase_size_one_baseline_run
    BEFORE INSERT ON codebase_size_snapshots
    WHEN NEW.kind = 'baseline' AND EXISTS (
        SELECT 1 FROM codebase_size_snapshots
        WHERE kind = 'baseline' AND run_id <> NEW.run_id
    )
    BEGIN SELECT RAISE(ABORT, 'the codebase size baseline is immutable'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS codebase_size_snapshots_no_update
    BEFORE UPDATE ON codebase_size_snapshots
    BEGIN SELECT RAISE(ABORT, 'codebase_size_snapshots is append-only'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS codebase_size_snapshots_no_delete
    BEFORE DELETE ON codebase_size_snapshots
    BEGIN SELECT RAISE(ABORT, 'codebase_size_snapshots is append-only'); END
    """,
)


def up(conn: sqlite3.Connection) -> None:
    for statement in DDL:
        conn.execute(statement)
