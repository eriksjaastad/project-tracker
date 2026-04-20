"""Tests for scripts/db/crr_manifest.py — the CRR classification layer.

The manifest is the foundation of Phase 2 (cr-sqlite sync). Its only job
is to be correct and strict: every live table in the DB must map to
exactly one of {CRR, LOCAL_ONLY, CONTROL_PLANE}. These tests make sure
the classification code catches every way the manifest can drift out of
sync with reality.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

# Add scripts to path (mirrors other test files in this repo).
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from db.crr_manifest import (  # noqa: E402 — path setup must precede import
    ALL_CLASSIFIED,
    CONTROL_PLANE_TABLES,
    CRR_TABLES,
    DuplicateClassificationError,
    LOCAL_ONLY_TABLES,
    UnclassifiedTableError,
    assert_manifest_is_disjoint,
    assert_tables_classified,
    live_table_names,
)


# --- Manifest invariants (no DB needed) -------------------------------


def test_manifest_is_disjoint_as_shipped():
    """The three frozensets must not overlap. If they do, the manifest
    itself is a bug — regardless of what the live DB looks like."""
    assert_manifest_is_disjoint()  # raises on overlap


def test_all_classified_is_union_of_three_sets():
    assert ALL_CLASSIFIED == (
        CRR_TABLES | LOCAL_ONLY_TABLES | CONTROL_PLANE_TABLES
    )


def test_no_empty_name_in_manifest():
    """Defensive: catches a stray empty string sneaking into a set."""
    for name in ALL_CLASSIFIED:
        assert name, "empty table name in manifest"
        assert name.strip() == name, f"whitespace in table name: {name!r}"


# --- live_table_names --------------------------------------------------


def test_live_table_names_excludes_sqlite_internals():
    """sqlite_master and friends should never surface as classifiable
    tables — the query filters them out."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE INDEX idx_tasks_id ON tasks(id)")  # implicit sqlite_autoindex
    live = live_table_names(conn)
    assert live == frozenset({"tasks"})
    # sqlite_master, sqlite_sequence, sqlite_autoindex_* all excluded
    assert not any(n.startswith("sqlite_") for n in live)


def test_live_table_names_empty_db():
    conn = sqlite3.connect(":memory:")
    assert live_table_names(conn) == frozenset()


def test_live_table_names_excludes_crsql_internal_tables():
    """cr-sqlite creates ``crsql_master``, ``crsql_site_id``,
    ``crsql_tracked_peers`` as soon as the extension loads on any
    connection. These are per-machine extension internals — they must
    NOT appear in the live-table set the manifest validates, or every
    boot of pt after the daemon starts would fail
    ``assert_tables_classified``."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE crsql_master (key TEXT, value ANY)")
    conn.execute("CREATE TABLE crsql_site_id (site_id BLOB)")
    conn.execute("CREATE TABLE crsql_tracked_peers (site_id BLOB)")
    live = live_table_names(conn)
    assert live == frozenset({"tasks"})


def test_live_table_names_excludes_per_table_crr_bookkeeping():
    """When ``crsql_as_crr('<name>')`` runs, cr-sqlite creates
    ``<name>__crsql_clock`` and ``<name>__crsql_pks``. These are
    per-table CRR metadata and must not appear in the manifest check —
    the manifest classifies the underlying user table (e.g. ``tasks``),
    not the bookkeeping tables cr-sqlite derived from it."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE tasks__crsql_clock (id INTEGER)")
    conn.execute("CREATE TABLE tasks__crsql_pks (id INTEGER)")
    conn.execute("CREATE TABLE ideas__crsql_clock (id INTEGER)")
    live = live_table_names(conn)
    assert live == frozenset({"tasks"})


def test_live_table_names_does_not_exclude_user_tables_with_crsql_in_name():
    """Defensive: only the exact extension-internal patterns are
    excluded. A user table that happens to have ``crsql`` in its name
    (unusual but legal) must still show up."""
    conn = sqlite3.connect(":memory:")
    # Would match 'crsql_%' if the filter were too greedy? No — leading
    # underscore disqualifies. Still worth pinning.
    conn.execute("CREATE TABLE my_crsql_audit (id INTEGER)")
    live = live_table_names(conn)
    assert "my_crsql_audit" in live


# --- assert_manifest_is_disjoint --------------------------------------


