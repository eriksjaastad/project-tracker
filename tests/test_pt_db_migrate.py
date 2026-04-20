"""Integration tests for the Phase 2 PR #3a wiring.

These tests exercise the three things PR #3a adds on top of the
Phase 2 PR #2 runner:

1. ``pt db migrate`` CLI — applies pending migrations, reports what
   was applied, idempotent, refuses under Turso.
2. ``_warn_unapplied_migrations`` — stderr warning on ``pt`` startup
   when migrations are pending, silent after they're applied, never
   raises.
3. ``scripts/db/schema.create_database`` — calls
   ``assert_tables_classified`` after ``ensure_schema``, so an
   unclassified table causes a hard stop at DB init.

Unit-level coverage of the runner itself lives in
``tests/test_migration_runner.py``. This file is the wiring layer.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

# noqa: E402 — sys.path setup must precede these imports
from db.crr_manifest import UnclassifiedTableError  # noqa: E402
from pt import cli, _warn_unapplied_migrations  # noqa: E402


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


MIGRATIONS_DIR = (
    Path(__file__).parent.parent / "scripts" / "db" / "migrations"
)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty sqlite file at a tmp path, pointed at via PT_DB_PATH.

    Stays out of the real ``data/tracker.db`` and bypasses the
    fresh-DB safety check via PT_ALLOW_FRESH_DB=1 (the same escape
    hatch Mini uses in its ~/.zshrc).
    """
    db_path = tmp_path / "tracker.db"
    db_path.touch()
    monkeypatch.setenv("PT_DB_PATH", str(db_path))
    monkeypatch.setenv("PT_ALLOW_FRESH_DB", "1")
    monkeypatch.setenv("PT_NO_BANNER", "1")
    monkeypatch.setenv("PT_SUPPRESS_MIGRATION_WARNING", "1")
    return db_path


# ---------------------------------------------------------------------
# pt db migrate CLI
# ---------------------------------------------------------------------


def test_pt_db_migrate_applies_pending_and_reports(
    runner: CliRunner, fresh_db: Path
) -> None:
    result = runner.invoke(cli, ["db", "migrate"])
    assert result.exit_code == 0, result.output
    assert "002_add_sync_ledgers" in result.output
    assert "003_crr_pk_not_null" in result.output
    assert "applied 2 migration" in result.output

    conn = sqlite3.connect(fresh_db)
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "schema_migrations" in tables
    assert "schema_migration_announcements" in tables
    conn.close()


def test_pt_db_migrate_is_idempotent(
    runner: CliRunner, fresh_db: Path
) -> None:
    first = runner.invoke(cli, ["db", "migrate"])
    second = runner.invoke(cli, ["db", "migrate"])
    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert "no pending migrations" in second.output


