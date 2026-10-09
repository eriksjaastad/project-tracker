"""Migration 018 removes cr-sqlite (#8093, D2).

The CRR-specific cases build a genuinely CRR-ified database with the real
extension and skip when it is not installed. The rest use plain sqlite.
"""

from __future__ import annotations

import hashlib
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from db.backend_manager import DatabaseManager as BackendManager  # noqa: E402
from db.manager import DatabaseManager  # noqa: E402
from db.migration_runner import apply_all, apply_migration, discover_migrations  # noqa: E402
from db.pt_id import load_machine_id, reset_for_testing  # noqa: E402
from db.schema import LEGACY_CRSQL_MESSAGE, LegacyCrsqlError, create_database  # noqa: E402

MIGRATIONS_DIR = Path(__file__).parent.parent / "scripts" / "db" / "migrations"
DYLIB = Path.home() / ".local/lib/crsqlite/crsqlite.dylib"
CRR_TABLES = (
    "ai_agents", "calendar_event_tasks", "calendar_events", "ideas",
    "project_info", "projects", "service_dependencies", "task_attachments",
    "task_history", "tasks",
)
needs_dylib = pytest.mark.skipif(not DYLIB.exists(), reason="needs the cr-sqlite extension")


@pytest.fixture(autouse=True)
def _reset_ids():
    reset_for_testing()
    yield
    reset_for_testing()


def _m018():
    [m] = [m for m in discover_migrations(MIGRATIONS_DIR, verbose=False) if m.version == 18]
    return m


def _apply_below_018(conn: sqlite3.Connection) -> None:
    """Apply every migration before 018 (the state a CRR database is in)."""
    pending = [m for m in discover_migrations(MIGRATIONS_DIR, verbose=False) if m.version < 18]
    from db.migration_runner import unapplied_migrations
    for m in unapplied_migrations(conn, pending):
        apply_migration(conn, m)


def _crsql_objects(conn: sqlite3.Connection) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE '%crsql%' ORDER BY name"
        )
    ]


def _user_tables(conn: sqlite3.Connection) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite\\_%' ESCAPE '\\' AND name NOT LIKE '%crsql%' "
            "AND name NOT IN ('_metadata', 'schema_migrations') ORDER BY name"
        )
    ]


def _snapshot(conn: sqlite3.Connection) -> dict[str, tuple[int, str]]:
    out = {}
    for t in _user_tables(conn):
        h = hashlib.sha256()
        rows = conn.execute(f"SELECT * FROM {t} ORDER BY 1, 2").fetchall()
        for row in rows:
            h.update(repr(row).encode())
        out[t] = (len(rows), h.hexdigest())
    return out


def _build_crr_db(path: Path) -> int:
    """A CRR-ified database with data in every table. Returns the machine id
    the pre-018 code derived from its site id."""
    create_database(path)
    BackendManager(path).migrate_attachments_table()  # task_attachments is created lazily
    conn = sqlite3.connect(path, isolation_level=None)
    conn.enable_load_extension(True)
    conn.load_extension(str(DYLIB), entrypoint="sqlite3_crsqlite_init")
    conn.enable_load_extension(False)
    _apply_below_018(conn)
    for t in CRR_TABLES:
        assert conn.execute("SELECT crsql_as_crr(?)", (t,)).fetchone() == ("OK",)
    now = "2026-10-01T00:00:00"
    conn.execute(
        "INSERT INTO projects (id, name, path, status, created_at) "
        "VALUES ('p1', 'P One', '/x/p1', 'active', ?)", (now,))
    for i in range(1, 6):
        conn.execute(
            "INSERT INTO tasks (id, text, status, project_id, created_at, updated_at) "
            "VALUES (?, ?, 'Backlog', 'p1', ?, ?)", (i, f"task {i}", now, now))
    conn.execute("UPDATE tasks SET status='Done' WHERE id=1")
    site_id = conn.execute("SELECT crsql_site_id()").fetchone()[0]
    assert conn.execute("SELECT COUNT(*) FROM tasks__crsql_clock").fetchone()[0] > 0
    conn.execute("SELECT crsql_finalize()")
    conn.close()
    d = hashlib.sha256(bytes(site_id)).digest()
    return ((d[0] << 8) | d[1]) & 1023


