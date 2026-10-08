"""Codebase size snapshot storage for `pt size` (#8083).

Scanning and scoring live in ``scripts/codebase_size.py`` and have no database
code; this mixin only stores and reads ``codebase_size_snapshots``.

The table is append-only. Rows are never updated or deleted (migration 017
adds triggers that abort either), so nothing here can lose a measurement:

- Each ``pt size --snapshot`` inserts one complete scan run under a new
  ``run_id`` in a single transaction. A same-day re-run adds another run;
  readers use the newest run, so a stored scan is always one whole
  measurement, never a mix of two.
- The baseline is a single ``kind='baseline'`` run dated
  ``BASELINE_DATE``. Importing it a second time, or for any other date, is
  refused here and by the database itself (a CHECK on the date, a trigger
  refusing a second baseline run, a unique index per project), so a race
  between two imports cannot replace it.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

_INSERT = """
    INSERT INTO codebase_size_snapshots
        (run_id, kind, snapshot_date, project, code_lines, test_lines,
         doc_files, doc_lines, last_commit, commits_90d, scanned_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_COLUMNS = (
    "project, code_lines, test_lines, doc_files, doc_lines, last_commit, commits_90d"
)


def _check_rows(rows: list) -> None:
    """Refuse a set that is not one complete measurement, before any write."""
    if not rows:
        raise ValueError("refusing to store an empty snapshot")
    bad = [r.project for r in rows if r.error]
    if bad:
        raise ValueError(f"refusing to store errored repos: {', '.join(bad)}")
    projects = [r.project for r in rows]
    dupes = sorted({p for p in projects if projects.count(p) > 1})
    if dupes:
        raise ValueError(f"refusing to store duplicate repos: {', '.join(dupes)}")


def _insert_run(conn, rows: list, kind: str, snapshot_date: str) -> str:
    run_id = uuid.uuid4().hex
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for r in rows:
        conn.execute(_INSERT, (
            run_id, kind, snapshot_date, r.project, r.code, r.tests,
            r.doc_files, r.doc_lines, r.last_commit, r.commits_90d, stamp,
        ))
    return run_id


class CodebaseSizeMixin:
    """Codebase size snapshot operations exposed through the shared DatabaseManager."""

    def save_codebase_scan(self, rows: Iterable, snapshot_date: str) -> str:
        """Append ``rows`` as one new scan run, atomically; return its run_id.

        Errored rows, duplicates and an empty set are refused before any
        write: an unmeasured repo must not be stored as zero lines.
        """
        rows = list(rows)
        _check_rows(rows)
        with self._db._get_conn() as conn:
            run_id = _insert_run(conn, rows, "scan", snapshot_date)
            conn.commit()
        return run_id

    def _codebase_run(self, kind: str):
        from scripts.codebase_size import RepoSize

        with self._db._get_conn() as conn:
            newest = conn.execute(
                "SELECT run_id, snapshot_date FROM codebase_size_snapshots "
                "WHERE kind = ? ORDER BY id DESC LIMIT 1",
                (kind,),
            ).fetchone()
            if newest is None:
                return None, {}
            run_id, date = newest[0], newest[1]
            found = conn.execute(
                f"SELECT {_COLUMNS} FROM codebase_size_snapshots WHERE run_id = ?",
                (run_id,),
            ).fetchall()
            return date, {r[0]: RepoSize(*tuple(r)) for r in found}

    def codebase_latest_scan(self):
        """(date, {project: RepoSize}) of the newest scan run."""
        return self._codebase_run("scan")

    def codebase_baseline(self):
        """(date, {project: RepoSize}) of the baseline run, or (None, {})."""
        return self._codebase_run("baseline")

    def import_codebase_baseline(self, file: Path, at: str, root: Optional[Path] = None) -> list:
        """Verify FILE against git history at ``at``, then store it as the baseline.

        Refused, with nothing written, when ``at`` is not on BASELINE_DATE, when
        a baseline already exists (it is immutable), or when any repo is
        unknown or differs from git history (BaselineMismatch).
        """
        from scripts import codebase_size as cs

        date = cs.baseline_date(at)
        if date != cs.BASELINE_DATE:
            raise ValueError(
                f"the baseline is pinned to {cs.BASELINE_DATE}; --at {at} is {date}"
            )
        if self.codebase_baseline()[0] is not None:
            raise ValueError("a baseline is already stored and is immutable")
        rebuilt = cs.verify_baseline(file, at, root)
        _check_rows(rebuilt)
        try:
            with self._db._get_conn() as conn:
                _insert_run(conn, rebuilt, "baseline", date)
                conn.commit()
        except sqlite3.IntegrityError as exc:
            # Another import stored a baseline after the check above: the
            # database's trigger and unique index refused this one whole.
            raise ValueError("a baseline is already stored and is immutable") from exc
        return rebuilt
