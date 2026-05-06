"""
CRR (Conflict-Resolved Replica) table classification manifest.

Every live table in tracker.db must be classified into exactly one of three
sets BEFORE any cr-sqlite sync code runs. The classifier runs at DB init
and refuses to start if the live schema doesn't match.

Classifications
---------------
- CRR_TABLES              Replicate across machines via cr-sqlite CRR.
                          Shared workspace state — tasks, projects, calendar,
                          etc. Conflicts are merged via CRDT semantics.
- LOCAL_ONLY_TABLES       Never leave the machine. Per-machine bookkeeping,
                          audit logs, migration ledger, runtime state.
- CONTROL_PLANE_TABLES    Always-on sync (never paused, even when the
                          data-plane is halted for a migration). Used for
                          coordination primitives like migration
                          announcements.

The three-set classification is locked in MAC_MINI_SYNC_PLAN.md §2.1. It
was reached via four-reviewer sign-off (Architect / Mac Mini Claude /
AI Memory FM / Project Tracker FM) — don't reclassify without a planning
round.

Why local-only for audit tables, schema_migrations, and schema_version:
- schema_migrations: if CRR, applying a migration on machine A would
  replicate the row to machine B *before* B's runner ran the DDL. B's
  runner would see the row, skip the DDL, schema drift. Phantom-migration
  risk. The CRR counterpart is `schema_migration_announcements` — written
  AFTER a successful local apply, purely as a cross-machine gate.
- _delete_permissions: execution-time policy. Replicating it silently
  widens the permission grant surface on the peer.
- delete_attempt_log / delete_audit_log: audit logs prove what happened
  where; replication adds a failure mode audit logs shouldn't have.
- cron_jobs / loop_executions: per-machine scheduling and execution
  history; machines run different schedules.
- _metadata / schema_version: per-machine DB bookkeeping.

Why always-on for schema_migration_announcements:
- Paused data-plane + paused announcements would deadlock `pt sync
  resume`, which blocks waiting for the peer's announcement row. The
  announcement table needs to keep crossing machines even during a
  migration window. See MAC_MINI_SYNC_PLAN.md §2.1 for the full
  chicken-and-egg resolution.

Adding a new table
------------------
When you create a new table in schema.py:
1. Classify it (CRR vs LOCAL_ONLY vs CONTROL_PLANE).
2. Add its name to the appropriate frozenset below.
3. The boot-time assertion in `assert_tables_classified()` will fail
   loudly if you forget — no silent drift.
"""

from __future__ import annotations

import sqlite3


# Tables that replicate across machines via cr-sqlite CRR.
CRR_TABLES: frozenset[str] = frozenset({
    "tasks",
    "ideas",
    "task_history",
    "task_attachments",
    "projects",
    "project_info",
    "ai_agents",
    "service_dependencies",
    "calendar_events",
    "calendar_event_tasks",
})

# Tables that stay on the local machine — never synced, ever.
LOCAL_ONLY_TABLES: frozenset[str] = frozenset({
    "schema_migrations",      # local source of truth for applied migrations
    "schema_version",         # per-machine DB version stamp
    "_metadata",              # runtime bookkeeping
    "_delete_permissions",    # execution-time policy — don't widen via sync
    "delete_attempt_log",     # machine-scoped audit stream
    "delete_audit_log",       # machine-scoped audit stream
    "cron_jobs",              # per-machine scheduling
    "loop_executions",        # per-machine execution history
    "task_display_ids",       # per-machine sequential display IDs for Snowflake PKs
    "handoffs",               # session-scoped unfinished-work / non-PR records (Phase D)
})

# Tables that sync even when the data-plane is paused. Used for sync
# coordination primitives that can't stop during a migration.
CONTROL_PLANE_TABLES: frozenset[str] = frozenset({
    "schema_migration_announcements",
})

ALL_CLASSIFIED: frozenset[str] = (
    CRR_TABLES | LOCAL_ONLY_TABLES | CONTROL_PLANE_TABLES
)


class UnclassifiedTableError(RuntimeError):
    """Raised when a live table has no CRR classification.

    The sync architecture assumes every table is explicitly classified
    as CRR, LOCAL_ONLY, or CONTROL_PLANE. Unclassified tables would be
    silently excluded from sync — or worse, silently included via an
    unintended default. Refuse to start.
    """


