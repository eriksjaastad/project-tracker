"""`_get_conn` must not leak file descriptors (#6482).

cr-sqlite keeps per-connection prepared statements alive, and `sqlite3_close_v2`
cannot fully tear a connection down while they exist. So `conn.close()` alone
left the `.db` and `-wal` descriptors open — about two per connection.

The dashboard opens a connection per request, so it climbed until it hit the
256 soft limit, after which every query failed with "unable to open database
file" (SQLite's rendering of EMFILE) while the process stayed up and kept
answering. That is the "alive but broken" state that made the dashboard
unusable every 1-3 days and defeated `lsof -i :8000` as a health check.

Caught live at 123 handles on tracker.db plus 122 on tracker.db-wal, in a
process whose limit was exactly 256. `SELECT crsql_finalize()` before close
releases them.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from db.manager import DatabaseManager  # noqa: E402
from db.pt_id import _find_crsqlite_dylib  # noqa: E402
from db.schema import create_database  # noqa: E402


def _open_handles(db_path: Path) -> int:
    """Count this process's open descriptors against the database and its WAL.

    Raises rather than returning 0 when lsof misbehaves. A silent 0 here would
    make the leak test pass vacuously — baseline 0, growth 0 — which is the
    failure mode this file exists to catch.
    """
    proc = subprocess.run(
        ["lsof", "-p", str(os.getpid())],
        capture_output=True, text=True, timeout=60,
    )
    # lsof exits 1 when some descriptors can't be stat'd, which is normal and
    # still yields usable output. Empty output is not.
    if not proc.stdout.strip():
        raise RuntimeError(
            f"lsof produced no output (rc={proc.returncode}): {proc.stderr[:200]!r} — "
            "cannot measure descriptor growth"
        )
    name = db_path.name
    return sum(1 for line in proc.stdout.splitlines() if name in line)


@pytest.mark.skipif(
    _find_crsqlite_dylib() is None,
    reason="leak only occurs when cr-sqlite is loaded onto the connection",
)
@pytest.mark.skipif(
    subprocess.run(["which", "lsof"], capture_output=True).returncode != 0,
    reason="lsof unavailable",
)
def test_repeated_connections_do_not_leak_descriptors(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.db"
    create_database(db_path)
    db = DatabaseManager(db_path=db_path)

    # Warm up so one-off setup handles aren't counted as growth.
    with db._get_conn() as conn:
        conn.execute("SELECT COUNT(*) FROM tasks").fetchone()
    baseline = _open_handles(db_path)

    cycles = 60
    for _ in range(cycles):
        with db._get_conn() as conn:
            conn.execute("SELECT COUNT(*) FROM tasks").fetchone()

    grown = _open_handles(db_path) - baseline

    # Pre-fix this leaked ~2 per cycle (~120 here). Allow a couple of handles
    # of slack for WAL/shm churn without letting real growth through.
    assert grown <= 4, (
        f"{cycles} connect/close cycles leaked {grown} descriptors "
        f"(baseline {baseline}). crsql_finalize() is not being called before "
        f"close — this is what exhausts the 256 limit and makes every query "
        f"fail with 'unable to open database file' while the process stays up."
    )


def test_connection_still_usable_and_closed_cleanly(tmp_path: Path) -> None:
    """The finalize call must not break normal use or leave the conn open."""
    db_path = tmp_path / "tracker.db"
    create_database(db_path)
    db = DatabaseManager(db_path=db_path)

    with db._get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0

    # Using the connection after the context manager exits must fail, proving
    # close() still happened despite the extra finalize step.
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


@pytest.mark.skipif(
    _find_crsqlite_dylib() is None,
    reason="needs cr-sqlite to register a CRR table",
)
def test_writes_survive_finalize_on_a_real_crr_table(tmp_path: Path) -> None:
    """crsql_finalize tears down cr-sqlite's per-connection state, so prove a
    later connection can still write to a genuinely CRR-registered table.

    `create_database()` does not run `crsql_as_crr()` — that is a manual step,
    not part of any numbered migration — so a plain fixture would only catch
    gross breakage while claiming more. Register the tables explicitly, the
    same way tests/test_006_crr_drop_unique_constraints.py does. The migrations
    must run first: `crsql_as_crr` refuses a table carrying a NOT NULL column
    with no default, which is exactly what migrations 003/004 exist to fix.
    """
    from db.migration_runner import apply_all

    db_path = tmp_path / "tracker.db"
    create_database(db_path)

    dylib = str(_find_crsqlite_dylib())
    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    conn.load_extension(dylib, entrypoint="sqlite3_crsqlite_init")
    conn.enable_load_extension(False)
    apply_all(conn, Path(__file__).parent.parent / "scripts" / "db" / "migrations")
    for table in ("projects", "tasks"):
        assert conn.execute("SELECT crsql_as_crr(?)", (table,)).fetchone() == ("OK",)
    conn.commit()
    conn.execute("SELECT crsql_finalize()")
    conn.close()

    # Every write below goes through _get_conn, so each one finalizes on exit.
    db = DatabaseManager(db_path=db_path)
    db.add_project("alpha", "Alpha", str(tmp_path / "alpha"), "active")
    assert db.add_task("first task", "alpha")
    assert db.add_task("second task", "alpha")
    assert len(db.get_tasks(project_id="alpha")) == 2

    # The CRR clock must have recorded those writes — that is what proves
    # finalize did not sever cr-sqlite's change tracking.
    check = sqlite3.connect(db_path)
    check.enable_load_extension(True)
    check.load_extension(dylib, entrypoint="sqlite3_crsqlite_init")
    check.enable_load_extension(False)
    clock_rows = check.execute("SELECT COUNT(*) FROM tasks__crsql_clock").fetchone()[0]
    check.execute("SELECT crsql_finalize()")
    check.close()
    assert clock_rows > 0, "writes did not reach the CRR clock after finalize"
