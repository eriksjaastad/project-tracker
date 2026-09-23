"""Source and failure contracts for the temporary Holoscape progress feed."""

import json
from datetime import datetime, time, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from dashboard import holoscape_progress as progress
from dashboard.app import app


def test_board_events_share_local_day_and_count_transitions(monkeypatch):
    rows = [
        {"timestamp": "2026-09-20T01:00:00Z", "event_type": "created",
         "old_status": None, "new_status": "Backlog"},
        {"timestamp": "2026-09-19T22:00:00", "event_type": "status_changed",
         "old_status": "In Progress", "new_status": "Review"},
        {"timestamp": "2026-09-20T00:30:00-04:00", "event_type": "completed",
         "old_status": "Review", "new_status": "Done"},
    ]

    class FakeDB:
        def task_history_events(self, start_iso, project_id):
            assert (start_iso, project_id) == ("2026-09-15", "holoscape")
            return rows

    monkeypatch.setattr(progress, "DatabaseManager", FakeDB)
    daily = progress.fetch_board()["daily"]
    assert daily["2026-09-19"]["task_created"] == 1
    assert daily["2026-09-19"]["review_entries"] == 1
    assert daily["2026-09-20"]["task_completed"] == 1


def test_paginated_github_api_flattens_every_page(monkeypatch):
    pages = [[{"sha": str(i)} for i in range(100)], [{"sha": "last"}]]

    def fake_run(cmd, **kwargs):
        assert cmd[1:3] == ["api", "--paginate"]
        assert "--slurp" in cmd
        return SimpleNamespace(returncode=0, stdout=json.dumps(pages))

    monkeypatch.setattr(progress, "_gha_binary", lambda: "gha")
    monkeypatch.setattr(progress.subprocess, "run", fake_run)
    assert len(progress._gha_json(["repos/x/y/pulls/1/commits?per_page=100"], paginated=True)) == 101

    def fake_run_objects(cmd, **kwargs):
        return SimpleNamespace(returncode=0, stdout=json.dumps([
            {"workflow_runs": [{"id": 1}]}, {"workflow_runs": [{"id": 2}]},
        ]))

    monkeypatch.setattr(progress.subprocess, "run", fake_run_objects)
    assert len(progress._gha_json(["repos/x/y/actions/runs"], paginated=True,
                                  page_key="workflow_runs")) == 2


def test_github_tracks_later_pr_work_and_ci_failures(monkeypatch):
    commit = lambda stamp: {"commit": {"committer": {"date": stamp}}}

    def fake_api(args, *, paginated=False, page_key=None):
        path = args[0]
        if path.endswith("/pulls/173"):
            return {"state": "closed", "merged": True, "head": {"sha": "abc"},
                    "created_at": "2026-09-19T14:35:20Z", "merged_at": "2026-09-23T19:24:42Z"}
        if "/commits?" in path:
            return ([{**commit("2026-09-20T02:00:00Z"), "sha": "first"},
                     {**commit("2026-09-20T15:00:00Z"), "sha": "second"}]
                    if "/173/" in path else
                    [{**commit("2026-09-24T12:00:00Z"), "sha": "later"}])
        if "/reviews?" in path:
            return [] if "/173/" in path else [
                {"submitted_at": "2026-09-24T13:00:00Z", "state": "COMMENTED"}]
        if "/actions/runs?" in path:
            assert page_key == "workflow_runs"
            return ([{"id": 1, "name": "check-label", "status": "completed",
                      "conclusion": "failure", "created_at": "2026-09-20T12:00:00Z"},
                     {"id": 2, "name": "check-label", "status": "completed",
                      "conclusion": "success", "created_at": "2026-09-23T18:00:00Z"}]
                    if "branch=experiment" in path else
                    [{"id": 3, "name": "pytest", "status": "in_progress",
                      "conclusion": None, "created_at": "2026-09-24T14:00:00Z"}])
        return [
            {"number": 173, "head": {"ref": "experiment"},
             "created_at": "2026-09-19T14:35:20Z", "merged_at": "2026-09-23T19:24:42Z"},
            {"number": 176, "head": {"ref": "next-branch"},
             "created_at": "2026-09-24T14:00:00Z", "merged_at": None},
        ]

    monkeypatch.setattr(progress, "_gha_json", fake_api)
    data = progress.fetch_github()
    assert data["pr"]["merged"] is True
    assert data["daily"]["2026-09-19"]["commits"] == 1  # 02:00 UTC is prior NY day
    assert data["daily"]["2026-09-20"]["commits"] == 1
    assert data["daily"]["2026-09-23"]["prs_merged"] == 1
    assert data["daily"]["2026-09-24"]["commits"] == 1
    assert data["daily"]["2026-09-24"]["github_reviews"] == 1
    assert data["daily"]["2026-09-20"]["ci_failure"] == 1
    assert data["daily"]["2026-09-23"]["ci_success"] == 1
    assert data["daily"]["2026-09-24"]["ci_pending"] == 1
    assert data["pr"]["workflow_names"] == ["check-label", "pytest"]
    assert sum(day["prs_opened"] for day in data["daily"].values()) == 2


