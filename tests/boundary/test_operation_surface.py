"""What the socket will and will not accept.

The boundary's second job, after "you cannot open the file", is "and what you
can ask for is a short list someone reviewed". These tests are that list's
teeth: each one names a way a caller might try to widen the surface and
asserts the refusal.
"""

from __future__ import annotations

import re

import pytest

from dbmed.errors import (
    InvalidParams,
    NotRegistered,
    ProtocolError,
    UnknownOperation,
)


def test_sanctioned_read_works(client):
    """The baseline. A refusal suite proves nothing if nothing is allowed."""
    assert client.call("get_all_projects") == []
    assert client.call("get_tasks") == []


def test_ping_reports_the_project(client):
    assert client.call("dbmed.ping")["project"] == "project-tracker"


def test_there_is_no_sql_operation(client):
    """No spelling of "run this SQL" exists to be allowed or denied."""
    for attempt in ("execute", "execute_sql", "query", "sql", "raw", "eval"):
        with pytest.raises(UnknownOperation):
            client.call(attempt, {"sql": "SELECT 1"})


def test_private_methods_are_unreachable(client):
    """`_get_conn` is the one that would hand back a connection."""
    for attempt in ("_get_conn", "_backup_before_delete", "_ensure_delete_allowed"):
        with pytest.raises(UnknownOperation):
            client.call(attempt)


def test_dunder_and_attribute_traversal_are_unreachable(client):
    for attempt in ("__class__", "__init__", "__getattribute__", "entry", "db_path"):
        with pytest.raises(UnknownOperation):
            client.call(attempt)


def test_unknown_parameters_are_refused_not_ignored(client):
    """Dropping an unrecognised argument would change what the call means."""
    with pytest.raises(InvalidParams) as excinfo:
        client.call("get_tasks", {"nonexistent_filter": "x"})
    assert "nonexistent_filter" in str(excinfo.value)


def test_a_path_cannot_be_smuggled_in_as_a_parameter(client):
    """The arbitrary-path bypass, attempted through every plausible name."""
    for key in ("db_path", "path", "database", "file", "filename"):
        with pytest.raises(InvalidParams):
            client.call("get_tasks", {key: "/etc/passwd"})


def test_parameter_types_are_checked(client):
    with pytest.raises(InvalidParams):
        client.call("get_task", {"task_id": "not-an-integer"})


def test_kwargs_surfaces_are_bounded(client):
    """`update_task` takes **kwargs; the allowlist enumerates the fields."""
    with pytest.raises(InvalidParams) as excinfo:
        client.call("update_task", {"task_id": 1, "id": 99})
    assert "does not accept" in str(excinfo.value)


def test_an_unregistered_project_is_denied(daemon):
    """A missing registration is a deployment failure, never a fallback."""
    from dbmed.client import DbmedClient

    stranger = DbmedClient("not-a-registered-project", path=daemon["socket"])
    with pytest.raises(NotRegistered):
        stranger.call("dbmed.ping")


def test_protocol_version_is_enforced(daemon):
    import json
    import socket as socketlib

    conn = socketlib.socket(socketlib.AF_UNIX, socketlib.SOCK_STREAM)
    conn.settimeout(5)
    conn.connect(str(daemon["socket"]))
    conn.sendall(
        json.dumps({"v": 99, "project": "project-tracker", "op": "get_tasks"}).encode()
        + b"\n"
    )
    response = json.loads(conn.makefile("rb").readline())
    conn.close()
    assert response["ok"] is False
    assert response["error"]["code"] == "PROTOCOL"


def test_unknown_request_fields_are_refused(daemon):
    """A frame cannot grow a side channel."""
    import json
    import socket as socketlib

    conn = socketlib.socket(socketlib.AF_UNIX, socketlib.SOCK_STREAM)
    conn.settimeout(5)
    conn.connect(str(daemon["socket"]))
    conn.sendall(
        json.dumps(
            {
                "v": 1,
                "project": "project-tracker",
                "op": "get_tasks",
                "params": {},
                "db_path": "/etc/passwd",
            }
        ).encode()
        + b"\n"
    )
    response = json.loads(conn.makefile("rb").readline())
    conn.close()
    assert response["ok"] is False
    assert response["error"]["code"] == "PROTOCOL"


def test_oversized_requests_are_refused_before_parsing(client):
    with pytest.raises(ProtocolError):
        client.call("add_task", {"text": "x" * (2 << 20)})


def test_the_published_operation_list_has_no_surprises(client):
    """A regression guard on the surface itself.

    If a future change exposes something whose name suggests raw access, this
    fails and someone has to justify it in review rather than discovering it
    in production.
    """
    # Matched on whole name segments, not substrings. A substring check reads
    # "exec" inside `loop_last_executions` and cries wolf, and a guard that
    # cries wolf gets weakened until it catches nothing.
    banned = {
        "sql", "exec", "execute", "eval", "shell", "connect", "conn",
        "cursor", "raw", "query",
    }

    # Named exemptions, each with its reason. Weakening the rule would be the
    # easy fix and the wrong one: the guard's value is that adding a
    # raw-sounding operation costs an argument in review. Adding a line here
    # is that argument, in writing, next to the name it excuses.
    justified = {
        # Bulk task import. "raw" describes the shape of the input — a list of
        # already-formed task dicts, bypassing per-field defaulting — not raw
        # SQL. It takes no SQL and no path, and it is classified DESTRUCTIVE
        # so it cannot run without a token and a verified backup.
        "raw_import_tasks",
    }

    ops = client.call("dbmed.ops")
    assert ops, "the allowlist is empty, which means nothing was bound"
    for name in ops:
        assert not name.startswith("_")
        if name in justified:
            continue
        segments = set(re.split(r"[._]", name.lower()))
        offending = segments & banned
        assert not offending, f"{name!r} reads like a raw-access operation ({offending})"


def test_the_justified_exemptions_still_exist(client):
    """Guard the guard.

    If `raw_import_tasks` is ever renamed or removed, the exemption above
    becomes dead weight that silently excuses a future operation that happens
    to reuse the name.
    """
    assert "raw_import_tasks" in client.call("dbmed.ops")


def test_every_operation_declares_a_kind(client):
    valid = {"read", "write", "destructive"}
    for name, spec in client.call("dbmed.ops").items():
        assert spec["kind"] in valid, f"{name} has kind {spec['kind']!r}"
