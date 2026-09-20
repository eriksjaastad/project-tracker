import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path

import pytest

# Ensure the project root is on sys.path so that `scripts` and `dashboard`
# are importable in any environment (including sandboxed uv run on the Mini).
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Phase 2.1a: the pt root callback emits a stderr warning when the DB
# has unapplied migrations. Humans see it; CliRunner merges it into
# ``result.output`` and breaks JSON-parsing tests that invoke real pt
# subcommands. Suppress by default for tests; tests that specifically
# want to exercise the warning delete this env var per-test.
os.environ.setdefault("PT_SUPPRESS_MIGRATION_WARNING", "1")

# Keep the destructive-operation audit log out of the developer's real one.
# `_audit_destructive` records every in-process deletion so a future incident
# can be attributed; tests that exercise those code paths were writing
# synthetic pytest-tmp entries straight into it (51 of 51 entries were test
# chaff), burying real evidence in the file that exists to preserve it.
# Session-scoped so a single run's records stay together if anyone inspects them.
_TEST_DESTRUCTIVE_LOG = (
    Path(tempfile.gettempdir()) / f"pt-destructive-tests-{os.getpid()}.log"
)
os.environ.setdefault("PT_DESTRUCTIVE_LOG_PATH", str(_TEST_DESTRUCTIVE_LOG))

# Keep migration backups out of the REAL external backup directory.
#
# `scripts/config.py` resolves EXTERNAL_BACKUP_DIR at import to
# ~/.project-tracker/backups — the second location DECISIONS.md requires so
# that losing the project directory does not lose the data. Migrations write a
# pre-flight backup to it, and the test suite runs migrations, so every run
# has been dropping 135KB snapshots into the disaster-recovery directory since
# April. 9,641 files were found there on 2026-09-17, effectively burying the
# real backups in test chaff.
#
# Set before anything imports scripts.config, because it is read once at
# import and cached in a module constant.
#
# FORCE the test override — use direct assignment instead of setdefault so
# that if PT_EXTERNAL_BACKUP_DIR is inherited from the outer environment,
# the test-scoped temp directory wins. Prevents leaks when pytest is run
# with the variable already set.
_TEST_EXTERNAL_BACKUPS = Path(tempfile.gettempdir()) / f"pt-test-backups-{os.getpid()}"
os.environ["PT_EXTERNAL_BACKUP_DIR"] = str(_TEST_EXTERNAL_BACKUPS)

# The schema layer refuses to initialise a database that is unexpectedly
# empty — a guard against the 2026-01-27 incident, where an empty database
# meant the real one had been destroyed. Every test database starts empty on
# purpose, so the guard is off for the suite and only for the suite.
os.environ.setdefault("PT_ALLOW_FRESH_DB", "1")

# Collection and no_dbmed tests must never inherit the installed service.
# Database fixtures replace this with their temporary socket for each test.
_TEST_SOCKET_ROOT = Path(tempfile.mkdtemp(prefix="pt-test-offline-"))
os.environ["DBMED_SOCKET"] = str(_TEST_SOCKET_ROOT / "unavailable.sock")


# ---------------------------------------------------------------------------
# dbmed: every test gets its own database, behind the same boundary as prod
# ---------------------------------------------------------------------------
#
# Before the boundary, a test that wanted a throwaway database set PT_DB_PATH
# and constructed `DatabaseManager(tmp_path / "tracker.db")`. Neither works
# now, and deliberately so: a caller-chosen path is the bypass the boundary
# exists to prevent, and the conftest that did not set PT_DB_PATH is how
# fourteen test modules ended up writing to the live tracker.db.
#
# What replaces it is the real thing, scaled down. Each test gets a real dbmed
# daemon on a real socket, serving a real database it alone owns, reached
# through the same client the dashboard uses. Tests exercise the production
# code path rather than a stand-in for it, which is the only way their passing
# means anything about production.
#
# What is NOT reproduced here is the kernel-level part: these directories are
# owned by the user running pytest, not by `_dbmed`. Proving that a process
# cannot open the file needs the real root install, and those probes live in
# tests/boundary/ where they skip loudly rather than pretending.

_SOCKET_DIRS: list[Path] = []

# The developer's cr-sqlite build. In production the installer vendors this
# root-owned and registers that copy; there is no install here, so the test
# daemon is pointed at wherever the developer's is. That is not a weakening:
# the registry is how the path is chosen either way, and this registry is one
# the test wrote for a daemon serving a throwaway database.
_CRSQLITE = next(
    (
        candidate
        for candidate in (
            Path.home() / ".local" / "lib" / "crsqlite" / "crsqlite.dylib",
            Path("/usr/local/lib/crsqlite/crsqlite.dylib"),
        )
        if candidate.exists()
    ),
    None,
)


@pytest.fixture(scope="session")
def _dbmed_base_template(tmp_path_factory) -> Path:
    """Base schema only, with the numbered migrations deliberately NOT applied.

    `pt db migrate` and the pending-migration warning can only be tested
    against a database that actually has something pending. Opt in with
    `@pytest.mark.unmigrated_db`.
    """
    from db.schema import create_database

    template = tmp_path_factory.mktemp("dbmed-base-template") / "tracker.db"
    create_database(template)
    return template


