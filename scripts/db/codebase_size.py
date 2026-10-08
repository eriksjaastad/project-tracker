"""Codebase size snapshot storage for `pt size` (#8083).

Scanning and scoring live in ``scripts/codebase_size.py`` and have no database
code; this mixin only stores and reads ``codebase_size_snapshots``. ``kind`` is
part of the unique key, so a scan taken on the baseline's date never
overwrites the baseline.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

KINDS = ("baseline", "scan")

_UPSERT = """
    INSERT INTO codebase_size_snapshots
        (snapshot_date, kind, project, code_lines, test_lines, doc_files,
         doc_lines, last_commit, commits_90d, scanned_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(snapshot_date, kind, project) DO UPDATE SET
        code_lines = excluded.code_lines,
        test_lines = excluded.test_lines,
        doc_files = excluded.doc_files,
        doc_lines = excluded.doc_lines,
        last_commit = excluded.last_commit,
        commits_90d = excluded.commits_90d,
        scanned_at = excluded.scanned_at
"""


def _store(conn, rows: list, kind: str, snapshot_date: str, scanned_at: Optional[str]) -> int:
    """Validate and upsert rows on an open connection. The caller commits."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")
    bad = [r.project for r in rows if r.error]
    if bad:
        raise ValueError(f"refusing to store errored repos: {', '.join(bad)}")
    stamp = scanned_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    for r in rows:
        conn.execute(_UPSERT, (
            snapshot_date, kind, r.project, r.code, r.tests, r.doc_files,
            r.doc_lines, r.last_commit, r.commits_90d, stamp,
        ))
    return len(rows)


class CodebaseSizeMixin:
    """Codebase size snapshot operations exposed through the shared DatabaseManager."""

    def save_codebase_snapshot(self, rows: Iterable, kind: str, snapshot_date: str,
                               scanned_at: Optional[str] = None) -> int:
        """Upsert one row per project for (snapshot_date, kind), atomically.

        Errored rows are refused: an unmeasured repo must not be stored as
        zero lines.
        """
        rows = list(rows)
        with self._db._get_conn() as conn:
            count = _store(conn, rows, kind, snapshot_date, scanned_at)
            conn.commit()
            return count

    def _latest_codebase(self, kind: str):
        from scripts.codebase_size import RepoSize

        with self._db._get_conn() as conn:
            date = conn.execute(
                "SELECT MAX(snapshot_date) FROM codebase_size_snapshots WHERE kind = ?",
                (kind,),
            ).fetchone()[0]
            if date is None:
                return None, {}
            found = conn.execute(
                "SELECT project, code_lines, test_lines, doc_files, doc_lines, "
                "last_commit, commits_90d FROM codebase_size_snapshots "
                "WHERE kind = ? AND snapshot_date = ?",
                (kind, date),
            ).fetchall()
            return date, {r[0]: RepoSize(*tuple(r)) for r in found}

    def codebase_latest_scan(self):
        """(date, {project: RepoSize}) of the newest kind='scan' snapshot."""
        return self._latest_codebase("scan")

    def codebase_baseline(self):
        """(date, {project: RepoSize}) of the newest kind='baseline' snapshot."""
        return self._latest_codebase("baseline")

    def import_codebase_baseline(self, file: Path, at: str, root: Optional[Path] = None) -> list:
        """Verify FILE against git history at ``at``, then store it as the baseline.

        Raises BaselineMismatch before touching the database if any repo is
        unknown or differs. Rows are stored in one transaction; a re-import for
        the same date replaces the earlier rows.
        """
        from scripts import codebase_size as cs

        rebuilt = cs.verify_baseline(file, at, root)
        with self._db._get_conn() as conn:
            _store(conn, rebuilt, "baseline", cs.baseline_date(at), None)
            conn.commit()
        return rebuilt
