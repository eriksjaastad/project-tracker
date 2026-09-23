"""Local job listings and submission history for the dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


JOB_CATEGORIES = frozenset({
    "Frontend/React", "Full Stack", "Forward Deployed / Solutions",
    "SEO", "Backend", "Other",
})
JOB_SOURCES = frozenset({"ats_sweep", "hn", "manual"})


class JobsMixin:
    """Job operations exposed through the shared DatabaseManager."""

    def upsert_job(
        self, *, company: str, title: str, url: str, source: str,
        location: str | None = None, posted_date: str | None = None,
        category: str = "Other", raw: str | None = None,
    ) -> dict[str, Any]:
        """Update a URL's listing without changing first-seen or dismissal state."""
        company, title, url = company.strip(), title.strip(), url.strip()
        if not company or not title or not url:
            raise ValueError("company, title and url are required")
        if source not in JOB_SOURCES:
            raise ValueError("invalid job source")
        if category not in JOB_CATEGORIES:
            raise ValueError("invalid job category")
        first_seen = datetime.now(timezone.utc).date().isoformat()
        with self._db._get_conn() as conn:
            conn.execute(
                """INSERT INTO jobs
                   (company, title, location, url, source, posted_date,
                    first_seen, category, raw)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(url) DO UPDATE SET
                     company=excluded.company, title=excluded.title,
                     location=COALESCE(excluded.location, jobs.location),
                     source=excluded.source,
                     posted_date=COALESCE(excluded.posted_date, jobs.posted_date),
                     category=excluded.category,
                     raw=COALESCE(excluded.raw, jobs.raw)""",
                (company, title, location, url, source, posted_date,
                 first_seen, category, raw),
            )
            row = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
            conn.commit()
            return dict(row)

    def get_open_jobs(self) -> list[dict[str, Any]]:
        """Listings neither dismissed nor submitted, newest first."""
        with self._db._get_conn() as conn:
            rows = conn.execute(
                """SELECT j.* FROM jobs AS j
                   WHERE j.deleted_at IS NULL
                     AND NOT EXISTS (
                       SELECT 1 FROM job_submissions AS s WHERE s.job_id = j.id
                     )
                   ORDER BY j.first_seen DESC, j.id DESC"""
            ).fetchall()
            return [dict(row) for row in rows]

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
        timestamp = submitted_at or datetime.now(timezone.utc).isoformat()
        try:
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid submitted_at date") from exc
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
            rows = conn.execute(
                """SELECT j.*, s.id AS submission_id, s.submitted_at,
                          s.resume_path, s.cover_letter_path, s.notes
                   FROM jobs AS j JOIN job_submissions AS s ON s.job_id = j.id
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
            jobs = conn.execute(
                """SELECT first_seen AS date, COUNT(*) AS count FROM jobs
                   GROUP BY first_seen ORDER BY first_seen"""
            ).fetchall()
            submissions = conn.execute(
                """SELECT substr(submitted_at, 1, 10) AS date, COUNT(*) AS count
                   FROM job_submissions GROUP BY substr(submitted_at, 1, 10)
                   ORDER BY date"""
            ).fetchall()
            categories = conn.execute(
                """SELECT j.category, COUNT(*) AS count FROM jobs AS j
                   WHERE j.deleted_at IS NULL AND NOT EXISTS (
                     SELECT 1 FROM job_submissions AS s WHERE s.job_id = j.id
                   ) GROUP BY j.category ORDER BY count DESC, j.category"""
            ).fetchall()
            return {
                "jobs_per_day": [dict(row) for row in jobs],
                "submissions_per_day": [dict(row) for row in submissions],
                "categories": [dict(row) for row in categories],
            }
