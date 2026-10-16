"""Project checkouts: `pt project checkout|checkin`, the task listings and /api/projects (#8339)."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from pt import cli  # noqa: E402
from dashboard.app import app  # noqa: E402

ENV = {"PT_NO_BANNER": "1", "PT_SUPPRESS_MIGRATION_WARNING": "1"}


def _pt(*args: str):
    return CliRunner().invoke(cli, list(args), env=ENV)


@pytest.fixture
def holoscape(db):
    db.add_project(project_id="holoscape", name="holoscape", path="virtual://holoscape", status="active")
    return db


def test_second_checkout_is_refused_naming_the_holder(holoscape) -> None:
    first = _pt("project", "checkout", "holoscape", "--machine", "mini", "--holder", "Qwen on Mini")
    assert first.exit_code == 0, first.output
    assert "CHECKED OUT — Mac Mini (Qwen on Mini" in first.output

    second = _pt("project", "checkout", "holoscape", "--machine", "laptop", "--holder", "Claude")
    assert second.exit_code != 0
    assert "already checked out to Mac Mini by Qwen on Mini" in second.output
    assert holoscape.get_open_checkouts()["holoscape"]["holder"] == "Qwen on Mini"


def test_checkout_of_a_missing_project_inserts_nothing(holoscape) -> None:
    # The project check is part of the INSERT, so a project deleted just
    # before it leaves no orphan checkout behind.
    with pytest.raises(ValueError, match="no project 'gone'"):
        holoscape.checkout_project("gone", "mini", "Qwen on Mini")
    with holoscape._get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM project_checkouts").fetchone()[0] == 0


def test_checkin_records_who_and_frees_the_project(holoscape) -> None:
    holoscape.checkout_project("holoscape", "mini", "Qwen on Mini")
    result = _pt("project", "checkin", "holoscape", "--by", "Claude on MacBook")
    assert result.exit_code == 0, result.output
    assert holoscape.get_open_checkouts() == {}
    with holoscape._get_conn() as conn:
        row = conn.execute("SELECT checked_in_by, checked_in_at FROM project_checkouts").fetchone()
    assert row["checked_in_by"] == "Claude on MacBook" and row["checked_in_at"]
    # Nothing is out now, so a second check-in is an error, and a new checkout works.
    assert _pt("project", "checkin", "holoscape", "--by", "x").exit_code != 0
    assert holoscape.checkout_project("holoscape", "laptop", "Claude")["machine"] == "laptop"


def test_listings_and_api_show_the_checkout(holoscape) -> None:
    holoscape.add_task(text="Wire the tab bar", project_id="holoscape", status="To Do")
    holoscape.checkout_project("holoscape", "mini", "Qwen on Mini")

    scoped = _pt("tasks", "-p", "holoscape")
    assert scoped.exit_code == 0, scoped.output
    assert "CHECKED OUT — Mac Mini" in scoped.output
    everything = _pt("tasks")
    assert "[OUT: Mac Mini] | holoscape |" in everything.output
    # Board cells wrap at 20 columns, so check the start of the marker.
    assert "[OUT:" in _pt("tasks", "--board").output
    assert "CHECKED OUT — Mac Mini" in _pt("status", "holoscape").output
    assert "holoscape | active | - | 0% | ! | CHECKED OUT — Mac Mini" in _pt("list").output

    [project] = [p for p in TestClient(app).get("/api/projects").json()["projects"] if p["id"] == "holoscape"]
    assert (project["checkout"]["machine_label"], project["checkout"]["holder"]) == ("Mac Mini", "Qwen on Mini")


def test_before_migration_023_listings_work_and_checkout_says_to_migrate(holoscape) -> None:
    # The per-test database copy, not the live one.
    with sqlite3.connect(os.environ["PT_DB_PATH"]) as conn:
        conn.execute("DROP TABLE project_checkouts")
    assert _pt("tasks", "-p", "holoscape").exit_code == 0
    response = TestClient(app).get("/api/projects")
    assert response.status_code == 200
    assert all(p["checkout"] is None for p in response.json()["projects"])
    refused = _pt("project", "checkout", "holoscape", "--machine", "mini", "--holder", "Qwen")
    assert refused.exit_code != 0 and "run `pt db migrate`" in refused.output