def test_disjoint_detects_overlap(monkeypatch):
    """If a future edit puts the same name in two sets, the assertion
    must catch it."""
    monkeypatch.setattr(
        "db.crr_manifest.CRR_TABLES",
        frozenset({"tasks", "shared"}),
    )
    monkeypatch.setattr(
        "db.crr_manifest.LOCAL_ONLY_TABLES",
        frozenset({"schema_migrations", "shared"}),
    )
    with pytest.raises(DuplicateClassificationError, match="shared"):
        assert_manifest_is_disjoint()


def test_disjoint_detects_crr_control_overlap(monkeypatch):
    monkeypatch.setattr(
        "db.crr_manifest.CRR_TABLES",
        frozenset({"schema_migration_announcements"}),
    )
    monkeypatch.setattr(
        "db.crr_manifest.CONTROL_PLANE_TABLES",
        frozenset({"schema_migration_announcements"}),
    )
    with pytest.raises(DuplicateClassificationError):
        assert_manifest_is_disjoint()


# --- assert_tables_classified -----------------------------------------


def test_classification_passes_on_fully_classified_db():
    """Synthetic DB whose tables are all in the manifest should pass."""
    conn = sqlite3.connect(":memory:")
    for name in ALL_CLASSIFIED:
        conn.execute(f"CREATE TABLE {name} (id INTEGER PRIMARY KEY)")
    # Should not raise.
    assert_tables_classified(conn)


def test_classification_passes_on_subset_of_manifest():
    """The manifest is allowed to include tables not yet created (e.g.
    schema_migrations before the first migration runs). Only a live
    table missing from the manifest should fail."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE ideas (id INTEGER PRIMARY KEY)")
    assert_tables_classified(conn)  # fine — subset of CRR_TABLES


def test_classification_fails_on_unclassified_live_table():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE mystery_new_table (id INTEGER PRIMARY KEY)")
    with pytest.raises(UnclassifiedTableError, match="mystery_new_table"):
        assert_tables_classified(conn)


def test_classification_reports_all_unclassified_tables():
    """If multiple tables are missing from the manifest, the error
    message should list all of them — otherwise the operator fixes one,
    reruns, and hits the next in a death march."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE one_unknown (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE two_unknown (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE three_unknown (id INTEGER PRIMARY KEY)")
    with pytest.raises(UnclassifiedTableError) as exc_info:
        assert_tables_classified(conn)
    msg = str(exc_info.value)
    assert "one_unknown" in msg
    assert "two_unknown" in msg
    assert "three_unknown" in msg


def test_classification_runs_disjoint_check_first(monkeypatch):
    """If both problems exist (overlap + unclassified), overlap should
    surface first — the manifest is a bug upstream of any live-DB
    check."""
    monkeypatch.setattr(
        "db.crr_manifest.CRR_TABLES",
        frozenset({"dup"}),
    )
    monkeypatch.setattr(
        "db.crr_manifest.LOCAL_ONLY_TABLES",
        frozenset({"dup"}),
    )
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE dup (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE mystery (id INTEGER PRIMARY KEY)")
    with pytest.raises(DuplicateClassificationError):
        assert_tables_classified(conn)


# --- Live manifest content (guards against typos and obvious mis-classifications)


def test_schema_migrations_is_local_only():
    """The phantom-migration argument in MAC_MINI_SYNC_PLAN.md §2.1 is
    load-bearing — do not accidentally CRR-ify the local migration
    ledger."""
    assert "schema_migrations" in LOCAL_ONLY_TABLES
    assert "schema_migrations" not in CRR_TABLES
    assert "schema_migrations" not in CONTROL_PLANE_TABLES


def test_schema_migration_announcements_is_control_plane():
    """Gate for pt sync resume — must replicate even while data-plane
    is paused. Classifying it as regular CRR would deadlock the gate."""
    assert "schema_migration_announcements" in CONTROL_PLANE_TABLES
    assert "schema_migration_announcements" not in CRR_TABLES
    assert "schema_migration_announcements" not in LOCAL_ONLY_TABLES


def test_audit_tables_are_local_only():
    """Three-reviewer unanimous decision (Q9). Revisit only via a
    planning round."""
    for name in ("_delete_permissions", "delete_attempt_log", "delete_audit_log"):
        assert name in LOCAL_ONLY_TABLES, f"{name} should be LOCAL_ONLY"


def test_workspace_state_tables_are_crr():
    """Sanity: the obvious shared-workspace tables must be CRR."""
    for name in ("tasks", "ideas", "projects", "task_history"):
        assert name in CRR_TABLES, f"{name} should be CRR"
