"""Tests for the Phase 2.1b sync control surface.

Two layers:

- ``scripts/db/sync_state.py`` — the thin persistence wrapper around
  ``_metadata`` keys. Exercised directly against a tmp sqlite DB.
- ``pt sync status/pause/resume`` CLI — exercised via ``click.testing.CliRunner``
  with PT_DB_PATH pointing at a tmp DB.

The real sync daemon doesn't exist yet (PR #3c); these tests pin the
control-surface contract so when the daemon does land it reads the
same state the CLI writes here.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

# noqa: E402 — sys.path setup precedes imports
from db.sync_state import (  # noqa: E402
    clear_paused,
    is_paused,
    last_sync,
    pause_scope,
    record_last_sync,
    set_paused,
)
from pt import cli  # noqa: E402


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """A fresh sqlite file with only the ``_metadata`` table created —
    enough for the sync-state module to operate against."""
    db_path = tmp_path / "tracker.db"
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute(
        "CREATE TABLE _metadata ("
        "key TEXT PRIMARY KEY, "
        "value TEXT NOT NULL, "
        "created_at TEXT NOT NULL)"
    )
    conn.close()
    return db_path


@pytest.fixture
def cli_env(
    tmp_db: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point pt at a throwaway DB and silence the banner/warning."""
    monkeypatch.setenv("PT_DB_PATH", str(tmp_db))
    monkeypatch.setenv("PT_NO_BANNER", "1")
    monkeypatch.setenv("PT_ALLOW_FRESH_DB", "1")
    monkeypatch.setenv("PT_SUPPRESS_MIGRATION_WARNING", "1")
    return tmp_db


# ---------------------------------------------------------------------
# sync_state module
# ---------------------------------------------------------------------


def test_default_state_is_not_paused(tmp_db: Path) -> None:
    conn = sqlite3.connect(tmp_db, isolation_level=None)
    try:
        assert is_paused(conn) is False
        assert pause_scope(conn) is None
        assert last_sync(conn) is None
    finally:
        conn.close()


def test_set_paused_default_scope_is_data_plane(tmp_db: Path) -> None:
    """Calling ``set_paused`` without args pauses the data plane only
    — the control plane must keep running (the §2.3 resume gate
    depends on it)."""
    conn = sqlite3.connect(tmp_db, isolation_level=None)
    try:
        set_paused(conn)
        assert is_paused(conn) is True
        assert pause_scope(conn) == "data_plane"
    finally:
        conn.close()


def test_set_paused_all_scope(tmp_db: Path) -> None:
    conn = sqlite3.connect(tmp_db, isolation_level=None)
    try:
        set_paused(conn, scope="all")
        assert pause_scope(conn) == "all"
    finally:
        conn.close()


def test_set_paused_rejects_invalid_scope(tmp_db: Path) -> None:
    conn = sqlite3.connect(tmp_db, isolation_level=None)
    try:
        with pytest.raises(ValueError, match="pause scope"):
            set_paused(conn, scope="nope")  # type: ignore[arg-type]
    finally:
        conn.close()


def test_clear_paused_round_trip(tmp_db: Path) -> None:
    conn = sqlite3.connect(tmp_db, isolation_level=None)
    try:
        set_paused(conn, scope="all")
        assert is_paused(conn) is True
        clear_paused(conn)
        assert is_paused(conn) is False
        assert pause_scope(conn) is None
    finally:
        conn.close()


def test_clear_paused_is_idempotent_when_not_paused(tmp_db: Path) -> None:
    """Calling clear on a never-paused DB must not raise and must not
    leave stray rows behind."""
    conn = sqlite3.connect(tmp_db, isolation_level=None)
    try:
        clear_paused(conn)
        clear_paused(conn)
        assert is_paused(conn) is False
    finally:
        conn.close()


def test_pause_scope_coerces_unexpected_values(tmp_db: Path) -> None:
    """A manual edit of _metadata (or a future daemon using a new
    scope token) should not crash the CLI — unknown scopes coerce
    to the conservative data_plane value."""
    conn = sqlite3.connect(tmp_db, isolation_level=None)
    try:
        conn.execute(
            "INSERT INTO _metadata (key, value, created_at) "
            "VALUES ('sync.paused', '1', '2026-04-19T00:00:00+00:00')"
        )
        conn.execute(
            "INSERT INTO _metadata (key, value, created_at) "
            "VALUES ('sync.pause_scope', 'garbage', '2026-04-19T00:00:00+00:00')"
        )
        assert pause_scope(conn) == "data_plane"
    finally:
        conn.close()


def test_record_last_sync_sets_iso_timestamp(tmp_db: Path) -> None:
    conn = sqlite3.connect(tmp_db, isolation_level=None)
    try:
        assert last_sync(conn) is None
        record_last_sync(conn)
        stamp = last_sync(conn)
        assert stamp is not None
        # ISO8601 with timezone offset
        assert "T" in stamp and ("+" in stamp or "Z" in stamp)
    finally:
        conn.close()


def test_sync_state_handles_missing_metadata_table() -> None:
    """A cold DB without ``_metadata`` must not crash the sync-state
    readers. They return defaults (False / None) so ``pt sync status``
    stays honest before the DB is initialized."""
    conn = sqlite3.connect(":memory:")
    try:
        assert is_paused(conn) is False
        assert pause_scope(conn) is None
        assert last_sync(conn) is None
    finally:
        conn.close()


# ---------------------------------------------------------------------
# pt sync CLI
# ---------------------------------------------------------------------