def test_hermes_metadata_keeps_unknown_cost_and_counts_real_calls(monkeypatch):
    csv_data = (
        "kind,occurred_at,ended_at,model,provider,cost_status,input_tokens,"
        "output_tokens,cache_read_tokens,cache_write_tokens,tool_references\n"
        "manager,1789927200.5,1789927260.5,gpt-5.5,openai-codex,included,100,20,30,0,0\n"
        "deepseek_cli,1789927200.5,1789927320.5,deepseek-v4-flash,,unknown,50,10,400,0,0\n"
        "worktree_reference,1789927200.5,,,,,0,0,0,0,3\n"
    )

    def fake_run(cmd, **kwargs):
        assert cmd[0] == "ssh" and "-readonly" in cmd[-1]
        assert "SELECT kind, occurred_at" in kwargs["input"]
        assert "content" not in kwargs["input"]
        return SimpleNamespace(returncode=0, stdout=csv_data)

    monkeypatch.setattr(progress.subprocess, "run", fake_run)
    data = progress.fetch_hermes()
    day = progress._timestamp_day(1789927200.5)
    assert data["daily"][day]["worktree_references"] == 3
    assert data["daily"][day]["deepseek_cli_session_minutes"] == 2.0
    assert data["deepseek_cost_unknown_sessions"] == 1
    assert data["models"]["deepseek_cli:deepseek-v4-flash"] == 1


def test_missing_source_values_are_unknown_not_zero(monkeypatch):
    class FakeCache:
        def __init__(self, value):
            self.value = value

        def read(self, _fetch):
            return self.value

    base = {"refreshing": False, "stale": False, "refresh_error": None}
    fetched_at = progress._fetched_at()
    monkeypatch.setattr(progress, "_BOARD_CACHE", FakeCache({**base, "daily": {}, "fetched_at": fetched_at}))
    monkeypatch.setattr(progress, "_GITHUB_CACHE", FakeCache({**base, "refresh_error": "GitHub refresh failed"}))
    monkeypatch.setattr(progress, "_HERMES_CACHE", FakeCache({**base, "daily": {}, "fetched_at": fetched_at}))
    payload = progress.progress_snapshot()
    today = payload["series"][-1]
    assert today["task_created"] == 0
    assert today["commits"] is None
    assert today["manager_sessions"] == 0
    assert payload["deepseek_cost_usd"] is None
    assert payload["sources"]["github"]["status"] == "unavailable"


def test_stale_snapshot_does_not_zero_fill_unobserved_dates(monkeypatch):
    yesterday = datetime.now(progress.DISPLAY_ZONE).date() - timedelta(days=1)
    fetched_at = datetime.combine(yesterday, time(12), progress.DISPLAY_ZONE).isoformat()

    class FakeCache:
        def __init__(self, value):
            self.value = value

        def read(self, _fetch):
            return self.value

    fresh = {"refreshing": False, "stale": False, "refresh_error": None,
             "daily": {}, "fetched_at": progress._fetched_at()}
    stale = {"refreshing": False, "stale": True, "refresh_error": "GitHub refresh failed",
             "daily": {yesterday.isoformat(): {"commits": 3}}, "fetched_at": fetched_at}
    monkeypatch.setattr(progress, "_BOARD_CACHE", FakeCache(fresh))
    monkeypatch.setattr(progress, "_GITHUB_CACHE", FakeCache(stale))
    monkeypatch.setattr(progress, "_HERMES_CACHE", FakeCache(fresh))

    payload = progress.progress_snapshot()
    observed, unobserved = payload["series"][-2:]
    assert observed["date"] == yesterday.isoformat()
    assert observed["commits"] == 3
    assert observed["prs_merged"] == 0
    assert unobserved["commits"] is None
    assert unobserved["ci_success"] is None
    assert unobserved["task_created"] == 0
    assert payload["sources"]["github"]["status"] == "stale"


def test_api_exposes_progress_shape(monkeypatch):
    expected = {"series": [{"date": "2026-09-20", "commits": 2}], "sources": {}}
    monkeypatch.setattr(progress, "progress_snapshot", lambda: expected)
    response = TestClient(app).get("/api/holoscape/series")
    assert response.status_code == 200
    assert response.json() == expected


def test_malformed_hermes_response_is_an_error(monkeypatch):
    monkeypatch.setattr(progress.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout="body,secret\na,b\n"))
    with pytest.raises(RuntimeError, match="invalid records"):
        progress.fetch_hermes()
