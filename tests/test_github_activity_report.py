"""Behavior checks for the read-only portfolio GitHub activity report."""

from datetime import date

import pytest

from scripts.github_activity_report import ReportError, collect, render


def pr(number, *, author, created, closed=None, merged=None, state="open",
       title="feat: work (#7549)"):
    return {
        "repository_url": "https://api.github.com/repos/eriksjaastad/project-tracker",
        "number": number,
        "html_url": f"https://github.com/eriksjaastad/project-tracker/pull/{number}",
        "title": title,
        "created_at": created,
        "closed_at": closed,
        "updated_at": closed or created,
        "state": state,
        "user": {"login": author},
        "pull_request": {"merged_at": merged},
    }


def test_cross_identity_events_and_reviews_are_not_confused_with_cycles():
    opened = pr(10, author="manager-identity[bot]",
                created="2026-09-23T04:30:00Z")
    merged = pr(11, author="eriksjaastad",
                created="2026-09-22T20:00:00Z",
                closed="2026-09-23T15:00:00Z",
                merged="2026-09-23T15:00:00Z", state="closed")
    closed = pr(12, author="architect-identity[bot]",
                created="2026-09-20T20:00:00Z",
                closed="2026-09-23T16:00:00Z", state="closed",
                title="chore: no card")

    def api(path, fields):
        if path == "search/issues":
            qualifier = fields["q"].split(" is:pr ")[1].split(":")[0]
            items = {
                "created": [opened],
                "updated": [opened, merged, closed],
                "closed": [merged, closed],
                "merged": [merged],
            }[qualifier]
            return {"items": items, "total_count": len(items),
                    "incomplete_results": False}
        if path.endswith("/10/reviews"):
            return [
                {"id": 77, "submitted_at": "2026-09-23T13:00:00Z",
                 "user": {"login": "chatgpt-codex-connector[bot]"},
                 "state": "COMMENTED"},
                {"id": 78, "submitted_at": "2026-09-22T13:00:00Z",
                 "user": {"login": "eriksjaastad"}, "state": "APPROVED"},
            ]
        return []

    report = collect("eriksjaastad", date(2026, 9, 23),
                     "America/New_York", api=api, cards={"7549"},
                     codex_reported_reviews=1)
    assert len(report["pull_requests"]) == 3
    assert report["review_cycles"] is None
    assert report["window_utc"] == [
        "2026-09-23T04:00:00+00:00", "2026-09-24T04:00:00+00:00"]
    assert report["pull_requests"][0]["card"] == "7549"
    assert len(report["pull_requests"][0]["reviews"]) == 1
    markdown = render(report)
    assert "**3 distinct PRs in the candidate set; 1 opened, 1 merged, 1 closed without merge; 1 submitted review objects on 1 distinct PRs.**" in markdown
    assert "Distinct Codex review executions: **unknown**" in markdown
    assert "Erik reported a code review count of 1 in the Codex UI" in markdown
    assert "manager-identity[bot]" in markdown
    assert "architect-identity[bot]" in markdown
    assert "eriksjaastad" in markdown
    assert "Still open among candidate PRs" in markdown


@pytest.mark.parametrize("data", [
    {"items": [], "total_count": 1000, "incomplete_results": False},
    {"items": [], "total_count": 0, "incomplete_results": True},
])
def test_incomplete_search_fails_instead_of_reporting_zero(data):
    with pytest.raises(ReportError):
        collect("eriksjaastad", date(2026, 9, 23),
                "America/New_York", api=lambda *_: data, cards=set())


def test_review_on_pr_without_same_day_lifecycle_event_is_found_by_update():
    old = pr(13, author="manager-identity[bot]",
             created="2026-08-01T04:00:00Z", title="fix: old (#7549)")

    def api(path, fields):
        if path == "search/issues":
            items = [old] if " updated:" in fields["q"] else []
            return {"items": items, "total_count": len(items),
                    "incomplete_results": False}
        return [{"id": 88, "submitted_at": "2026-09-23T18:00:00Z",
                 "user": {"login": "eriksjaastad"}, "state": "APPROVED"}]

    report = collect("eriksjaastad", date(2026, 9, 23),
                     "America/New_York", api=api, cards={"7549"})
    assert len(report["pull_requests"]) == 1
    assert not report["pull_requests"][0]["opened"]
    assert report["pull_requests"][0]["reviews"][0]["actor"] == "eriksjaastad"
