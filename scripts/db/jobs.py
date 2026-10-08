"""Local job listings and submission history for the dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .job_ranking import ranked_split


JOB_CATEGORIES = frozenset({
    "Frontend/React", "Full Stack", "Forward Deployed / Solutions",
    "SEO", "Backend", "Other",
})
JOB_SOURCES = frozenset({"ats_sweep", "hn", "manual"})
# 'volunteer' rows live on /jobs/volunteer and never in Jobs listings,
# stats or submissions (#101668605654102016).
JOB_KINDS = frozenset({"job", "volunteer"})

_OPEN = """j.deleted_at IS NULL AND NOT EXISTS (
             SELECT 1 FROM job_submissions AS s WHERE s.job_id = j.id)"""


def _has_kind_columns(conn: Any) -> bool:
    """True once migration 016 has added jobs.kind and jobs.volunteering_since.

    Numbered migrations reach an existing database only through
    `pt db migrate`, which takes a verified backup first; neither the
    dashboard nor `pt` applies them at startup. Until an operator runs it,
    every row is a job and none has a volunteering date, so the Jobs page
    keeps working and the Volunteer page is empty instead of a 500.
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    return {"kind", "volunteering_since"} <= columns


def _kind_sql(conn: Any) -> tuple[str, str]:
    """SQL for ``j.kind`` and ``j.volunteering_since``, as literals before 016."""
    if _has_kind_columns(conn):
        return "j.kind", "j.volunteering_since"
    return "'job'", "NULL"


