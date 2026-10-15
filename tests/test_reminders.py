"""Erik's Reminders: manager mixin, dashboard API and `pt reminders` (#8282)."""

from __future__ import annotations

import sys
from pathlib import Path

from click.testing import CliRunner
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from pt import cli  # noqa: E402
from dashboard.app import app  # noqa: E402

client = TestClient(app)


def _add(name: str, **fields) -> dict:
    response = client.post("/api/reminders", json={"name": name, **fields})
    assert response.status_code == 201, response.text
    return response.json()["reminder"]


def _names(section: str) -> list[str]:
    return [r["name"] for r in client.get("/api/reminders").json()[section]]


def test_reminder_lifecycle_add_built_in_remove() -> None:
    first = _add("  Prompt pack  ", purpose="Run an audit", location="~/x")
    assert (first["name"], first["purpose"], first["location"]) == ("Prompt pack", "Run an audit", "~/x")
    assert _add("Guide", purpose="  ", location="")["purpose"] is None
    third = _add("Roadmap")
    assert client.post("/api/reminders", json={"name": "   "}).status_code == 400
    # Active reminders keep the order they were added in.
    assert _names("active") == ["Prompt pack", "Guide", "Roadmap"]

    built = client.post(f"/api/reminders/{first['id']}/built-in")
    assert built.status_code == 200 and built.json()["reminder"]["built_in_at"]
    assert _names("active") == ["Guide", "Roadmap"]
    assert _names("built_in") == ["Prompt pack"]

    assert client.delete(f"/api/reminders/{third['id']}").status_code == 200
    assert _names("active") == ["Guide"]
    # A removed reminder is gone for both actions; the row itself is kept.
    assert client.delete(f"/api/reminders/{third['id']}").status_code == 404
    assert client.post(f"/api/reminders/{third['id']}/built-in").status_code == 404
    assert client.delete("/api/reminders/999999").status_code == 404


def test_pt_reminders_add_appears_on_the_page_and_in_the_list() -> None:
    env = {"PT_NO_BANNER": "1", "PT_SUPPRESS_MIGRATION_WARNING": "1"}
    result = CliRunner().invoke(
        cli,
        ["reminders", "add", "Saraev prompt pack", "--purpose", "Audit", "--location", "~/p"],
        env=env,
    )
    assert result.exit_code == 0, result.output
    [reminder] = client.get("/api/reminders").json()["active"]
    assert (reminder["name"], reminder["purpose"], reminder["location"]) == (
        "Saraev prompt pack", "Audit", "~/p")

    listed = CliRunner().invoke(cli, ["reminders"], env=env)
    assert listed.exit_code == 0, listed.output
    assert f"#{reminder['id']} Saraev prompt pack" in listed.output
