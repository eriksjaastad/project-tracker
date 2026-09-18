"""The unprivileged client. Runs as the agent, and can do nothing on its own.

**This module imports no database driver, and it must stay that way.**
`tests/boundary/test_client_has_no_driver.py` asserts it. The reason is not
tidiness: if the client had a driver it would have a fallback, and a fallback is
exactly what card #7228 forbids — "Failure of the mediation service or missing
coverage must deny access, never fall back to direct database access." Making
the fallback *impossible to write* is stronger than making it forbidden.

`DBMED_SOCKET` may point this client at a different daemon, which the test
harness uses. That is not an escalation: the socket only selects which daemon
answers, and only the real daemon's service account can open protected files.
Pointing at a socket of your own gets you a daemon with no access to anything.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Any

from . import protocol
from .errors import DbUnavailable, DbmedError, UnknownOperation, from_wire
from .registry import DEFAULT_SOCKET

CONNECT_TIMEOUT_SECONDS = 5.0
CALL_TIMEOUT_SECONDS = 30.0


def socket_path() -> Path:
    override = os.environ.get("DBMED_SOCKET")
    return Path(override) if override else DEFAULT_SOCKET


class DbmedClient:
    """One client per project. Stateless: a connection per call."""

    def __init__(
        self,
        project: str,
        *,
        path: Path | None = None,
        timeout: float = CALL_TIMEOUT_SECONDS,
    ) -> None:
        self.project = project
        self.path = path or socket_path()
        self.timeout = timeout

    def call(self, op: str, params: dict[str, Any] | None = None, *, token: str | None = None) -> Any:
        request = protocol.encode_request(self.project, op, params or {}, token)
        blob = self._roundtrip(request)

        try:
            frame = _loads(blob)
        except ValueError as exc:
            raise DbUnavailable(
                f"the dbmed daemon at {self.path} returned an unreadable response"
            ) from exc

        if not isinstance(frame, dict) or "ok" not in frame:
            raise DbUnavailable(f"the dbmed daemon at {self.path} returned a malformed frame")
        if frame["ok"]:
            return frame.get("data")
        raise from_wire(frame.get("error") or {})

    def _roundtrip(self, request: bytes) -> bytes:
        try:
            conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        except OSError as exc:  # pragma: no cover - platform failure
            raise DbUnavailable(f"could not create a unix socket: {exc}") from exc

        try:
            conn.settimeout(CONNECT_TIMEOUT_SECONDS)
            try:
                conn.connect(str(self.path))
            except (FileNotFoundError, ConnectionRefusedError, PermissionError, OSError) as exc:
                raise DbUnavailable(
                    f"the dbmed database service is not reachable at {self.path} ({exc}). "
                    "Database access is unavailable; it has not fallen back to opening the "
                    "file directly. Start the service or ask Erik to."
                ) from exc

            conn.settimeout(self.timeout)
            try:
                conn.sendall(request)
                conn.shutdown(socket.SHUT_WR)
                with conn.makefile("rb") as stream:
                    return protocol.read_frame(stream, protocol.MAX_RESPONSE_BYTES)
            except socket.timeout as exc:
                raise DbUnavailable(
                    f"the dbmed daemon did not answer within {self.timeout}s"
                ) from exc
            except OSError as exc:
                raise DbUnavailable(f"the dbmed connection failed mid-request: {exc}") from exc
        finally:
            conn.close()


class RemoteDatabaseManager:
    """A stand-in for the old in-process `DatabaseManager`.

    Method names and call signatures are unchanged, so `scripts/pt.py` and
    `dashboard/app.py` keep calling `db.get_tasks(...)` exactly as before. The
    difference is that the call now crosses the boundary and is checked against
    the operation allowlist on the far side.

    Positional arguments still work. The client does not hold a copy of the
    backend signature — it asks the daemon, once per process, for each
    operation's real parameter order and maps positionals onto that. Keeping
    the authoritative order on the side that owns the code means a caller
    cannot drift out of sync with it; if someone reorders a backend parameter,
    the published order moves with it and existing call sites stay correct.
    """

    _PROJECT = "project-tracker"

    def __init__(self, db_path: Any = None, *, client: DbmedClient | None = None) -> None:
        if db_path is not None:
            raise DbmedError(
                "DatabaseManager no longer accepts a db_path. The database path is "
                "resolved by the dbmed registry, not by the caller — a caller-chosen "
                "path is the arbitrary-path bypass the boundary exists to prevent. "
                "For tests, provision a fixture through the daemon."
            )
        self._client = client or DbmedClient(self._PROJECT)
        self._ops_cache: dict[str, Any] | None = None

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(
                f"{name!r} is private to the dbmed backend and is not reachable from a "
                "client. A cursor or a connection cannot cross the socket. If you need "
                "a multi-step transaction, it becomes one named operation: add it to "
                "the allowlist and deploy it."
            )

        def _invoke(*args: Any, **params: Any) -> Any:
            if args:
                order = self._order(name)
                if len(args) > len(order):
                    raise DbmedError(
                        f"{name}() takes at most {len(order)} positional arguments "
                        f"({', '.join(order) or 'none'}), got {len(args)}"
                    )
                for key, value in zip(order, args):
                    if key in params:
                        raise DbmedError(f"{name}() got multiple values for {key!r}")
                    params[key] = value
            return self._client.call(name, params)

        _invoke.__name__ = name
        return _invoke

    def _order(self, op: str) -> list[str]:
        """Positional parameter order for `op`, cached per process.

        One extra round trip the first time any positional call is made, then
        never again. Cached on the instance rather than globally so a test
        harness pointing at a different daemon cannot inherit another
        daemon's answer.
        """
        if self._ops_cache is None:
            self._ops_cache = self._client.call("dbmed.ops")
        spec = self._ops_cache.get(op)
        if spec is None:
            raise UnknownOperation(
                f"{op!r} is not an allowlisted operation on {self._PROJECT!r}"
            )
        return list(spec.get("order", []))

    def call(self, op: str, /, **params: Any) -> Any:
        """Explicit form, for callers that prefer not to rely on __getattr__."""
        return self._client.call(op, params)

    def seed(self, task_id: int, **columns: Any) -> Any:
        """Test-fixture seeding. Refused unless the registry entry allows it.

        Present on the client for the test suite's convenience; it is not a
        capability the client grants. The daemon decides, from a root-owned
        registry file, and refuses everywhere the installer put one.
        """
        return self._client.call("dbmed.seed", {"task_id": task_id, **columns})

    def seed_task(self, task_id: int, **fields: Any) -> Any:
        """Create a task with a chosen id. Test support; see `seed`."""
        return self._client.call("dbmed.seed_task", {"task_id": task_id, **fields})

    def count_rows(self, table: str) -> int:
        """Row count for an allowlisted table. Test support; see `seed`."""
        return self._client.call("dbmed.count", {"table": table})["rows"]

    def authorize(self, op: str, /, *, reason: str, **params: Any) -> Any:
        """Run a destructive operation, requesting a token first.

        Two round trips on purpose. The first asks the daemon to take and verify
        a timestamped backup and issue a single-use token; the second performs
        the mutation. A caller cannot skip the first, because the daemon will
        not accept a destructive op without a token it issued itself.
        """
        grant = self._client.call("dbmed.authorize", {"op": op, "reason": reason})
        return self._client.call(op, params, token=grant["token"])


def _loads(blob: bytes) -> Any:
    import json

    if not blob:
        raise ValueError("empty response")
    return json.loads(blob.decode("utf-8"))
