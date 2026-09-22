import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure the project root is on sys.path so that `scripts` and `dashboard`
# are importable in any environment (including sandboxed uv run on the Mini).
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))

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

# Prevent collection-time imports from reaching the real database.
_TEST_DB_ROOT = Path(tempfile.mkdtemp(prefix="pt-test-db-"))
os.environ["PT_DB_PATH"] = str(_TEST_DB_ROOT / "collection.db")

@pytest.fixture(scope="session")
def _base_template(tmp_path_factory) -> Path:
    """Base schema only, with the numbered migrations deliberately NOT applied.

    `pt db migrate` and the pending-migration warning can only be tested
    against a database that actually has something pending. Opt in with
    `@pytest.mark.unmigrated_db`.
    """
    from db.schema import create_database

    template = tmp_path_factory.mktemp("local-base-template") / "tracker.db"
    create_database(template)
    return template


@pytest.fixture(scope="session")
def _template(tmp_path_factory) -> Path:
    """A schema-only database, built once and copied per test.

    Building the schema takes about 15ms and copying a 100KB file takes well
    under one. Multiplied across the suite that is the difference between a
    boundary that tests tolerate and one they resent.
    """
    import sqlite3

    from db.migration_runner import apply_all
    from db.schema import create_database

    template = tmp_path_factory.mktemp("local-template") / "tracker.db"
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


@pytest.fixture(autouse=True)
def isolated_database(request, tmp_path, monkeypatch, _template, _base_template):
    template = _base_template if request.node.get_closest_marker("unmigrated_db") else _template
    target = tmp_path / "_local" / "tracker.db"
    target.parent.mkdir()
    shutil.copy(template, target)
    monkeypatch.setenv("PT_DB_PATH", str(target))
    monkeypatch.setenv("PT_EXTERNAL_BACKUP_DIR", str(tmp_path / "external-backups"))
    from db import attachment_paths
    monkeypatch.setattr(attachment_paths, "ATTACHMENTS_ROOT", tmp_path / "attachments")
    from tests.local_db_support import LocalTestSupport
    from db.operations import ProjectTrackerOps
    for name in ("seed", "seed_task", "count_rows", "_SEEDABLE_TASK_COLUMNS", "_COUNTABLE_TABLES"):
        monkeypatch.setattr(ProjectTrackerOps, name, getattr(LocalTestSupport, name), raising=False)
    return target

@pytest.fixture
def db(isolated_database):
    from db.manager import DatabaseManager
    return DatabaseManager()

@pytest.fixture
def local_backend(isolated_database):
    from db.backend_manager import DatabaseManager
    return DatabaseManager(isolated_database)

def pytest_configure(config):
    config.addinivalue_line("markers", "unmigrated_db: exercise pending migrations")
