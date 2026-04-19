"""Tests for scripts/db/migration_runner.py — Phase 2.1a + 2.2.

The runner is small but load-bearing: it owns the ``schema_migrations``
ledger, and in §2.2 it becomes the one place the CRR-alter wrapper
lives. These tests pin the contract so future changes can't silently
drift away from the four-reviewer plan:

- discovery: tolerant of non-migration files, strict about malformed
  migrations that *claim* to be migrations, strict about CRR-table
  declarations that don't line up with ``crr_manifest.CRR_TABLES``;
- applied-versions: returns an empty set before the bootstrap
  migration runs (so the bootstrap isn't mistaken for already-applied);
- apply_migration: runs inside a transaction, records the ledger row
  atomically with the DDL, and rolls the whole thing back on failure
  — including the ledger insert, so the runner will retry the failed
  migration on the next call;
- apply_all: idempotent (re-running is a no-op), applies pending
  migrations in version order, stops at the first failure.

Tests write their own synthetic migration files into a tmp directory so
nothing here depends on the real ``scripts/db/migrations/`` tree.
"""

from __future__ import annotations

import sqlite3
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from db.migration_runner import (  # noqa: E402 — path setup precedes import
    MigrationError,
    applied_versions,
    apply_all,
    apply_migration,
    discover_migrations,
    unapplied_migrations,
)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _write(path: Path, body: str) -> None:
    path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")


def _valid_migration(version: int, name: str) -> str:
    """Minimal valid migration body — no CRR tables, trivial DDL."""
    return f"""
    from __future__ import annotations

    import sqlite3

    CRR_TABLES = frozenset()

    def up(conn: sqlite3.Connection) -> None:
        conn.execute(
            "CREATE TABLE {name}_{version:03d} (id INTEGER PRIMARY KEY)"
        )
    """


def _ledger_conn() -> sqlite3.Connection:
    """Fresh in-memory DB with the ``schema_migrations`` table pre-created."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, "
        "name TEXT NOT NULL, applied_at TEXT NOT NULL)"
    )
    return conn


# ---------------------------------------------------------------------
# discover_migrations
# ---------------------------------------------------------------------


def test_discover_empty_dir(tmp_path: Path) -> None:
    assert discover_migrations(tmp_path) == []


def test_discover_returns_migrations_in_version_order(tmp_path: Path) -> None:
    _write(tmp_path / "010_late.py", _valid_migration(10, "late"))
    _write(tmp_path / "002_early.py", _valid_migration(2, "early"))
    _write(tmp_path / "005_middle.py", _valid_migration(5, "middle"))

    migrations = discover_migrations(tmp_path)
    assert [m.version for m in migrations] == [2, 5, 10]
    assert [m.name for m in migrations] == ["early", "middle", "late"]


def test_discover_ignores_non_matching_filenames(tmp_path: Path) -> None:
    """__init__.py, dotfiles, editor swap files: silently ignored."""
    (tmp_path / "__init__.py").write_text("# package marker\n")
    (tmp_path / ".DS_Store").write_text("")
    (tmp_path / "README.md").write_text("# notes\n")
    (tmp_path / "002_real.py.swp").write_text("editor swap\n")

    _write(tmp_path / "001_real.py", _valid_migration(1, "real"))

    migrations = discover_migrations(tmp_path)
    assert [m.version for m in migrations] == [1]


def test_discover_rejects_duplicate_versions(tmp_path: Path) -> None:
    _write(tmp_path / "003_one.py", _valid_migration(3, "one"))
    _write(tmp_path / "003_two.py", _valid_migration(3, "two"))

    with pytest.raises(MigrationError, match="Duplicate migration version 003"):
        discover_migrations(tmp_path)


def test_discover_skips_file_without_up(tmp_path: Path, capsys) -> None:
    """Matches ``NNN_name.py`` but has no ``up`` — legacy/deprecated
    artifact. Skip with a stderr warning, don't raise."""
    _write(
        tmp_path / "001_legacy.py",
        """
        CRR_TABLES = frozenset()
        # No up() — this is the shape of the deprecated 001 script.
        """,
    )
    _write(tmp_path / "002_real.py", _valid_migration(2, "real"))

    migrations = discover_migrations(tmp_path)
    assert [m.version for m in migrations] == [2]

    err = capsys.readouterr().err
    assert "001_legacy.py" in err
    assert "up" in err


def test_discover_skips_file_without_crr_tables(tmp_path: Path, capsys) -> None:
    _write(
        tmp_path / "001_no_decl.py",
        """
        def up(conn):
            pass
        """,
    )
    migrations = discover_migrations(tmp_path)
    assert migrations == []
    assert "CRR_TABLES" in capsys.readouterr().err


def test_discover_skips_file_with_non_frozenset_crr_tables(
    tmp_path: Path, capsys
) -> None:
    """A set (not frozenset) is a common accident — runner must catch it."""
    _write(
        tmp_path / "001_wrong_type.py",
        """
        CRR_TABLES = {"tasks"}  # set literal, not frozenset

        def up(conn):
            pass
        """,
    )
    migrations = discover_migrations(tmp_path)
    assert migrations == []
    assert "frozenset" in capsys.readouterr().err