def test_pt_db_migrate_refuses_under_turso(
    runner: CliRunner, fresh_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The local runner must not operate against a Turso-backed DB.
    Flipping the module-level flag simulates the deployment switch in
    ``~/projects/.turso-config.json``."""
    monkeypatch.setattr("pt._USE_TURSO", True)
    result = runner.invoke(cli, ["db", "migrate"])
    assert result.exit_code == 2
    assert "Turso" in result.output


# ---------------------------------------------------------------------
# _warn_unapplied_migrations
# ---------------------------------------------------------------------


def test_warn_unapplied_fires_when_pending(
    capsys: pytest.CaptureFixture[str], fresh_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PT_SUPPRESS_MIGRATION_WARNING", raising=False)
    _warn_unapplied_migrations()
    err = capsys.readouterr().err
    assert "pending migration" in err
    assert "002_add_sync_ledgers" in err
    assert "pt db migrate" in err


def test_warn_unapplied_silent_after_apply(
    runner: CliRunner, capsys: pytest.CaptureFixture[str],
    fresh_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner.invoke(cli, ["db", "migrate"])
    capsys.readouterr()  # drain any output from the invoke
    monkeypatch.delenv("PT_SUPPRESS_MIGRATION_WARNING", raising=False)
    _warn_unapplied_migrations()
    assert capsys.readouterr().err == ""


def test_warn_unapplied_skipped_under_turso(
    capsys: pytest.CaptureFixture[str], fresh_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Turso-mode users get nothing from this warning (the runner
    doesn't target Turso). Silently skip."""
    monkeypatch.delenv("PT_SUPPRESS_MIGRATION_WARNING", raising=False)
    monkeypatch.setattr("pt._USE_TURSO", True)
    _warn_unapplied_migrations()
    assert capsys.readouterr().err == ""


def test_warn_unapplied_skips_silently_when_db_missing(
    capsys: pytest.CaptureFixture[str], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing DB file is the normal state before first run — early
    return, no output, no crash."""
    monkeypatch.delenv("PT_SUPPRESS_MIGRATION_WARNING", raising=False)
    monkeypatch.setenv("PT_DB_PATH", str(tmp_path / "nonexistent.db"))
    monkeypatch.setenv("PT_ALLOW_FRESH_DB", "1")
    _warn_unapplied_migrations()
    assert capsys.readouterr().err == ""


def test_warn_unapplied_reports_but_does_not_raise_on_unexpected_error(
    capsys: pytest.CaptureFixture[str], fresh_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The catch-all is the CLI's safety net — unexpected failures
    (broken config, permission error, corrupt migration file) must
    NOT brick pt. They should land on stderr so the operator knows
    something is off, and the CLI should keep running."""
    monkeypatch.delenv("PT_SUPPRESS_MIGRATION_WARNING", raising=False)

    # Force an error from inside the warning helper by monkeypatching
    # sqlite3.connect — this covers the path after db_path.exists() has
    # returned True, which the earlier test did not exercise. The patch
    # target "pt.sqlite3.connect" works because pt.py imports the
    # module via `import sqlite3` (not `from sqlite3 import connect`);
    # if that import ever changes, this monkeypatch becomes a silent
    # no-op and the test needs to be updated.
    def _boom(*_args, **_kwargs):
        raise sqlite3.DatabaseError("synthetic: disk I/O error")

    monkeypatch.setattr("pt.sqlite3.connect", _boom)
    _warn_unapplied_migrations()  # must NOT raise

    err = capsys.readouterr().err
    assert "could not check for pending migrations" in err
    assert "disk I/O error" in err


# ---------------------------------------------------------------------
# Boot-time manifest assertion wired into create_database
# ---------------------------------------------------------------------


def test_create_database_rejects_unclassified_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unclassified live table must cause ``create_database`` to
    raise ``UnclassifiedTableError`` — proving the assertion is wired
    into the DB init path, not just sitting in the manifest module."""
    from db import schema

    db_path = tmp_path / "tracker.db"
    # Pre-create an unclassified table so that when ensure_schema
    # finishes and assert_tables_classified runs, it finds 'rogue' in
    # the live tables but not in any classification set.
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE rogue (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    monkeypatch.setenv("PT_ALLOW_FRESH_DB", "1")

    with pytest.raises(UnclassifiedTableError, match="rogue"):
        schema.create_database(db_path)


def test_create_database_passes_with_manifested_tables_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sanity check: creating a DB with only schema.py's tables passes
    the assertion. This is the happy path on every laptop/Mini that
    has a normal pt install."""
    from db import schema

    db_path = tmp_path / "tracker.db"
    monkeypatch.setenv("PT_ALLOW_FRESH_DB", "1")

    # Should not raise.
    schema.create_database(db_path)

    # And every table that ensure_schema creates must be in the manifest.
    from db.crr_manifest import ALL_CLASSIFIED, live_table_names
    conn = sqlite3.connect(db_path)
    try:
        live = live_table_names(conn)
    finally:
        conn.close()
    assert live.issubset(ALL_CLASSIFIED), (
        f"schema.py creates tables not in crr_manifest.py: "
        f"{sorted(live - ALL_CLASSIFIED)}"
    )
