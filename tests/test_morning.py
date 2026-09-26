from datetime import date

import pytest
from fastapi.testclient import TestClient

from dashboard.app import app
from dashboard.morning import (
    GITHUB_BLOB_BASE,
    MorningPlanError,
    load_hn_snapshots,
    morning_snapshot,
    parse_morning_plan,
)


SYNTHETIC_README = """\
# job-search

Preamble that should be ignored.

## Standing morning plan

**Plan intro.** Aim for a calm morning.

Read [the tracker](./applications/TRACKER.md) and `pt tasks -p job-search`.

| # | Channel | Time | What happens |
|---|---|---|---|
| 0 | Replies | 2 min | Check [replies](applications/TRACKER.md#replies) first. |
| 1 | Hacker News | 2 min | Open `hn-jobs-*-freelance.txt` snapshots. |
| 2 | Upwork | 10 min | **Screen** new posts and show up to five. |

Every lead shown carries its URL.

### Next morning

Run the table above. First review is Monday.

No new plan written yet.

## Layout

| Path | What |
|---|---|
| resume/ | Master resume |
"""


def test_parse_morning_plan_returns_intro_steps_and_next_morning():
    plan = parse_morning_plan(SYNTHETIC_README)

    assert len(plan["intro"]) == 2
    assert plan["intro"][0][0] == {"type": "strong", "text": "Plan intro."}
    intro_second = plan["intro"][1]
    assert {"type": "code", "text": "pt tasks -p job-search"} in intro_second
    link = next(seg for seg in intro_second if seg["type"] == "link")
    assert link == {
        "type": "link",
        "text": "the tracker",
        "href": f"{GITHUB_BLOB_BASE}/applications/TRACKER.md",
    }

    assert [step["number"] for step in plan["steps"]] == ["0", "1", "2"]
    assert plan["steps"][0]["channel"] == "Replies"
    assert plan["steps"][0]["time"] == "2 min"

    replies_link = next(
        seg for seg in plan["steps"][0]["description"] if seg["type"] == "link"
    )
    assert replies_link["href"] == (
        f"{GITHUB_BLOB_BASE}/applications/TRACKER.md#replies"
    )
    assert {
        "type": "code",
        "text": "hn-jobs-*-freelance.txt",
    } in plan["steps"][1]["description"]
    assert {"type": "strong", "text": "Screen"} in plan["steps"][2]["description"]

    assert len(plan["next_morning"]) == 2
    assert plan["next_morning"][0][0]["text"] == (
        "Run the table above. First review is Monday."
    )


def test_parse_morning_plan_absolute_and_mailto_links_unchanged():
    text = """\
## Standing morning plan

See [Contra](https://contra.com/) or [mail](mailto:admin@example.com).

| # | Channel | Time | What happens |
|---|---|---|---|
| 0 | Replies | 2 min | [A](https://example.com/a) and [B](mailto:b@example.com). |
"""
    plan = parse_morning_plan(text)

    assert plan["intro"][0][1]["href"] == "https://contra.com/"
    assert plan["intro"][0][3]["href"] == "mailto:admin@example.com"
    hrefs = {
        seg["href"] for seg in plan["steps"][0]["description"] if seg["type"] == "link"
    }
    assert hrefs == {"https://example.com/a", "mailto:b@example.com"}


def test_parse_morning_plan_missing_section_raises():
    with pytest.raises(MorningPlanError):
        parse_morning_plan("# job-search\n\nNo morning section here.\n")


def test_parse_morning_plan_missing_table_raises():
    text = """\
## Standing morning plan

Just some intro, no table in sight.
"""
    with pytest.raises(MorningPlanError):
        parse_morning_plan(text)


def test_parse_morning_plan_empty_table_raises():
    text = """\
## Standing morning plan

| # | Channel | Time | What happens |
|---|---|---|---|
"""
    with pytest.raises(MorningPlanError):
        parse_morning_plan(text)


def test_load_hn_snapshots_present_and_missing(tmp_path):
    day = date(2026, 9, 26)
    (tmp_path / f"hn-jobs-{day.isoformat()}-freelance.txt").write_text("freelance data")

    snapshots = load_hn_snapshots(tmp_path, day)

    assert snapshots == [
        {
            "kind": "freelance",
            "filename": "hn-jobs-2026-09-26-freelance.txt",
            "present": True,
            "text": "freelance data",
        },
        {
            "kind": "hiring",
            "filename": "hn-jobs-2026-09-26-hiring.txt",
            "present": False,
            "text": None,
        },
    ]


def _write_fake_job_search(root, readme_text=SYNTHETIC_README):
    job_search = root / "job-search"
    snapshots = job_search / "market-monitor" / "snapshots"
    snapshots.mkdir(parents=True)
    (job_search / "README.md").write_text(readme_text)
    return job_search


def test_morning_endpoint_returns_steps_from_fake_job_search(tmp_path, monkeypatch):
    _write_fake_job_search(tmp_path)
    monkeypatch.setenv("PROJECTS_ROOT", str(tmp_path))

    response = TestClient(app).get("/api/morning")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["date"]) == 10
    assert payload["date"][4] == "-"
    assert [step["channel"] for step in payload["steps"]] == [
        "Replies",
        "Hacker News",
        "Upwork",
    ]
    assert payload["source"] == str(tmp_path / "job-search" / "README.md")
    assert [snap["kind"] for snap in payload["snapshots"]] == ["freelance", "hiring"]
    assert all(snap["present"] is False for snap in payload["snapshots"])
    assert all(snap["text"] is None for snap in payload["snapshots"])
    assert all(snap["filename"].startswith("hn-jobs-") for snap in payload["snapshots"])


def test_morning_endpoint_503_when_readme_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("PROJECTS_ROOT", str(tmp_path))

    response = TestClient(app).get("/api/morning")

    assert response.status_code == 503
    assert "Morning plan source not found" in response.json()["detail"]


def test_morning_snapshot_uses_local_date(tmp_path, monkeypatch):
    _write_fake_job_search(tmp_path)
    monkeypatch.setenv("PROJECTS_ROOT", str(tmp_path))

    snapshot = morning_snapshot(date(2026, 9, 26))

    assert snapshot["date"] == "2026-09-26"
    assert snapshot["steps"]


def test_fragment_only_link_points_at_the_readme():
    plan = parse_morning_plan(
        "## Standing morning plan\n\n"
        "| # | Channel | Time | What happens |\n|---|---|---|---|\n"
        "| 0 | Replies | 2 min | See [the rules](#the-rules). |\n"
    )
    link = next(s for s in plan["steps"][0]["description"] if s["type"] == "link")
    assert link["href"] == f"{GITHUB_BLOB_BASE}/README.md#the-rules"