class DuplicateClassificationError(RuntimeError):
    """Raised when a table name appears in more than one set.

    This is a manifest authoring bug; the three sets are meant to be
    disjoint. Keep it strict so ambiguity never enters the runtime path.
    """


def live_table_names(conn: sqlite3.Connection) -> frozenset[str]:
    """Return every user-facing table in the database.

    Excludes:
      - SQLite's own internals (``sqlite_master``, ``sqlite_sequence``,
        ``sqlite_autoindex_*`` — anything matching ``sqlite_%``).
      - cr-sqlite's DB-scoped bookkeeping (``crsql_master``,
        ``crsql_site_id``, ``crsql_tracked_peers`` — anything matching
        ``crsql_%``). These are created as soon as cr-sqlite is loaded
        on *any* connection and are per-machine extension state; they
        have no business being classified in the CRR manifest. The
        ``crsql_%`` prefix is a namespace claim on cr-sqlite's part —
        don't create user tables starting with ``crsql_`` or they
        will be silently excluded from manifest validation. This is
        forward-compatible with cr-sqlite adding new internal tables
        in future versions (v0.17, v0.18, …) without requiring a
        manifest-code change each time.
      - cr-sqlite's per-table CRR bookkeeping
        (``<name>__crsql_clock``, ``<name>__crsql_pks`` — anything
        containing ``__crsql_``). These appear as soon as
        ``crsql_as_crr(<name>)`` is called on the user table; we
        classify only the underlying user table.
      - §2.4 trial scratch tables (anything matching ``_crr_test_%``).
        The Phase 2.4 cross-machine runbook creates ephemeral tables
        like ``_crr_test_scratch`` on the live DB to probe cr-sqlite
        behavior without touching real user data. They exist only for
        the duration of the trial and are dropped in teardown (§2.4.I).
        Claiming the ``_crr_test_%`` prefix keeps ``pt`` commands
        (which go through ``DatabaseManager`` → ``create_database`` →
        ``assert_tables_classified``) working during the trial —
        otherwise every ``pt sync pause/resume`` call in the runbook
        would raise ``UnclassifiedTableError`` mid-test. Don't name
        real application tables with this prefix.

    The manifest assertion then validates the remaining set — the
    actual user/application tables — against CRR / LOCAL_ONLY /
    CONTROL_PLANE classification.
    """
    cur = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' "
        "AND name NOT LIKE 'crsql_%' "
        "AND name NOT LIKE '%\\_\\_crsql\\_%' ESCAPE '\\' "
        "AND name NOT LIKE '\\_crr\\_test\\_%' ESCAPE '\\' "
        "ORDER BY name"
    )
    return frozenset(row[0] for row in cur.fetchall())


def assert_manifest_is_disjoint() -> None:
    """Fail fast if the three frozensets overlap. Called at module load
    implicitly by assert_tables_classified()."""
    crr_vs_local = CRR_TABLES & LOCAL_ONLY_TABLES
    crr_vs_control = CRR_TABLES & CONTROL_PLANE_TABLES
    local_vs_control = LOCAL_ONLY_TABLES & CONTROL_PLANE_TABLES
    overlaps = crr_vs_local | crr_vs_control | local_vs_control
    if overlaps:
        raise DuplicateClassificationError(
            "Table(s) classified in more than one set: "
            f"{sorted(overlaps)}. Each table must appear in exactly one of "
            "CRR_TABLES, LOCAL_ONLY_TABLES, or CONTROL_PLANE_TABLES."
        )


def assert_tables_classified(conn: sqlite3.Connection) -> None:
    """
    Fail fast if any live table in the database is not classified.

    Runs at DB init. The sync layer (when cr-sqlite lands) iterates
    CRR_TABLES to call crsql_as_crr(); an unclassified live table
    would either be silently excluded or silently included via a default.
    Neither is acceptable.

    Raises
    ------
    DuplicateClassificationError
        If the manifest itself has overlapping sets (authoring bug).
    UnclassifiedTableError
        If a live table is not in any set (update the manifest).
    """
    assert_manifest_is_disjoint()

    live = live_table_names(conn)
    unclassified = live - ALL_CLASSIFIED
    if unclassified:
        raise UnclassifiedTableError(
            "Live tables present in tracker.db but not classified in "
            "crr_manifest.py: "
            f"{sorted(unclassified)}. Add each to CRR_TABLES, "
            "LOCAL_ONLY_TABLES, or CONTROL_PLANE_TABLES — see the module "
            "docstring for the classification rules."
        )