@needs_dylib
def test_018_removes_every_crsql_object_and_keeps_data(tmp_path: Path) -> None:
    db_path = tmp_path / "crr.db"
    derived = _build_crr_db(db_path)

    conn = sqlite3.connect(db_path, isolation_level=None)
    before_objects = _crsql_objects(conn)
    assert len([n for n in before_objects if n.endswith(("_itrig", "_utrig", "_dtrig"))]) == 30
    assert {"crsql_master", "crsql_site_id", "crsql_tracked_peers"} <= set(before_objects)
    before = _snapshot(conn)
    assert before["tasks"][0] == 5

    # Plain connection: the extension is NOT loaded here.
    with pytest.raises(sqlite3.OperationalError, match="crsql"):
        conn.execute("UPDATE tasks SET text='x' WHERE id=2")

    applied = apply_all(conn, MIGRATIONS_DIR)
    assert [m.version for m in applied] == [18]

    assert _crsql_objects(conn) == []
    assert _snapshot(conn) == before
    assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    stored = conn.execute(
        "SELECT value FROM _metadata WHERE key='pt.machine_id'"
    ).fetchone()
    assert stored == (str(derived),)
    conn.close()

    assert load_machine_id(db_path) == derived

    # Writes work through the manager with no extension anywhere.
    db = BackendManager(db_path)
    with db._get_conn() as c:
        c.execute("UPDATE tasks SET text='edited' WHERE id=2")
        c.commit()
        assert c.execute("SELECT text FROM tasks WHERE id=2").fetchone()[0] == "edited"


@needs_dylib
def test_018_rerun_is_a_noop(tmp_path: Path) -> None:
    db_path = tmp_path / "crr.db"
    _build_crr_db(db_path)
    conn = sqlite3.connect(db_path, isolation_level=None)
    apply_all(conn, MIGRATIONS_DIR)
    after_first = _snapshot(conn)
    meta = conn.execute("SELECT key, value FROM _metadata ORDER BY key").fetchall()

    _m018().up(conn)  # run the body again, outside the ledger

    assert _snapshot(conn) == after_first
    assert conn.execute("SELECT key, value FROM _metadata ORDER BY key").fetchall() == meta
    assert apply_all(conn, MIGRATIONS_DIR) == []


@needs_dylib
def test_018_keeps_an_explicit_machine_id(tmp_path: Path) -> None:
    db_path = tmp_path / "crr.db"
    _build_crr_db(db_path)
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute(
        "INSERT INTO _metadata (key, value, created_at) VALUES ('pt.machine_id', '7', 'now')"
    )
    apply_all(conn, MIGRATIONS_DIR)
    assert conn.execute(
        "SELECT value FROM _metadata WHERE key='pt.machine_id'"
    ).fetchone() == ("7",)


def test_018_machine_id_hash_matches_the_old_derivation(tmp_path: Path) -> None:
    """Pin the mapping with literals computed once from the old pt_id code
    (sha256 of the site id, first two bytes, masked to 10 bits)."""
    cases = [
        ("00" * 16, 839),
        ("ff" * 16, 710),
        ("2f172ba73131458299556dc2f2773351", 883),
    ]
    for site_hex, expected in cases:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE _metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL, created_at TEXT NOT NULL)")
        conn.execute("CREATE TABLE crsql_site_id (site_id BLOB NOT NULL, ordinal INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO crsql_site_id VALUES (?, 0)", (bytes.fromhex(site_hex),))
        conn.execute("INSERT INTO crsql_site_id VALUES (?, 1)", (bytes.fromhex("11" * 16),))  # a peer
        _m018().up(conn)
        assert conn.execute("SELECT value FROM _metadata WHERE key='pt.machine_id'").fetchone() == (str(expected),)
        assert _crsql_objects(conn) == []


