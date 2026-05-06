"""Create handoffs table for structured unfinished-work and non-PR records.

Agents write a handoff record when they exit without opening a PR (Phase D
of the locked-project hygiene workflow). The record captures enough context
for the resuming agent to continue without re-reading the full session.

Classification: LOCAL_ONLY — handoffs are machine-scoped session artifacts.
They reference tasks (CRR) by card_id but are never synced across machines.
"""

from __future__ import annotations

import sqlite3

CRR_TABLES: frozenset[str] = frozenset()


def up(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS handoffs (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id                  INTEGER NOT NULL,
            project                  TEXT,
            branch                   TEXT,
            file_list                TEXT NOT NULL DEFAULT '[]',
            intent                   TEXT NOT NULL,
            current_status           TEXT NOT NULL,
            next_command             TEXT NOT NULL,
            discard_or_preserve_guidance TEXT NOT NULL,
            record_type              TEXT NOT NULL DEFAULT 'unfinished'
                                         CHECK(record_type IN ('unfinished', 'pr_exempt')),
            pr_exempt_reason         TEXT,
            pr_exempt_disposition    TEXT
                                         CHECK(pr_exempt_disposition IN
                                               ('reverted', 'discarded',
                                                'left_as_artifact', 'merged_elsewhere',
                                                NULL)),
            pr_exempt_approver       TEXT,
            created_at               TEXT NOT NULL,
            created_by               TEXT,
            resolved_at              TEXT,
            resolved_note            TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_handoffs_card_id
        ON handoffs (card_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_handoffs_project
        ON handoffs (project)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_handoffs_resolved_at
        ON handoffs (resolved_at)
        WHERE resolved_at IS NULL
    """)
