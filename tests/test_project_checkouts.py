"""Project checkouts: `pt project checkout|checkin`, the task listings and /api/projects (#8339)."""

from __future__ import annotations

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

    [project] = [p for p in TestClient(app).get("/api/projects").json()["projects"] if p["id"] == "holoscape"]
    assert (project["checkout"]["machine_label"], project["checkout"]["holder"]) == ("Mac Mini", "Qwen on Mini")
