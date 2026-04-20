"""
Migration runner for project-tracker (Phase 2.1a + 2.2).

Reads migration modules from ``scripts/db/migrations/``, applies any that
aren't already recorded in the local ``schema_migrations`` ledger, wraps
each apply in a SQL transaction, and — when cr-sqlite is loaded — brackets
the alters to CRR tables with ``crsql_begin_alter`` / ``crsql_commit_alter``
so CRR bookkeeping metadata unwinds together with the SQL state if anything
raises.

The runner is stand-alone in this PR. It is **not** wired into `pt`
startup or exposed via CLI yet — that lands in Phase 2 PR #3 (the sync
control surface), along with the boot-time ``assert_tables_classified``
wiring. See MAC_MINI_SYNC_PLAN.md §2.1a, §2.2 for the contract.

Migration file format
---------------------
Files live in ``scripts/db/migrations/`` and match ``NNN_name.py`` where
``NNN`` is a 3-digit version number. Each module must expose:

- ``CRR_TABLES: frozenset[str]`` — the CRR-classified tables this
  migration alters. Empty for migrations that don't touch CRR tables.
  Every name must appear in ``crr_manifest.CRR_TABLES``; a typo or an
  unknown table stops the runner (refuse, not "run wrong at 2am" —
  §2.2).
- ``up(conn: sqlite3.Connection) -> None`` — applies the migration.
  Called inside an already-open transaction; must **not** issue
  ``BEGIN``, ``COMMIT``, or ``ROLLBACK``.

Files under ``migrations/`` whose basename doesn't match ``NNN_name.py``
(``__init__.py``, dotfiles, editor backups) are ignored silently. Files
that match the naming pattern but lack ``up()`` or ``CRR_TABLES`` — for
example the legacy, deprecated ``001_add_review_status.py`` that
pre-dates this runner — emit a stderr warning on discovery and are
skipped. They will never be applied.

cr-sqlite gating
----------------
The wrapper detects cr-sqlite by probing ``crsql_dbversion()`` once per
``apply_migration`` call. If the extension isn't loaded (the current
state on both machines), the ``crsql_begin_alter`` / ``crsql_commit_alter``
calls are skipped — the migration still runs inside a transaction, just
without the CRR bracketing. This keeps the runner usable before Phase 2
flips cr-sqlite on, and makes the flip a one-liner (load the extension)
rather than a code change.
"""

from __future__ import annotations

import importlib.util
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Callable, Iterable, cast

from db.crr_manifest import CRR_TABLES as MANIFEST_CRR_TABLES


MIGRATION_FILENAME_RE = re.compile(r"^(\d{3})_([a-z0-9_]+)\.py$")


class MigrationError(RuntimeError):
    """Raised when a migration file is malformed or declares unknown CRR tables."""


@dataclass(frozen=True)
class Migration:
    """One discovered, validated migration ready to apply."""

    version: int
    name: str
    path: Path
    crr_tables: frozenset[str]
    up: Callable[[sqlite3.Connection], None]


def discover_migrations(
    migrations_dir: Path, *, verbose: bool = True
) -> list[Migration]:
    """Return every valid migration in ``migrations_dir``, ordered by version.

    Files that don't match ``NNN_name.py`` are ignored silently. Files
    that match the pattern but fail validation (missing ``up`` or
    ``CRR_TABLES``, or ``CRR_TABLES`` names a table not in the manifest)
    are skipped — never applied. This tolerates historical artifacts
    like the deprecated ``001_add_review_status.py`` without
    special-casing their names.

    With ``verbose=True`` (default, used from ``pt db migrate``) a
    stderr warning is printed for each skipped file so the operator
    sees authoring bugs. With ``verbose=False`` the same files are
    skipped silently — used from the pt-startup unapplied-migration
    check, where a skip warning on every CLI call would be noise.
    """
    migrations: list[Migration] = []
    seen_versions: dict[int, Path] = {}

    for path in sorted(migrations_dir.iterdir()):
        if not path.is_file():
            continue
        match = MIGRATION_FILENAME_RE.match(path.name)
        if not match:
            continue

        version = int(match.group(1))
        name = match.group(2)

        if version in seen_versions:
            raise MigrationError(
                f"Duplicate migration version {version:03d}: "
                f"{seen_versions[version].name} and {path.name}. "
                "Every migration needs a unique version number."
            )
        seen_versions[version] = path

        try:
            migration = _load_migration_module(version, name, path)
        except MigrationError as err:
            if verbose:
                print(
                    f"migration_runner: skipping {path.name} ({err})",
                    file=sys.stderr,
                )
            continue
        migrations.append(migration)

    migrations.sort(key=lambda m: m.version)
    return migrations


