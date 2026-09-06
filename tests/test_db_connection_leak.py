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
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from db.manager import DatabaseManager  # noqa: E402
from db.pt_id import _find_crsqlite_dylib  # noqa: E402
from db.schema import create_database  # noqa: E402


def _open_handles(db_path: Path) -> int:
    """Count this process's open descriptors against the database and its WAL."""
    out = subprocess.run(
        ["lsof", "-p", str(os.getpid())],
        capture_output=True, text=True, timeout=60,
    ).stdout
    name = db_path.name
    return sum(1 for line in out.splitlines() if name in line)


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
    with pytest.raises(Exception):
        conn.execute("SELECT 1")


def test_writes_still_work_after_finalize_is_wired_in(tmp_path: Path) -> None:
    """crsql_finalize tears down cr-sqlite state; a later connection must still
    be able to write to a CRR table rather than failing on a missing function."""
    db_path = tmp_path / "tracker.db"
    create_database(db_path)
    db = DatabaseManager(db_path=db_path)

    db.add_project("alpha", "Alpha", str(tmp_path / "alpha"), "active")
    first = db.add_task("first task", "alpha")
    second = db.add_task("second task", "alpha")

    assert first and second
    assert len(db.get_tasks(project_id="alpha")) == 2
