"""Destructive operations refuse by default, and cost a verified backup.

Card #7219 says to preserve the existing destructive-operation gates, not to
invent new friction. So routine single-row deletes stayed WRITE — they already
snapshot the rows they touch and already honour SAFE_MODE. What moved up to
DESTRUCTIVE is the set that can empty a board in one call.

For those, refusal is the default and lives on the privileged side, where no
client environment variable reaches it. Getting past it costs a token, and the
daemon only issues one after it has taken a full timestamped backup and
verified that the backup opens, passes integrity_check, and contains the
tables it should.
"""

from __future__ import annotations

import pytest

from dbmed.errors import InvalidParams, NotAuthorized

DESTRUCTIVE = [
    "delete_project",
    "delete_done_tasks",
    "trim_done_tasks",
    "raw_import_tasks",
    "backup_restore",
    "migrations_apply",
]


def _seed(db):
    db.add_project("alpha", "Alpha", "/tmp/alpha", "active")
    return db.add_task("a card", "alpha", status="Done")


@pytest.mark.parametrize("op", DESTRUCTIVE)
def test_destructive_operations_refuse_without_a_token(client, op):
    with pytest.raises(NotAuthorized) as excinfo:
        client.call(op, {})
    assert "refuses by default" in str(excinfo.value)


def test_the_classification_is_what_we_think_it_is(client):
    """Guard the list above against drift in either direction.

    A new destructive operation that nobody added here would go ungated, and
    an operation wrongly promoted to destructive would demand a full backup on
    a routine action — which is how `archive_done_tasks` briefly ended up
    taking a backup of the whole database every time a card was finished.
    """
    published = {
        name for name, spec in client.call("dbmed.ops").items()
        if spec["kind"] == "destructive"
    }
    assert published == set(DESTRUCTIVE), (
        f"destructive set drifted.\n  only in code: {sorted(published - set(DESTRUCTIVE))}"
        f"\n  only in test: {sorted(set(DESTRUCTIVE) - published)}"
    )


def test_archiving_is_not_destructive(client):
    """It sets a column, deletes nothing, and runs on every completed card."""
    assert client.call("dbmed.ops")["archive_done_tasks"]["kind"] == "write"


def test_single_row_deletes_keep_their_existing_gates(client):
    """They were WRITE before and stay WRITE; #7219 says preserve, not escalate."""
    ops = client.call("dbmed.ops")
    for name in ("delete_task", "delete_attachment", "delete_idea", "delete_info"):
        assert ops[name]["kind"] == "write", f"{name} was escalated without cause"


def test_authorize_demands_a_reason(client):
    for reason in ("", "   ", "oops"):
        with pytest.raises(InvalidParams):
            client.call("dbmed.authorize", {"op": "trim_done_tasks", "reason": reason})


def test_authorize_refuses_a_non_destructive_operation(client):
    with pytest.raises(InvalidParams) as excinfo:
        client.call("dbmed.authorize", {"op": "get_tasks", "reason": "no reason at all"})
    assert "needs no authorization" in str(excinfo.value)


def test_authorize_takes_a_backup_that_verifies(manager, daemon):
    """The backup is the price of the token, and it is checked, not assumed."""
    _seed(manager)
    grant = manager.call(
        "dbmed.authorize", op="trim_done_tasks", reason="boundary evidence suite"
    )

    backup = daemon["project_data"] / "backups"
    produced = list(backup.glob("pre_trim_done_tasks_*.db"))
    assert produced, f"no backup was written to {backup}"

    # Both DECISIONS.md locations, not just the one beside the database.
    external = daemon["data"] / "external" / "project-tracker"
    assert list(external.glob("pre_trim_done_tasks_*.db")), (
        "the second backup location is empty; DECISIONS.md requires two, because "
        "the 2026-01-27 incident proved one can be lost with the project"
    )
    assert grant["token"]
    assert grant["backup_path"].endswith(".db")


def test_a_token_works_once(manager, client):
    _seed(manager)
    grant = manager.call(
        "dbmed.authorize", op="trim_done_tasks", reason="single use check"
    )
    client.call("trim_done_tasks", {"keep": 0}, token=grant["token"])
    with pytest.raises(NotAuthorized) as excinfo:
        client.call("trim_done_tasks", {"keep": 0}, token=grant["token"])
    assert "already used" in str(excinfo.value)


def test_a_token_is_not_transferable_between_operations(manager, client):
    _seed(manager)
    grant = manager.call(
        "dbmed.authorize", op="trim_done_tasks", reason="transfer check"
    )
    with pytest.raises(NotAuthorized) as excinfo:
        client.call("delete_done_tasks", {}, token=grant["token"])
    assert "different caller or operation" in str(excinfo.value)


def test_an_invented_token_is_refused(client):
    with pytest.raises(NotAuthorized):
        client.call("trim_done_tasks", {"keep": 0}, token="not-a-real-token")


def test_the_authorize_helper_round_trips(manager):
    """`db.authorize(...)` is what the CLI call sites use."""
    _seed(manager)
    removed = manager.authorize(
        "trim_done_tasks", reason="helper round trip", keep=0
    )
    assert isinstance(removed, int)


def test_restore_will_not_accept_a_path(manager):
    """The bypass this closed: restore used to copy any file over the live DB."""
    _seed(manager)
    for attempt in ("/etc/passwd", "../../etc/passwd", "backups/../../../etc/passwd"):
        with pytest.raises(Exception) as excinfo:
            manager.authorize("backup_restore", reason="path probe", name=attempt)
        assert "bare backup name" in str(excinfo.value) or "no backup named" in str(
            excinfo.value
        ), f"{attempt!r} produced an unexpected error: {excinfo.value}"


def test_destructive_work_is_written_to_the_audit_log(manager, daemon):
    _seed(manager)
    manager.authorize("trim_done_tasks", reason="audit log evidence", keep=0)

    log = (daemon["data"] / "audit" / "dbmed.jsonl").read_text()
    assert "authorize" in log
    assert "trim_done_tasks" in log
    assert "audit log evidence" in log, "the stated reason is the point of the record"
