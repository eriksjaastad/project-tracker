"""Add the codebase_size_snapshots table for #8083.

Dated snapshots of how much code and documentation each repo under the
projects root carries, plus one imported baseline per repo, so `pt size` can
score how much leaner a repo has become.

Classification: LOCAL_ONLY. Snapshots are measured from the laptop's own
checkouts; the Mini has no use for them and replicating them would only create
conflicting copies. The same DDL lives in schema.py for fresh databases;
CREATE IF NOT EXISTS makes this migration safe after either creation path.
`kind` is part of the unique key so a scan taken on the baseline's date can
never overwrite the baseline.
"""

from __future__ import annotations

import sqlite3

CRR_TABLES: frozenset[str] = frozenset()


def up(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS codebase_size_snapshots (
            id            INTEGER PRIMARY KEY NOT NULL,
            snapshot_date TEXT NOT NULL,
            kind          TEXT NOT NULL CHECK(kind IN ('baseline', 'scan')),
            project       TEXT NOT NULL,
            code_lines    INTEGER NOT NULL,
            test_lines    INTEGER NOT NULL,
            doc_files     INTEGER NOT NULL,
            doc_lines     INTEGER NOT NULL,
            last_commit   TEXT,
            commits_90d   INTEGER,
            scanned_at    TEXT NOT NULL,
            UNIQUE(snapshot_date, kind, project)
        )
    """)
