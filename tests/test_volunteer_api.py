"""Volunteer tab (#101668605654102016): sections, transitions, and isolation from Jobs."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from dashboard.app import app


def _role(db, suffix: str, kind: str = "volunteer", title: str = "", **extra) -> dict:
    return db.upsert_job(
        company=f"Org {suffix}", title=title or f"Role {suffix}",
        url=f"https://example.test/volunteer/{suffix}", source="manual",
        kind=kind, **extra,
    )


def test_volunteer_rows_never_reach_jobs_listings_stats_or_submissions(db) -> None:
    client = TestClient(app)
    job = _role(db, "job", kind="job", category="Frontend/React")
    possible = _role(db, "possible", category="Frontend/React")
    applied = _role(db, "applied")
    assert client.post(f"/api/jobs/{applied['id']}/submissions", json={
        "submitted_at": "2026-10-01T12:00:00+00:00"}).status_code == 201

    body = client.get("/api/jobs").json()
    assert [row["id"] for row in body["jobs"] + body["stale"]] == [job["id"]]
    assert client.get("/api/jobs/submissions").json()["jobs"] == []
    stats = client.get("/api/jobs/stats").json()
    assert stats["categories"] == [{"category": "Frontend/React", "count": 1}]
    assert stats["submissions_per_day"] == []
    assert sum(row["count"] for row in stats["jobs_per_day"]) == 1
    # Volunteer roles cannot be sent to the resume-tailoring agent either.
    assert client.post(f"/api/jobs/{possible['id']}/agent-prompt").status_code == 404


def test_volunteer_sections_and_started_volunteering_transition(db) -> None:
    client = TestClient(app)
    _role(db, "job", kind="job")
    possible = _role(db, "possible", title="Website volunteer (WordPress)")
    other = _role(db, "other")
    dismissed = _role(db, "dismissed")
    old = _role(db, "old", posted_date=(date.today() - timedelta(days=45)).isoformat())
    applied = _role(db, "applied")
    client.delete(f"/api/jobs/{dismissed['id']}")
    client.post(f"/api/jobs/{applied['id']}/submissions", json={})

    body = client.get("/api/volunteer").json()
    assert body["current"] == []
    assert [row["id"] for row in body["applied"]] == [applied["id"]]
    assert body["applied"][0]["last_submitted_at"]
    # Ranked: the WordPress role outranks the plain one.
    assert [row["id"] for row in body["possible"]] == [possible["id"], other["id"]]
    assert [row["id"] for row in body["possible_stale"]] == [old["id"]]

    response = client.post(f"/api/jobs/{applied['id']}/volunteering")
    assert response.status_code == 200, response.text
    since = response.json()["job"]["volunteering_since"]
    assert since

    body = client.get("/api/volunteer").json()
    assert [row["id"] for row in body["current"]] == [applied["id"]]
    assert body["applied"] == []

    # Repeating the click keeps the original start date.
    again = client.post(f"/api/jobs/{applied['id']}/volunteering").json()["job"]
    assert again["volunteering_since"] == since


@pytest.mark.parametrize("target", ["job", "missing"])
def test_started_volunteering_rejects_non_volunteer_rows(db, target: str) -> None:
    client = TestClient(app)
    job_id = _role(db, "job", kind="job")["id"] if target == "job" else 999_999
    assert client.post(f"/api/jobs/{job_id}/volunteering").status_code == 404
    if target == "job":
        assert db.get_open_jobs()[0]["volunteering_since"] is None


def test_upsert_rejects_unknown_kind_and_keeps_kind_when_omitted(db) -> None:
    with pytest.raises(ValueError, match="kind"):
        _role(db, "bad", kind="gig")
    role = _role(db, "keep")
    refreshed = db.upsert_job(company="Org keep", title="Role keep", source="manual",
                              url=role["url"])
    assert refreshed["kind"] == "volunteer"


def test_dismissed_volunteer_roles_leave_every_section(db) -> None:
    client = TestClient(app)
    applied = _role(db, "applied")
    current = _role(db, "current")
    for role in (applied, current):
        assert client.post(f"/api/jobs/{role['id']}/submissions", json={}).status_code == 201
    assert client.post(f"/api/jobs/{current['id']}/volunteering").status_code == 200
    for role in (applied, current):
        assert client.delete(f"/api/jobs/{role['id']}").status_code == 200

    body = client.get("/api/volunteer").json()
    assert body == {"migration_pending": False, "current": [], "applied": [], "possible": [], "possible_stale": []}


def test_started_volunteering_rejects_dismissed_role(db) -> None:
    client = TestClient(app)
    role = _role(db, "dismissed")
    assert client.delete(f"/api/jobs/{role['id']}").status_code == 200
    assert client.post(f"/api/jobs/{role['id']}/volunteering").status_code == 404
    with db._db._get_conn() as conn:
        row = conn.execute(
            "SELECT volunteering_since FROM jobs WHERE id = ?", (role["id"],)
        ).fetchone()
    assert row[0] is None


def test_possible_role_goes_straight_to_current_without_an_application(db) -> None:
    client = TestClient(app)
    role = _role(db, "already")
    assert client.post(f"/api/jobs/{role['id']}/volunteering").status_code == 200
    body = client.get("/api/volunteer").json()
    assert [row["id"] for row in body["current"]] == [role["id"]]
    assert body["applied"] == [] and body["possible"] == [] and body["possible_stale"] == []