@pytest.fixture(scope="session")
def _dbmed_template(tmp_path_factory) -> Path:
    """A schema-only database, built once and copied per test.

    Building the schema takes about 15ms and copying a 100KB file takes well
    under one. Multiplied across the suite that is the difference between a
    boundary that tests tolerate and one they resent.
    """
    import sqlite3

    from db.migration_runner import apply_all
    from db.schema import create_database

    template = tmp_path_factory.mktemp("dbmed-template") / "tracker.db"
    create_database(template)

    # Apply the numbered migrations too. `create_database` builds the base
    # schema; tables like `handoffs` (010) and `migrations` (011) arrive as
    # migrations, and a test database missing them is not the database
    # production runs — tests would pass against a schema nobody ships.
    migrations_dir = Path(__file__).resolve().parent / "scripts" / "db" / "migrations"
    conn = sqlite3.connect(template, isolation_level=None)
    try:
        apply_all(conn, migrations_dir)
    except Exception as exc:  # pragma: no cover - surfaced, never swallowed
        raise RuntimeError(
            f"could not build the test schema template: {type(exc).__name__}: {exc}"
        ) from exc
    finally:
        conn.close()
    return template


@pytest.fixture
def dbmed_daemon(request, tmp_path, _dbmed_template, _dbmed_base_template):
    """An isolated dbmed daemon for one test. Yields its socket path."""
    from dbmed import daemon as dbmed_daemon_module

    template = (
        _dbmed_base_template
        if request.node.get_closest_marker("unmigrated_db")
        else _dbmed_template
    )

    root = tmp_path / "_dbmed"
    config = root / "etc"
    install = root / "libexec"
    data = root / "var"
    project_data = data / "project-tracker"

    (config / "registry.d").mkdir(parents=True)
    install.mkdir(parents=True)
    for sub in ("backups", "fixtures", "attic"):
        (project_data / sub).mkdir(parents=True)
    (data / "external" / "project-tracker").mkdir(parents=True)

    shutil.copy(template, project_data / "tracker.db")

    (config / "registry.d" / "project-tracker.toml").write_text(
        f'project = "project-tracker"\n'
        f'db_path = "{project_data}/tracker.db"\n'
        f'data_root = "{data}"\n'
        f'backup_dir = "{project_data}/backups"\n'
        f'external_backup_dir = "{data}/external/project-tracker"\n'
        f'fixture_root = "{project_data}/fixtures"\n'
        f'ops_module = "db.dbmed_ops"\n'
        + (f'crsqlite_path = "{_CRSQLITE}"\n' if _CRSQLITE else "")
        + f"allowed_users = [{os.getuid()}]\n"
        # Enables dbmed.seed and dbmed.count, which exist only for fixtures.
        # install.sh never writes this flag, so a real daemon refuses both.
        f"test_support = true\n"
    )

    # sun_path is capped near 104 bytes on macOS and pytest's tmp_path blows
    # straight through it. The failure is a bare "AF_UNIX path too long", so
    # the socket goes somewhere short.
    socket_dir = Path(tempfile.mkdtemp(prefix="ptd", dir="/tmp"))
    _SOCKET_DIRS.append(socket_dir)
    socket_path = socket_dir / "d.sock"

    ready: threading.Event = threading.Event()
    control: dict = {}
    thread = threading.Thread(
        target=dbmed_daemon_module.serve,
        kwargs={
            "socket_path": socket_path,
            "config_dir": config,
            "install_dir": install,
            "data_root": data,
            # pytest cannot create root-owned files. The daemon refuses this
            # flag when running as root, so the real service can never use it.
            "verify_integrity": False,
            "ready": ready,
            "control": control,
            "poll_interval": 0.01,
        },
        daemon=True,
    )
    thread.start()
    if not ready.wait(30):
        raise RuntimeError("the test dbmed daemon never became ready")

    previous = os.environ.get("DBMED_SOCKET")
    os.environ["DBMED_SOCKET"] = str(socket_path)
    try:
        yield socket_path
    finally:
        if previous is None:
            os.environ.pop("DBMED_SOCKET", None)
        else:
            os.environ["DBMED_SOCKET"] = previous
        server = control.get("server")
        if server is not None:
            server.shutdown()
        thread.join(timeout=10)


@pytest.fixture(autouse=True)
def _dbmed_autouse(request):
    """Point every database-touching test at its own daemon.

    Autouse so the ~150 tests that construct a `DatabaseManager` did not each
    need a new parameter threaded through them. Tests that never touch a
    database pay nothing: the daemon is only started when this resolves
    `dbmed_daemon`, and that is skipped for anything marked `no_dbmed`.
    """
    if request.node.get_closest_marker("no_dbmed"):
        yield None
        return
    yield request.getfixturevalue("dbmed_daemon")


@pytest.fixture
def db(dbmed_daemon):
    """A `DatabaseManager` for this test's isolated database.

    The direct replacement for the old `DatabaseManager(tmp_path / 'x.db')`.
    """
    from db.manager import DatabaseManager

    return DatabaseManager()


@pytest.fixture
def dbmed_backend(dbmed_daemon, tmp_path):
    """Seed unusual historical states in the daemon's synthetic DB only.

    Application requests still use the RPC client. This fixture is a backend
    test harness, never a caller-selectable production database path.
    """
    from db.backend_manager import DatabaseManager

    return DatabaseManager(tmp_path / "_dbmed/var/project-tracker/tracker.db")


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "no_dbmed: test needs no database; skip starting a dbmed daemon for it",
    )
    config.addinivalue_line(
        "markers",
        "unmigrated_db: serve a base-schema database with migrations unapplied, "
        "for tests that exercise the migration runner itself",
    )


def pytest_sessionfinish(session, exitstatus):
    """Clean up the short-path socket directories from /tmp."""
    from send2trash import send2trash

    for directory in _SOCKET_DIRS:
        try:
            if directory.exists():
                send2trash(str(directory))
        except OSError:
            # A leftover socket directory in /tmp is cosmetic and the OS
            # clears it on reboot. Never fail a test run over cleanup.
            pass