def _load_migration_module(version: int, name: str, path: Path) -> Migration:
    """Import one migration file and validate its exported contract.

    Raises ``MigrationError`` for any contract violation — missing
    symbols, wrong types, or CRR-table declarations that don't line up
    with ``crr_manifest.CRR_TABLES``.
    """
    spec = importlib.util.spec_from_file_location(
        f"_pt_migration_{version:03d}", path
    )
    if spec is None or spec.loader is None:
        raise MigrationError(f"cannot load spec for {path.name}")

    module: ModuleType = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise MigrationError(f"import failed: {exc!r}") from exc

    up = getattr(module, "up", None)
    if not callable(up):
        raise MigrationError("missing or non-callable up(conn)")

    crr_tables = getattr(module, "CRR_TABLES", None)
    if not isinstance(crr_tables, frozenset):
        raise MigrationError(
            "missing or non-frozenset CRR_TABLES declaration"
        )

    for bad in (t for t in crr_tables if not isinstance(t, str) or not t):
        raise MigrationError(
            f"CRR_TABLES contains invalid table name: {bad!r}"
        )

    unknown = crr_tables - MANIFEST_CRR_TABLES
    if unknown:
        raise MigrationError(
            "CRR_TABLES names tables not classified as CRR in "
            f"crr_manifest.py: {sorted(unknown)}. Either fix the typo "
            "or update the manifest — the runner refuses to guess."
        )

    return Migration(
        version=version,
        name=name,
        path=path,
        crr_tables=crr_tables,
        up=cast(Callable[[sqlite3.Connection], None], up),
    )


def applied_versions(conn: sqlite3.Connection) -> set[int]:
    """Return the set of migration versions already recorded as applied.

    Before the first migration runs the ``schema_migrations`` ledger
    doesn't exist yet — return an empty set so the bootstrap migration
    (the one that creates the ledger) isn't mistaken for already-applied.

    Only the specific "no such table: schema_migrations" case is
    swallowed. Other ``OperationalError`` cases (database locked, disk
    full, corruption) propagate — silencing them would let the runner
    re-attempt every migration and surface as a confusing IntegrityError
    on the PRIMARY KEY instead of the real cause.
    """
    try:
        cur = conn.execute("SELECT version FROM schema_migrations")
    except sqlite3.OperationalError as err:
        if "no such table" in str(err).lower():
            return set()
        raise
    return {row[0] for row in cur.fetchall()}


def unapplied_migrations(
    conn: sqlite3.Connection, migrations: Iterable[Migration]
) -> list[Migration]:
    """Filter ``migrations`` down to the ones not yet in ``schema_migrations``.

    Preserves the input order so the caller can apply them sequentially.
    """
    applied = applied_versions(conn)
    return [m for m in migrations if m.version not in applied]


def _crsql_loaded(conn: sqlite3.Connection) -> bool:
    """True if cr-sqlite is loaded on this connection."""
    try:
        conn.execute("SELECT crsql_dbversion()")
        return True
    except sqlite3.OperationalError:
        return False


def apply_migration(conn: sqlite3.Connection, migration: Migration) -> None:
    """Apply one migration inside a transaction with the §2.2 CRR wrapper.

    The sequence is:

    1. ``BEGIN``
    2. For each ``t`` in ``migration.crr_tables`` (only if cr-sqlite is
       loaded): ``SELECT crsql_begin_alter(?)``.
    3. ``migration.up(conn)`` — the migration's DDL.
    4. For each ``t`` in ``migration.crr_tables`` (only if cr-sqlite is
       loaded): ``SELECT crsql_commit_alter(?)``.
    5. Insert the row into ``schema_migrations`` (inside the same
       transaction so "applied" and "recorded" commit atomically).
    6. ``COMMIT``.

    On any exception we ``ROLLBACK``. SQLite's rollback unwinds the DDL
    and the ledger insert. cr-sqlite's docs need verification that its
    CRR metadata unwinds with the same rollback — that's the §2.2
    pre-ship check, gated by the 2.4 trial. Until cr-sqlite is loaded,
    the ``crsql_*`` calls are skipped, so the failure mode is the
    standard SQL-only transaction rollback.
    """
    crsql_on = _crsql_loaded(conn)
    applied_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    conn.execute("BEGIN")
    try:
        if crsql_on:
            for t in migration.crr_tables:
                conn.execute("SELECT crsql_begin_alter(?)", (t,))

        migration.up(conn)

        if crsql_on:
            for t in migration.crr_tables:
                conn.execute("SELECT crsql_commit_alter(?)", (t,))

        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) "
            "VALUES (?, ?, ?)",
            (migration.version, migration.name, applied_at),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def apply_all(
    conn: sqlite3.Connection, migrations_dir: Path
) -> list[Migration]:
    """Discover, filter, and apply every pending migration in order.

    Returns the list of migrations that were applied in this call
    (possibly empty). Raises immediately on the first failure — the
    transaction rollback in ``apply_migration`` keeps the DB consistent,
    but subsequent migrations are **not** attempted. The operator fixes
    the failure and re-runs.
    """
    migrations = discover_migrations(migrations_dir)
    pending = unapplied_migrations(conn, migrations)
    for migration in pending:
        apply_migration(conn, migration)
    return pending