def test_status_reports_idle_and_never_on_fresh_db(
    runner: CliRunner, cli_env: Path
) -> None:
    result = runner.invoke(cli, ["sync", "status"])
    assert result.exit_code == 0, result.output
    assert "idle" in result.output
    assert "never" in result.output
    assert "NOT loaded" in result.output


def test_pause_updates_status_to_paused_data_plane(
    runner: CliRunner, cli_env: Path
) -> None:
    pause = runner.invoke(cli, ["sync", "pause"])
    assert pause.exit_code == 0, pause.output
    assert "paused" in pause.output and "data_plane" in pause.output

    status = runner.invoke(cli, ["sync", "status"])
    assert status.exit_code == 0
    assert "paused" in status.output
    assert "data_plane" in status.output


def test_pause_all_halts_control_plane_and_warns(
    runner: CliRunner, cli_env: Path
) -> None:
    result = runner.invoke(cli, ["sync", "pause", "--all"])
    assert result.exit_code == 0, result.output
    assert "all" in result.output
    assert "Control plane" in result.output

    status = runner.invoke(cli, ["sync", "status"])
    assert "all" in status.output


def test_resume_clears_pause_state(
    runner: CliRunner, cli_env: Path
) -> None:
    runner.invoke(cli, ["sync", "pause"])
    result = runner.invoke(cli, ["sync", "resume"])
    assert result.exit_code == 0, result.output
    assert "resumed" in result.output

    status = runner.invoke(cli, ["sync", "status"])
    assert "paused" not in status.output


def test_resume_on_not_paused_is_noop(
    runner: CliRunner, cli_env: Path
) -> None:
    result = runner.invoke(cli, ["sync", "resume"])
    assert result.exit_code == 0, result.output
    assert "not paused" in result.output


def test_pause_refuses_under_turso(
    runner: CliRunner, cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Turso's replication is handled upstream; local pause/resume
    is meaningless. Refuse rather than silently no-op."""
    monkeypatch.setattr("pt._USE_TURSO", True)
    pause = runner.invoke(cli, ["sync", "pause"])
    resume = runner.invoke(cli, ["sync", "resume"])
    status = runner.invoke(cli, ["sync", "status"])

    assert pause.exit_code == 2
    assert resume.exit_code == 2
    # Status reports the Turso state instead of refusing — it's a read.
    assert status.exit_code == 0
    assert "Turso" in status.output


def test_resume_unblocked_when_crsqlite_not_loaded(
    runner: CliRunner, cli_env: Path
) -> None:
    """Before cr-sqlite is loaded on the real DB, the peer-announcement
    gate has no way to observe peer rows (no replication). Resume must
    NOT block in that case — otherwise the operator could never clear
    a pause on a daemon-less install."""
    runner.invoke(cli, ["sync", "pause"])
    result = runner.invoke(cli, ["sync", "resume"])
    assert result.exit_code == 0, result.output
    assert "resumed" in result.output


def test_resume_blocks_when_peer_announcement_missing(
    runner: CliRunner, cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If cr-sqlite is loaded and there's a locally-applied migration
    that the peer hasn't announced, resume must refuse to clear pause
    and print the §2.3 step-6 message. Without --force."""
    runner.invoke(cli, ["sync", "pause"])

    # Stub the gate query: pretend versions 7 and 9 are locally applied
    # but peer hasn't announced them. Patching the helper is cleaner
    # than patching sqlite3.Connection.execute (immutable C-extension
    # method — can't be monkeypatched).
    monkeypatch.setattr(
        "pt._sync_resume_blocked_versions", lambda conn: [7, 9]
    )

    result = runner.invoke(cli, ["sync", "resume"])
    assert result.exit_code == 3
    assert "waiting for peer" in result.output
    assert "007" in result.output  # zero-padded version
    assert "009" in result.output
    assert "--force" in result.output


def test_resume_force_bypasses_block(
    runner: CliRunner, cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner.invoke(cli, ["sync", "pause"])
    monkeypatch.setattr(
        "pt._sync_resume_blocked_versions", lambda conn: [7]
    )
    result = runner.invoke(cli, ["sync", "resume", "--force"])
    assert result.exit_code == 0, result.output
    assert "resumed" in result.output


def test_sync_resume_blocked_versions_returns_empty_without_crsqlite(
    cli_env: Path,
) -> None:
    """Direct unit test: with a stock sqlite3 conn (no cr-sqlite),
    the helper returns [] — this is the guard that keeps daemon-less
    installs unblocked."""
    from pt import _sync_resume_blocked_versions
    conn = sqlite3.connect(cli_env, isolation_level=None)
    try:
        assert _sync_resume_blocked_versions(conn) == []
    finally:
        conn.close()


def test_pause_reports_clean_error_on_db_open_failure(
    runner: CliRunner, cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A broken DB path must produce a Click-style error, not a raw
    Python traceback. Covers the code-reviewer LOW finding on
    unhandled sqlite3 errors in sync_pause/resume/status."""
    def _boom(*_args, **_kwargs):
        raise sqlite3.DatabaseError("synthetic: unable to open database file")

    monkeypatch.setattr("pt.sqlite3.connect", _boom)
    result = runner.invoke(cli, ["sync", "pause"])
    assert result.exit_code == 2
    assert "pt sync pause" in result.output
    assert "unable to open database file" in result.output
    # No traceback surfaced to the operator.
    assert "Traceback" not in result.output


def test_sync_help_lists_all_three_subcommands(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["sync", "--help"])
    assert result.exit_code == 0
    for sub in ("status", "pause", "resume"):
        assert sub in result.output
