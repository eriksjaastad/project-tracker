"""The jobs migration preserves existing data and creates local-only tables."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from db.crr_manifest import (  # noqa: E402
    CRR_TABLES,
    LOCAL_ONLY_TABLES,
    assert_tables_classified,
)
from db.migration_runner import discover_migrations  # noqa: E402
from db.schema import ensure_schema  # noqa: E402


MIGRATIONS_DIR = Path(__file__).parent.parent / "scripts" / "db" / "migrations"


def _migration_up(conn: sqlite3.Connection) -> None:
    migration = next(
        m for m in discover_migrations(MIGRATIONS_DIR) if m.version == 13
    )
    assert migration.crr_tables == frozenset()
    migration.up(conn)


def test_jobs_migration_is_additive_idempotent_and_preserves_existing_data(
    tmp_path: Path,
) -> None:
    original = sqlite3.connect(tmp_path / "original.db")
    original.execute("CREATE TABLE existing_record (value TEXT NOT NULL)")
    original.execute("INSERT INTO existing_record VALUES ('retained')")
    original.commit()
    copy = sqlite3.connect(tmp_path / "copy.db")
    original.backup(copy)
    original.close()

    _migration_up(copy)
    _migration_up(copy)
    assert copy.execute("SELECT value FROM existing_record").fetchall() == [
        ("retained",)
    ]
    assert {
        row[0]
        for row in copy.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    } >= {"jobs", "job_submissions", "existing_record"}
    copy.close()


def test_jobs_constraints_and_repeat_submissions(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "jobs.db")
    conn.execute("PRAGMA foreign_keys = ON")
    _migration_up(conn)
    conn.execute(
        "INSERT INTO jobs (company, title, url) VALUES (?, ?, ?)",
        ("Example", "Engineer", "https://example.test/jobs/1"),
    )
    job_id = conn.execute("SELECT id FROM jobs").fetchone()[0]
    conn.executemany(
        "INSERT INTO job_submissions (job_id, submitted_at) VALUES (?, ?)",
        [(job_id, "2026-09-22T12:00:00Z"), (job_id, "2026-09-23T12:00:00Z")],
    )
    _migration_up(conn)
    assert conn.execute(
        "SELECT submitted_at FROM job_submissions ORDER BY submitted_at"
    ).fetchall() == [
        ("2026-09-22T12:00:00Z",),
        ("2026-09-23T12:00:00Z",),
    ]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO jobs (company, title, url) VALUES (?, ?, ?)",
            ("Other", "Engineer", "https://example.test/jobs/1"),
        )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO jobs (company, title, url, category) VALUES (?, ?, ?, ?)",
            ("Other", "Engineer", "https://example.test/jobs/2", "Unbounded"),
        )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO job_submissions (job_id, submitted_at) VALUES (?, ?)",
            (999, "2026-09-23T12:00:00Z"),
        )
    assert conn.execute("PRAGMA foreign_key_list(job_submissions)").fetchall() == [
        (0, 0, "jobs", "job_id", "id", "NO ACTION", "NO ACTION", "NONE")
    ]
    assert conn.execute("SELECT COUNT(*) FROM job_submissions").fetchone()[0] == 2
    conn.close()


def test_fresh_schema_matches_migration_and_manifest() -> None:
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn.cursor())
    _migration_up(conn)
    assert {"jobs", "job_submissions"} <= LOCAL_ONLY_TABLES
    assert not ({"jobs", "job_submissions"} & CRR_TABLES)
    assert_tables_classified(conn)
    migrated = sqlite3.connect(":memory:")
    _migration_up(migrated)
    for table in ("jobs", "job_submissions"):
        assert conn.execute(f"PRAGMA table_info({table})").fetchall() == (
            migrated.execute(f"PRAGMA table_info({table})").fetchall()
        )
        assert conn.execute(f"PRAGMA index_list({table})").fetchall() == (
            migrated.execute(f"PRAGMA index_list({table})").fetchall()
        )
    conn.close()
    migrated.close()