def test_discover_skips_file_declaring_unknown_crr_table(
    tmp_path: Path, capsys
) -> None:
    """CRR_TABLES entries must match crr_manifest.CRR_TABLES — prevents
    typos silently altering the wrong table."""
    _write(
        tmp_path / "001_typo.py",
        """
        CRR_TABLES = frozenset({"taskz"})  # typo

        def up(conn):
            pass
        """,
    )
    migrations = discover_migrations(tmp_path)
    assert migrations == []
    err = capsys.readouterr().err
    assert "taskz" in err


def test_discover_accepts_empty_crr_tables(tmp_path: Path) -> None:
    """CREATE-only migrations legitimately have empty CRR_TABLES."""
    _write(tmp_path / "001_create_only.py", _valid_migration(1, "create_only"))
    migrations = discover_migrations(tmp_path)
    assert len(migrations) == 1
    assert migrations[0].crr_tables == frozenset()


def test_discover_accepts_known_crr_table(tmp_path: Path) -> None:
    """A migration that alters a real CRR-classified table should load."""
    _write(
        tmp_path / "003_alter_tasks.py",
        """
        from __future__ import annotations
        import sqlite3

        CRR_TABLES = frozenset({"tasks"})

        def up(conn: sqlite3.Connection) -> None:
            conn.execute("ALTER TABLE tasks ADD COLUMN new_col TEXT")
        """,
    )
    migrations = discover_migrations(tmp_path)
    assert [m.version for m in migrations] == [3]
    assert migrations[0].crr_tables == frozenset({"tasks"})


# ---------------------------------------------------------------------
# applied_versions / unapplied_migrations
# ---------------------------------------------------------------------


def test_applied_versions_is_empty_when_ledger_missing() -> None:
    """Before the bootstrap migration runs, the ledger table doesn't
    exist. Returning an empty set is what makes the bootstrap migration
    runnable — otherwise the runner couldn't decide whether to apply
    the migration that creates its own ledger."""
    conn = sqlite3.connect(":memory:")
    assert applied_versions(conn) == set()


def test_applied_versions_reflects_ledger_rows() -> None:
    conn = _ledger_conn()
    conn.execute(
        "INSERT INTO schema_migrations (version, name, applied_at) "
        "VALUES (2, 'a', '2026-01-01T00:00:00+00:00'), "
        "       (5, 'b', '2026-01-02T00:00:00+00:00')"
    )
    assert applied_versions(conn) == {2, 5}


def test_unapplied_filters_out_recorded_versions(tmp_path: Path) -> None:
    _write(tmp_path / "001_a.py", _valid_migration(1, "a"))
    _write(tmp_path / "002_b.py", _valid_migration(2, "b"))
    _write(tmp_path / "003_c.py", _valid_migration(3, "c"))
    migrations = discover_migrations(tmp_path)

    conn = _ledger_conn()
    conn.execute(
        "INSERT INTO schema_migrations (version, name, applied_at) "
        "VALUES (1, 'a', '2026-01-01T00:00:00+00:00')"
    )
    pending = unapplied_migrations(conn, migrations)
    assert [m.version for m in pending] == [2, 3]


# ---------------------------------------------------------------------
# apply_migration
# ---------------------------------------------------------------------


def test_apply_migration_runs_up_and_records_ledger_row(tmp_path: Path) -> None:
    _write(tmp_path / "001_bootstrap.py", _valid_migration(1, "bootstrap"))
    [migration] = discover_migrations(tmp_path)

    conn = _ledger_conn()
    apply_migration(conn, migration)

    assert applied_versions(conn) == {1}
    row = conn.execute(
        "SELECT version, name FROM schema_migrations WHERE version = 1"
    ).fetchone()
    assert row == (1, "bootstrap")

    # The migration's own DDL also ran.
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='bootstrap_001'"
    )
    assert cur.fetchone() is not None


def test_apply_migration_creates_bootstrap_ledger_in_same_transaction(
    tmp_path: Path,
) -> None:
    """The real ``002_add_sync_ledgers`` migration creates the
    ``schema_migrations`` table, then the runner inserts into it in the
    same transaction. This exercises that path with a synthetic
    bootstrap migration — if the commit order is wrong (insert before
    CREATE), the test fails."""
    _write(
        tmp_path / "002_bootstrap_ledger.py",
        """
        from __future__ import annotations
        import sqlite3

        CRR_TABLES = frozenset()

        def up(conn: sqlite3.Connection) -> None:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, "
                "name TEXT NOT NULL, "
                "applied_at TEXT NOT NULL)"
            )
        """,
    )
    [migration] = discover_migrations(tmp_path)

    conn = sqlite3.connect(":memory:")  # ledger does NOT exist yet
    assert applied_versions(conn) == set()

    apply_migration(conn, migration)
    assert applied_versions(conn) == {2}