def test_018_is_a_noop_on_a_fresh_database(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.db"
    create_database(db_path)
    conn = sqlite3.connect(db_path, isolation_level=None)
    _apply_below_018(conn)
    before = _snapshot(conn)
    meta = conn.execute("SELECT key, value FROM _metadata ORDER BY key").fetchall()
    apply_all(conn, MIGRATIONS_DIR)
    assert _snapshot(conn) == before
    assert conn.execute("SELECT key, value FROM _metadata ORDER BY key").fetchall() == meta
    assert not any(k == "pt.machine_id" for k, _ in meta)
    assert load_machine_id(db_path) == 0


def test_018_works_on_a_bare_database() -> None:
    conn = sqlite3.connect(":memory:")
    _m018().up(conn)  # no tables at all: must not raise


FAKE_TRIGGER = (
    "CREATE TRIGGER tasks__crsql_itrig AFTER INSERT ON tasks "
    "BEGIN SELECT crsql_internal_sync_bit(); END"
)


def _legacy_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "legacy.db"
    create_database(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(FAKE_TRIGGER)
    conn.commit()
    conn.close()
    return db_path


def test_legacy_database_gives_a_clear_write_error_and_reads_still_work(tmp_path: Path) -> None:
    db_path = _legacy_db(tmp_path)
    db = BackendManager(db_path)

    with db._get_conn() as conn:  # reads and non-trigger writes are untouched
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0

    with pytest.raises(LegacyCrsqlError) as exc:
        with db._get_conn() as conn:
            conn.execute(
                "INSERT INTO tasks (id, text, status, created_at, updated_at) "
                "VALUES (1, 't', 'Backlog', 'n', 'n')"
            )
    assert str(exc.value) == LEGACY_CRSQL_MESSAGE
    assert "pt db migrate" in str(exc.value)
    assert isinstance(exc.value, sqlite3.OperationalError)


def test_legacy_database_is_not_schema_ensured_and_migrate_fixes_it(tmp_path: Path) -> None:
    db_path = _legacy_db(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM schema_version")  # not current: ensure_schema would run
    conn.commit()
    conn.close()

    db = DatabaseManager(db_path)  # constructing must not touch or fail on it
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 0
    conn.close()

    result = db.migrations_apply()  # `pt db migrate` itself is not blocked
    assert result["ok"], result
    assert 18 in [m["version"] for m in result["applied"]]

    db2 = DatabaseManager(db_path)  # re-checks, now ensures the schema
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] > 0
    assert _crsql_objects(conn) == []
    conn.close()
    db2.add_project(project_id="p", name="P", path=str(tmp_path / "p"), status="active")
    task = db2.add_task("after migrate", "p")
    assert task["id"]


def test_migrate_drops_legacy_triggers_first_so_old_row_writing_migrations_run(tmp_path: Path) -> None:
    """A pre-009 backup that still has CRR triggers: 009 inserts rows into
    task_display_ids, which the (fake) trigger would reject without the
    extension. The apply path drops the triggers first; 018 finishes the rest."""
    db_path = tmp_path / "old.db"
    create_database(db_path)
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute("DROP TABLE IF EXISTS task_display_ids")
    conn.execute("DROP TABLE IF EXISTS schema_migrations")
    conn.execute(
        "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
    )
    for m in discover_migrations(MIGRATIONS_DIR, verbose=False):
        if m.version < 9:
            apply_migration(conn, m)
    conn.execute(
        "INSERT INTO projects (id, name, path, status, created_at) VALUES ('p', 'P', '/p', 'active', 'n')"
    )
    conn.execute(
        "INSERT INTO tasks (id, text, status, project_id, created_at, updated_at) "
        "VALUES (7, 't', 'Backlog', 'p', 'n', 'n')"
    )
    conn.execute(
        "CREATE TABLE task_display_ids (task_id INTEGER PRIMARY KEY NOT NULL, display_id INTEGER NOT NULL UNIQUE)"
    )
    conn.execute(
        "CREATE TRIGGER task_display_ids__crsql_itrig AFTER INSERT ON task_display_ids "
        "BEGIN SELECT crsql_internal_sync_bit(); END"
    )
    conn.execute("CREATE TABLE crsql_site_id (site_id BLOB NOT NULL, ordinal INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO crsql_site_id VALUES (?, 0)", (bytes.fromhex("00" * 16),))
    conn.close()

    result = DatabaseManager(db_path).migrations_apply()
    assert result["ok"], result
    versions = [m["version"] for m in result["applied"]]
    assert 9 in versions and versions[-1] == 18

    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT display_id FROM task_display_ids WHERE task_id=7").fetchone() == (7,)
    assert _crsql_objects(conn) == []
    assert conn.execute(
        "SELECT value FROM _metadata WHERE key='pt.machine_id'"
    ).fetchone() == ("839",)


def test_tracker_conn_translates_legacy_crsql_errors(tmp_path: Path) -> None:
    db = DatabaseManager(_legacy_db(tmp_path))
    conn = db._tracker_conn()
    try:
        with pytest.raises(LegacyCrsqlError, match="pt db migrate"):
            conn.execute(
                "INSERT INTO tasks (id, text, status, created_at, updated_at) "
                "VALUES (1, 't', 'Backlog', 'n', 'n')"
            )
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
    finally:
        conn.close()


def test_opening_a_legacy_database_logs_the_fix(tmp_path: Path, caplog) -> None:
    """Some callers stringify write errors, so the remedy is logged up front too."""
    import logging

    db_path = _legacy_db(tmp_path)
    with caplog.at_level(logging.WARNING):
        BackendManager(db_path)
    assert LEGACY_CRSQL_MESSAGE in [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