class JobsMixin:
    """Job operations exposed through the shared DatabaseManager."""

    def upsert_job(
        self, *, company: str, title: str, url: str, source: str,
        location: str | None = None, posted_date: str | None = None,
        category: str = "Other", raw: str | None = None,
        kind: str | None = None,
    ) -> dict[str, Any]:
        """Update a URL's listing without changing first-seen or dismissal state.

        ``kind`` defaults to 'job' for a new row; omitting it on a later
        import keeps whatever kind the row already has.
        """
        company, title, url = company.strip(), title.strip(), url.strip()
        if not company or not title or not url:
            raise ValueError("company, title and url are required")
        if source not in JOB_SOURCES:
            raise ValueError("invalid job source")
        if category not in JOB_CATEGORIES:
            raise ValueError("invalid job category")
        if kind is not None and kind not in JOB_KINDS:
            raise ValueError("invalid job kind")
        first_seen = datetime.now(timezone.utc).date().isoformat()
        with self._db._get_conn() as conn:
            migrated = _has_kind_columns(conn)
            if not migrated and kind == "volunteer":
                raise ValueError(
                    "kind 'volunteer' needs migration 016; run `pt db migrate`"
                )
            kind_column = ", kind" if migrated else ""
            kind_value = ", COALESCE(?, 'job')" if migrated else ""
            kind_update = ", kind=COALESCE(?, jobs.kind)" if migrated else ""
            conn.execute(
                f"""INSERT INTO jobs
                   (company, title, location, url, source, posted_date,
                    first_seen, category, raw{kind_column})
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?{kind_value})
                   ON CONFLICT(url) DO UPDATE SET
                     company=excluded.company, title=excluded.title,
                     location=COALESCE(excluded.location, jobs.location),
                     source=excluded.source,
                     posted_date=COALESCE(excluded.posted_date, jobs.posted_date),
                     category=excluded.category,
                     raw=COALESCE(excluded.raw, jobs.raw){kind_update}""",
                (company, title, location, url, source, posted_date,
                 first_seen, category, raw) + ((kind, kind) if migrated else ()),
            )
            row = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
            conn.commit()
            return dict(row)

    def get_open_jobs(self, kind: str = "job") -> list[dict[str, Any]]:
        """Listings of one kind neither dismissed nor submitted, newest first."""
        with self._db._get_conn() as conn:
            kind_sql, since_sql = _kind_sql(conn)
            rows = conn.execute(
                f"""SELECT j.* FROM jobs AS j
                    WHERE {kind_sql} = ? AND {since_sql} IS NULL AND {_OPEN}
                    ORDER BY j.first_seen DESC, j.id DESC""",
                (kind,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_ranked_open_jobs(self, kind: str = "job") -> dict[str, list[dict[str, Any]]]:
        """Open listings ranked by fit, split into fresh and stale (#101679546294759424)."""
        today = datetime.now(timezone.utc).date()
        return ranked_split(self.get_open_jobs(kind), today)

    def get_volunteer_roles(self) -> dict[str, Any]:
        """The Volunteer page: current, applied, and ranked possible roles.

        A role with volunteering_since is Current whether or not it was ever
        submitted; Applied and Possible both exclude it.
        """
        with self._db._get_conn() as conn:
            migration_pending = not _has_kind_columns(conn)
            kind_sql, since_sql = _kind_sql(conn)
            current = conn.execute(
                f"""SELECT j.* FROM jobs AS j
                    WHERE {kind_sql} = 'volunteer' AND j.deleted_at IS NULL
                      AND {since_sql} IS NOT NULL
                    ORDER BY {since_sql} DESC, j.id DESC"""
            ).fetchall()
            applied = conn.execute(
                f"""SELECT j.*, MAX(s.submitted_at) AS last_submitted_at
                    FROM jobs AS j JOIN job_submissions AS s ON s.job_id = j.id
                    WHERE {kind_sql} = 'volunteer' AND j.deleted_at IS NULL
                      AND {since_sql} IS NULL
                    GROUP BY j.id ORDER BY last_submitted_at DESC, j.id DESC"""
            ).fetchall()
        possible = self.get_ranked_open_jobs("volunteer")
        return {
            "migration_pending": migration_pending,
            "current": [dict(row) for row in current],
            "applied": [dict(row) for row in applied],
            "possible": possible["fresh"],
            "possible_stale": possible["stale"],
        }

    def start_volunteering(self, job_id: int) -> dict[str, Any] | None:
        """Stamp volunteering_since once; None for a missing or dismissed volunteer role."""
        with self._db._get_conn() as conn:
            if not _has_kind_columns(conn):
                return None
            conn.execute(
                """UPDATE jobs SET volunteering_since = ?
                   WHERE id = ? AND kind = 'volunteer' AND deleted_at IS NULL
                     AND volunteering_since IS NULL""",
                (datetime.now(timezone.utc).isoformat(), job_id),
            )
            row = conn.execute(
                """SELECT * FROM jobs
                   WHERE id = ? AND kind = 'volunteer' AND deleted_at IS NULL""",
                (job_id,),
            ).fetchone()
            conn.commit()
            return dict(row) if row else None

    def soft_delete_job(self, job_id: int) -> dict[str, Any] | None:
        """Dismiss a listing while keeping its row and submission history."""
        with self._db._get_conn() as conn:
            cursor = conn.execute(
                """UPDATE jobs SET deleted_at = ?
                   WHERE id = ? AND deleted_at IS NULL""",
                (datetime.now(timezone.utc).isoformat(), job_id),
            )
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            conn.commit()
            return dict(row) if cursor.rowcount and row else None

    def add_job_submission(
        self, job_id: int, *, submitted_at: str | None = None,
        resume_path: str | None = None, cover_letter_path: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any] | None:
        """Append one submission; a later submission never replaces an earlier one."""
        supplied = submitted_at or datetime.now(timezone.utc).isoformat()
        try:
            parsed = datetime.fromisoformat(supplied.replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid submitted_at date") from exc
        # A date-only historical entry is midnight UTC; explicit offsets are
        # converted before storage so text ordering matches chronological order.
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        timestamp = parsed.astimezone(timezone.utc).isoformat()
        with self._db._get_conn() as conn:
            job = conn.execute(
                "SELECT id FROM jobs WHERE id = ? AND deleted_at IS NULL", (job_id,)
            ).fetchone()
            if job is None:
                return None
            cursor = conn.execute(
                """INSERT INTO job_submissions
                   (job_id, submitted_at, resume_path, cover_letter_path, notes)
                   VALUES (?, ?, ?, ?, ?)""",
                (job_id, timestamp, resume_path, cover_letter_path, notes),
            )
            row = conn.execute(
                "SELECT * FROM job_submissions WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            conn.commit()
            return dict(row)

    def get_submitted_jobs(self) -> list[dict[str, Any]]:
        """Group every submission under its listing, latest activity first."""
        with self._db._get_conn() as conn:
            kind_sql, _ = _kind_sql(conn)
            rows = conn.execute(
                f"""SELECT j.*, s.id AS submission_id, s.submitted_at,
                          s.resume_path, s.cover_letter_path, s.notes
                   FROM jobs AS j JOIN job_submissions AS s ON s.job_id = j.id
                   WHERE {kind_sql} = 'job'
                   ORDER BY s.submitted_at DESC, s.id DESC"""
            ).fetchall()
        groups: dict[int, dict[str, Any]] = {}
        for row in rows:
            record = dict(row)
            job_id = record["id"]
            if job_id not in groups:
                groups[job_id] = {
                    "job": {key: record[key] for key in (
                        "id", "company", "title", "location", "url", "source",
                        "posted_date", "first_seen", "category", "raw", "deleted_at",
                    )},
                    "submissions": [],
                }
            groups[job_id]["submissions"].append({
                "id": record["submission_id"], "job_id": job_id,
                "submitted_at": record["submitted_at"],
                "resume_path": record["resume_path"],
                "cover_letter_path": record["cover_letter_path"],
                "notes": record["notes"],
            })
        return list(groups.values())

    def get_job_stats(self) -> dict[str, list[dict[str, Any]]]:
        """Discovery/submission history and current open category counts."""
        with self._db._get_conn() as conn:
            kind_sql, _ = _kind_sql(conn)
            jobs = conn.execute(
                f"""SELECT j.first_seen AS date, COUNT(*) AS count FROM jobs AS j
                    WHERE {kind_sql} = 'job' GROUP BY j.first_seen ORDER BY j.first_seen"""
            ).fetchall()
            submissions = conn.execute(
                f"""SELECT substr(s.submitted_at, 1, 10) AS date, COUNT(*) AS count
                   FROM job_submissions AS s JOIN jobs AS j ON j.id = s.job_id
                   WHERE {kind_sql} = 'job'
                   GROUP BY substr(s.submitted_at, 1, 10) ORDER BY date"""
            ).fetchall()
            categories = conn.execute(
                f"""SELECT j.category, COUNT(*) AS count FROM jobs AS j
                    WHERE {kind_sql} = 'job' AND {_OPEN}
                    GROUP BY j.category ORDER BY count DESC, j.category"""
            ).fetchall()
            return {
                "jobs_per_day": [dict(row) for row in jobs],
                "submissions_per_day": [dict(row) for row in submissions],
                "categories": [dict(row) for row in categories],
            }