def test_apply_migration_rolls_back_ddl_and_ledger_on_failure(
    tmp_path: Path,
) -> None:
    """Runner guarantees atomicity: a failing ``up`` leaves no trace —
    not the partial DDL, not a ledger row. Re-running must retry."""
    _write(
        tmp_path / "001_fails_halfway.py",
        """
        from __future__ import annotations
        import sqlite3

        CRR_TABLES = frozenset()

        def up(conn: sqlite3.Connection) -> None:
            conn.execute("CREATE TABLE thing_a (id INTEGER PRIMARY KEY)")
            # Fails here — ROLLBACK must unwind thing_a too.
            conn.execute("INVALID SQL STATEMENT")
        """,
    )
    [migration] = discover_migrations(tmp_path)

    conn = _ledger_conn()
    with pytest.raises(sqlite3.OperationalError):
        apply_migration(conn, migration)

    # Ledger is empty — migration did NOT record itself.
    assert applied_versions(conn) == set()

    # DDL was unwound — thing_a does not exist.
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='thing_a'"
    )
    assert cur.fetchone() is None


def test_apply_migration_is_noop_calls_crsql_when_extension_absent(
    tmp_path: Path,
) -> None:
    """cr-sqlite isn't loaded in these tests (stock sqlite3). A migration
    that declares CRR_TABLES must still apply cleanly — the runner just
    skips the ``crsql_begin_alter`` / ``crsql_commit_alter`` calls. This
    is the pre-Phase-2.2 behavior we rely on to ship the runner before
    cr-sqlite lands."""
    # Create a dummy 'tasks' table so the DDL the migration runs can
    # target a real table. (In production this table is classified CRR
    # in the manifest, so the declaration is valid.)
    _write(
        tmp_path / "003_add_column_to_tasks.py",
        """
        from __future__ import annotations
        import sqlite3

        CRR_TABLES = frozenset({"tasks"})

        def up(conn: sqlite3.Connection) -> None:
            conn.execute(
                "ALTER TABLE tasks ADD COLUMN sync_trial_col TEXT"
            )
        """,
    )
    [migration] = discover_migrations(tmp_path)

    conn = _ledger_conn()
    conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY)")

    # Should NOT raise even though crsql_begin_alter doesn't exist:
    # the runner probes cr-sqlite once and skips the calls when absent.
    apply_migration(conn, migration)
    assert applied_versions(conn) == {3}

    # The column was actually added.
    cols = [r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()]
    assert "sync_trial_col" in cols


# ---------------------------------------------------------------------
# apply_all
# ---------------------------------------------------------------------


def test_apply_all_applies_pending_in_order(tmp_path: Path) -> None:
    _write(tmp_path / "001_a.py", _valid_migration(1, "a"))
    _write(tmp_path / "002_b.py", _valid_migration(2, "b"))
    _write(tmp_path / "003_c.py", _valid_migration(3, "c"))

    conn = _ledger_conn()
    applied = apply_all(conn, tmp_path)

    assert [m.version for m in applied] == [1, 2, 3]
    assert applied_versions(conn) == {1, 2, 3}


def test_apply_all_is_idempotent(tmp_path: Path) -> None:
    _write(tmp_path / "001_a.py", _valid_migration(1, "a"))
    _write(tmp_path / "002_b.py", _valid_migration(2, "b"))

    conn = _ledger_conn()
    first = apply_all(conn, tmp_path)
    second = apply_all(conn, tmp_path)

    assert [m.version for m in first] == [1, 2]
    assert second == []  # nothing left to apply


def test_apply_all_stops_at_first_failure_and_preserves_prior_state(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "001_ok.py", _valid_migration(1, "ok"))
    _write(
        tmp_path / "002_broken.py",
        """
        from __future__ import annotations
        import sqlite3

        CRR_TABLES = frozenset()

        def up(conn: sqlite3.Connection) -> None:
            conn.execute("CREATE TABLE before_error (id INTEGER PRIMARY KEY)")
            conn.execute("NOT VALID SQL")
        """,
    )
    _write(tmp_path / "003_never_runs.py", _valid_migration(3, "never_runs"))

    conn = _ledger_conn()
    with pytest.raises(sqlite3.OperationalError):
        apply_all(conn, tmp_path)

    # 001 committed; 002 rolled back; 003 never attempted.
    assert applied_versions(conn) == {1}
    cur = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name IN ('before_error', 'never_runs_003', 'ok_001')"
    )
    names = {r[0] for r in cur.fetchall()}
    assert "ok_001" in names
    assert "before_error" not in names
    assert "never_runs_003" not in names


# ---------------------------------------------------------------------
# Real 002 migration
# ---------------------------------------------------------------------


def test_real_002_migration_creates_both_ledgers() -> None:
    """Exercise the actual migration file this PR ships — not a mock."""
    migrations_dir = Path(__file__).parent.parent / "scripts" / "db" / "migrations"
    real_002 = next(
        m for m in discover_migrations(migrations_dir) if m.version == 2
    )
    assert real_002.name == "add_sync_ledgers"
    assert real_002.crr_tables == frozenset()

    conn = sqlite3.connect(":memory:")  # no ledger yet — cold start
    apply_migration(conn, real_002)

    # Both tables exist.
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "schema_migrations" in tables
    assert "schema_migration_announcements" in tables

    # Ledger recorded this migration as applied.
    assert applied_versions(conn) == {2}
