"""Tests for scripts/db/sync_daemon.py — the long-running scaffolding.

The daemon's payload (``_sync_round_placeholder``) is a stub until PR
#3c-2 ships the real changeset exchange. These tests pin the outer
loop: preflight gating, pause respect, round cadence, clean shutdown,
signal handlers, and the ``_outstanding_peer_announcements`` helper
that ``pt sync resume`` reads.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from db.sync_daemon import (  # noqa: E402
    NTP_DRIFT_LIMIT_S,
    PreflightReport,
    SyncDaemon,
    _outstanding_peer_announcements,
    preflight,
)


# ---------------------------------------------------------------------
# PreflightReport.ok
# ---------------------------------------------------------------------


def _report(**overrides) -> PreflightReport:
    defaults = dict(
        crsqlite_loaded=True,
        ntp_drift_s=0.01,
        peer_reachable=True,
        manifest_hash="deadbeef" * 8,
    )
    defaults.update(overrides)
    return PreflightReport(**defaults)


def test_preflight_ok_when_all_checks_pass():
    assert _report().ok is True


def test_preflight_not_ok_when_crsqlite_absent():
    assert _report(crsqlite_loaded=False).ok is False


def test_preflight_not_ok_when_ntp_drift_is_none():
    """None means the sntp probe itself failed — treat as hard no."""
    assert _report(ntp_drift_s=None).ok is False


def test_preflight_not_ok_when_drift_over_limit():
    assert _report(ntp_drift_s=NTP_DRIFT_LIMIT_S + 0.01).ok is False


def test_preflight_ok_at_exact_limit():
    """Drift equal to the limit is within tolerance."""
    assert _report(ntp_drift_s=NTP_DRIFT_LIMIT_S).ok is True


def test_preflight_not_ok_when_peer_unreachable():
    assert _report(peer_reachable=False).ok is False


def test_preflight_summary_has_every_field():
    text = _report(ntp_drift_s=-0.042).summary()
    assert "crsqlite=yes" in text
    assert "ntp_drift=-0.042s" in text
    assert "peer_reachable=yes" in text
    assert "manifest=" in text


def test_preflight_summary_shows_unavailable_for_none_drift():
    assert "ntp_drift=unavailable" in _report(ntp_drift_s=None).summary()


# ---------------------------------------------------------------------
# preflight() integration
# ---------------------------------------------------------------------


def test_preflight_crsqlite_absent_when_probe_raises():
    conn = sqlite3.connect(":memory:")
    with patch("db.sync_daemon.ntp_drift_seconds", return_value=0.01), \
         patch("db.sync_daemon.peer_reachable", return_value=True):
        report = preflight(conn, peer_host="eriks-mac-mini")
    assert report.crsqlite_loaded is False


# ---------------------------------------------------------------------
# SyncDaemon lifecycle
# ---------------------------------------------------------------------


@pytest.fixture
def seeded_db(tmp_path: Path) -> Path:
    """Create a fresh DB with the _metadata table so sync_state works."""
    db_path = tmp_path / "tracker.db"
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute(
        "CREATE TABLE _metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL, "
        "created_at TEXT NOT NULL)"
    )
    conn.close()
    return db_path


def _healthy_preflight(*_args, **_kwargs):
    return PreflightReport(
        crsqlite_loaded=True, ntp_drift_s=0.0,
        peer_reachable=True, manifest_hash="h" * 64,
    )


def _failing_preflight(*_args, **_kwargs):
    return PreflightReport(
        crsqlite_loaded=True, ntp_drift_s=10.0,  # over the limit
        peer_reachable=True, manifest_hash="h" * 64,
    )


class _FakeConn:
    """Minimal sqlite-like connection that records calls for assertions.

    Substituted for a real cr-sqlite-loaded connection so tests don't
    depend on the dylib being present.
    """
    def __init__(self, real_conn: sqlite3.Connection) -> None:
        self._real = real_conn
        self.closed = False

    def execute(self, *a, **kw):
        return self._real.execute(*a, **kw)

    def close(self):
        self.closed = True
        self._real.close()


def test_daemon_refuses_to_start_when_preflight_fails(seeded_db: Path):
    rounds: list = []
    daemon = SyncDaemon(
        db_path=seeded_db,
        peer_host="peer",
        interval_seconds=0.01,
        round_fn=lambda c, h: rounds.append(h),
        sleep_fn=lambda s: None,
    )
    with patch.object(daemon, "_open_conn",
                      return_value=_FakeConn(sqlite3.connect(seeded_db, isolation_level=None))), \
         patch("db.sync_daemon.preflight", _failing_preflight):
        exit_code = daemon.start()
    assert exit_code == 2
    assert rounds == []  # no rounds ran


def test_daemon_runs_rounds_and_records_last_sync(seeded_db: Path):
    rounds: list = []

    def fake_round(conn, host):
        rounds.append(host)

    daemon = SyncDaemon(
        db_path=seeded_db,
        peer_host="peer",
        interval_seconds=0.0,
        round_fn=fake_round,
        sleep_fn=lambda s: daemon.stop(),  # stop after first sleep
    )

    conn_for_test = sqlite3.connect(seeded_db, isolation_level=None)
    with patch.object(daemon, "_open_conn", return_value=_FakeConn(conn_for_test)), \
         patch("db.sync_daemon.preflight", _healthy_preflight):
        exit_code = daemon.start()

    assert exit_code == 0
    assert rounds == ["peer"]  # exactly one round before stop

    # last_successful_sync was recorded.
    check = sqlite3.connect(seeded_db)
    row = check.execute(
        "SELECT value FROM _metadata WHERE key='sync.last_successful_sync'"
    ).fetchone()
    assert row is not None
    check.close()


def test_daemon_skips_rounds_while_paused(seeded_db: Path):
    """Paused state must not run the round function or record last_sync.
    Round counter stays at 0, last_sync stays absent."""
    rounds: list = []

    # Pre-set pause.
    conn = sqlite3.connect(seeded_db, isolation_level=None)
    conn.execute(
        "INSERT INTO _metadata (key, value, created_at) "
        "VALUES ('sync.paused', '1', '2026-04-19T00:00:00+00:00')"
    )
    conn.close()

    daemon = SyncDaemon(
        db_path=seeded_db,
        peer_host="peer",
        interval_seconds=0.0,
        round_fn=lambda c, h: rounds.append(h),
        sleep_fn=lambda s: daemon.stop(),
    )
    conn_for_test = sqlite3.connect(seeded_db, isolation_level=None)
    with patch.object(daemon, "_open_conn", return_value=_FakeConn(conn_for_test)), \
         patch("db.sync_daemon.preflight", _healthy_preflight):
        daemon.start()

    assert rounds == []  # round_fn not called
    check = sqlite3.connect(seeded_db)
    row = check.execute(
        "SELECT value FROM _metadata WHERE key='sync.last_successful_sync'"
    ).fetchone()
    assert row is None  # last_sync NOT recorded during pause
    check.close()


def test_daemon_survives_round_exception(seeded_db: Path):
    """A failing round must not kill the daemon — the loop logs and
    continues so transient network errors don't require a manual
    restart."""
    calls = {"n": 0}

    def flaky_round(conn, host):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("synthetic transient failure")

    daemon = SyncDaemon(
        db_path=seeded_db,
        peer_host="peer",
        interval_seconds=0.0,
        round_fn=flaky_round,
        sleep_fn=lambda s: None if calls["n"] < 2 else daemon.stop(),
    )
    conn_for_test = sqlite3.connect(seeded_db, isolation_level=None)
    with patch.object(daemon, "_open_conn", return_value=_FakeConn(conn_for_test)), \
         patch("db.sync_daemon.preflight", _healthy_preflight):
        exit_code = daemon.start()

    assert exit_code == 0
    assert calls["n"] == 2  # loop ran twice, first threw, second succeeded


def test_daemon_stop_is_idempotent_and_safe():
    daemon = SyncDaemon(db_path=Path("/tmp/nope"), peer_host="x")
    daemon.stop()
    daemon.stop()
    assert daemon._stop_requested is True


# ---------------------------------------------------------------------
# _outstanding_peer_announcements
# ---------------------------------------------------------------------


def _announcements_db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "ann.db", isolation_level=None)
    conn.execute(
        "CREATE TABLE schema_migration_announcements ("
        "version INTEGER NOT NULL, name TEXT NOT NULL, "
        "machine_id TEXT NOT NULL, applied_at TEXT NOT NULL, "
        "PRIMARY KEY (version, machine_id))"
    )
    return conn


def test_outstanding_returns_empty_when_table_missing():
    conn = sqlite3.connect(":memory:")
    assert _outstanding_peer_announcements(conn, local_site_id="me") == []


def test_outstanding_returns_empty_when_peer_has_matched(tmp_path: Path):
    conn = _announcements_db(tmp_path)
    conn.execute(
        "INSERT INTO schema_migration_announcements VALUES "
        "(2, 'add_sync_ledgers', 'me',   '2026-04-19T00:00:00+00:00'),"
        "(2, 'add_sync_ledgers', 'peer', '2026-04-19T00:01:00+00:00')"
    )
    assert _outstanding_peer_announcements(conn, local_site_id="me") == []


def test_outstanding_lists_locally_applied_unannounced_versions(tmp_path: Path):
    conn = _announcements_db(tmp_path)
    # Local machine applied 2 and 3. Peer only announced 2.
    conn.execute(
        "INSERT INTO schema_migration_announcements VALUES "
        "(2, 'a', 'me',   '2026-04-19T00:00:00+00:00'),"
        "(3, 'b', 'me',   '2026-04-19T00:02:00+00:00'),"
        "(2, 'a', 'peer', '2026-04-19T00:03:00+00:00')"
    )
    assert _outstanding_peer_announcements(conn, local_site_id="me") == [3]


def test_outstanding_ignores_versions_peer_announced_but_we_did_not(tmp_path: Path):
    """The gate is asymmetric — it blocks resume on this machine only
    for migrations THIS machine applied. Peer-only announcements are
    irrelevant here; that's the peer's problem."""
    conn = _announcements_db(tmp_path)
    conn.execute(
        "INSERT INTO schema_migration_announcements VALUES "
        "(5, 'unique_peer_mig', 'peer', '2026-04-19T00:00:00+00:00')"
    )
    assert _outstanding_peer_announcements(conn, local_site_id="me") == []
