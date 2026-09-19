"""When the service is gone, access is gone.

Card #7228: "Failure of the mediation service or missing coverage must deny
access, never fall back to direct database access."

The strongest version of that is not a rule the client obeys — it is a client
with no code capable of disobeying. These tests assert both: the behaviour,
and the absence of the machinery that would allow the other behaviour.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from dbmed.errors import DbUnavailable

REPO_ROOT = Path(__file__).resolve().parents[2]

# Every module an unprivileged caller imports on the way to the database.
CLIENT_MODULES = [
    REPO_ROOT / "dbmed" / "client.py",
    REPO_ROOT / "dbmed" / "protocol.py",
    REPO_ROOT / "dbmed" / "errors.py",
    REPO_ROOT / "scripts" / "db" / "manager.py",
    REPO_ROOT / "scripts" / "db" / "calendar_manager.py",
]

DRIVERS = {"sqlite3", "libsql", "libsql_client", "psycopg", "psycopg2", "sqlalchemy", "duckdb"}


@pytest.mark.parametrize("module", CLIENT_MODULES, ids=lambda p: p.name)
def test_client_modules_import_no_database_driver(module):
    """The fallback is not forbidden, it is absent.

    Parsed rather than grepped, so a driver imported inside a function body or
    behind a try/except is caught too — which is exactly where a well-meaning
    "just in case the daemon is down" fallback would be written.
    """
    tree = ast.parse(module.read_text())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    offending = found & DRIVERS
    assert not offending, (
        f"{module.name} imports {offending}. A client that can open a database "
        "has a fallback, and a fallback is the thing the boundary forbids."
    )


def test_client_modules_never_name_a_driver_at_all():
    """Belt and braces: not even a string that could reach one via importlib."""
    for path in CLIENT_MODULES:
        source = path.read_text()
        for driver in ("importlib.import_module", "__import__"):
            assert driver not in source, (
                f"{path.name} uses {driver}, which can reach a driver without an "
                "import statement for the AST check to find"
            )


def test_daemon_unreachable_raises_rather_than_returning_empty(daemon):
    """The silent-failure shape this must never take is `return []`.

    A caller cannot distinguish "no tasks" from "database unreachable" if the
    unreachable case returns an empty list, and would render an empty board
    over a broken service.
    """
    from dbmed.client import DbmedClient

    nowhere = DbmedClient(
        "project-tracker", path=daemon["root"] / "definitely-not-a-socket"
    )
    with pytest.raises(DbUnavailable):
        nowhere.call("get_tasks")


def test_the_unavailable_message_names_the_service_and_denies_a_fallback(daemon):
    from dbmed.client import DbmedClient

    nowhere = DbmedClient("project-tracker", path=daemon["root"] / "absent.sock")
    with pytest.raises(DbUnavailable) as excinfo:
        nowhere.call("get_tasks")
    message = str(excinfo.value)
    assert "not reachable" in message
    # The operator needs to know it did not quietly do something else instead.
    assert "has not fallen back" in message


def test_a_dead_socket_file_is_still_a_refusal():
    """A leftover socket inode with nothing listening must not hang or pass."""
    import socket as socketlib

    from dbmed.client import DbmedClient

    dead = Path("/tmp") / f"dbmed-dead-{os.getpid()}.sock"
    server = socketlib.socket(socketlib.AF_UNIX, socketlib.SOCK_STREAM)
    server.bind(str(dead))
    server.close()  # bound then closed: the path exists, nothing is listening
    try:
        with pytest.raises(DbUnavailable):
            DbmedClient("project-tracker", path=dead).call("get_tasks")
    finally:
        from send2trash import send2trash

        if dead.exists():
            send2trash(str(dead))


def test_pt_exits_non_zero_when_the_service_is_unreachable():
    """End to end, through the real CLI. Truthful exit codes (rule E1).

    Points `DBMED_SOCKET` at a path that does not exist. That override cannot
    grant access — it only chooses which daemon answers, and no daemon answers
    here — so this exercises the fail-closed path rather than weakening it.
    """
    env = {
        **os.environ,
        "DBMED_SOCKET": "/tmp/dbmed-definitely-absent.sock",
        "PT_SKIP_DOPPLER": "1",
        "PT_NO_BANNER": "1",
    }
    result = subprocess.run(
        [sys.executable, "scripts/pt.py", "tasks", "--json"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode != 0, (
        "pt exited 0 with no database service reachable. An exit code that "
        f"lies is worse than a crash.\nstdout: {result.stdout[:400]}"
    )
    combined = result.stdout + result.stderr
    assert "dbmed" in combined.lower() or "not reachable" in combined.lower(), (
        f"pt failed without naming the database service:\n{combined[:600]}"
    )
