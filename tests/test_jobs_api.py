"""Jobs API contract: dismissal preserves history and submissions remain repeatable."""

from fastapi.testclient import TestClient

from dashboard.app import app


def _job(db, suffix: str, category: str = "Other") -> dict:
    return db.upsert_job(
        company=f"Company {suffix}", title=f"Engineer {suffix}",
        url=f"https://example.test/jobs/{suffix}", source="manual",
        category=category, raw=f"Original posting {suffix}",
    )


def test_open_jobs_excludes_submitted_and_dismissed_without_erasing_rows(db):
    client = TestClient(app)
    open_job = _job(db, "open", "Frontend/React")
    submitted = _job(db, "submitted")
    dismissed = _job(db, "dismissed")

    response = client.post(
        f"/api/jobs/{submitted['id']}/submissions",
        json={"submitted_at": "2026-09-22T15:00:00+00:00"},
    )
    assert response.status_code == 201, response.text
    response = client.delete(f"/api/jobs/{dismissed['id']}")
    assert response.status_code == 200, response.text
    assert response.json()["job"]["deleted_at"]

    response = client.get("/api/jobs")
    assert response.status_code == 200, response.text
    assert [row["id"] for row in response.json()["jobs"]] == [open_job["id"]]
    assert client.get("/api/jobs/stats").json()["categories"] == [
        {"category": "Frontend/React", "count": 1}
    ]
    with db._db._get_conn() as conn:
        ids = {row[0] for row in conn.execute("SELECT id FROM jobs")}
    assert ids == {open_job["id"], submitted["id"], dismissed["id"]}

    # A refresh cannot silently resurrect Erik's dismissed listing.
    refreshed = _job(db, "dismissed")
    assert refreshed["id"] == dismissed["id"]
    assert refreshed["deleted_at"] is not None


def test_repeat_submissions_are_grouped_newest_first_and_counted(db):
    client = TestClient(app)
    job = _job(db, "repeat", "Backend")
    for timestamp in ("2026-09-20T12:00:00+00:00", "2026-09-23T12:00:00+00:00"):
        response = client.post(
            f"/api/jobs/{job['id']}/submissions",
            json={"submitted_at": timestamp, "resume_path": "applications/repeat/resume.md"},
        )
        assert response.status_code == 201, response.text

    groups = client.get("/api/jobs/submissions").json()["jobs"]
    assert len(groups) == 1
    assert groups[0]["job"]["id"] == job["id"]
    assert [s["submitted_at"][:10] for s in groups[0]["submissions"]] == [
        "2026-09-23", "2026-09-20"
    ]
    assert groups[0]["submissions"][0]["id"] != groups[0]["submissions"][1]["id"]
    assert all(s["resume_path"] == "applications/repeat/resume.md" for s in groups[0]["submissions"])

    stats = client.get("/api/jobs/stats").json()
    assert stats["submissions_per_day"] == [
        {"date": "2026-09-20", "count": 1},
        {"date": "2026-09-23", "count": 1},
    ]
    assert stats["categories"] == []  # submitted jobs are no longer open prospects
    assert sum(row["count"] for row in stats["jobs_per_day"]) == 1


def test_unknown_and_invalid_submissions_do_not_create_history(db):
    client = TestClient(app)
    job = _job(db, "validation")
    assert client.delete("/api/jobs/999999").status_code == 404
    assert client.post("/api/jobs/999999/submissions", json={}).status_code == 404
    bad = client.post(
        f"/api/jobs/{job['id']}/submissions", json={"submitted_at": "not-a-date"}
    )
    assert bad.status_code == 400
    assert client.get("/api/jobs/submissions").json()["jobs"] == []


def test_upsert_preserves_first_seen_and_rejects_unbounded_categories(db):
    first = _job(db, "same", "Other")
    with db._db._get_conn() as conn:
        conn.execute("UPDATE jobs SET first_seen = ? WHERE id = ?", ("2026-09-01", first["id"]))
        conn.commit()
    revised = db.upsert_job(
        company="Revised Company", title="Revised role",
        url=first["url"], source="manual", category="SEO",
    )
    assert revised["id"] == first["id"]
    assert revised["first_seen"] == "2026-09-01"
    assert revised["company"] == "Revised Company"
    assert revised["category"] == "SEO"
    assert revised["raw"] == first["raw"]

    import pytest
    with pytest.raises(ValueError, match="invalid job category"):
        db.upsert_job(company="A", title="B", url="https://example.test/new", source="manual", category="Novel")
