"""Client-side `CalendarManager`. Talks to dbmed; cannot open a database.

The real implementation now lives in `backend_calendar_manager.py`, which only
ever runs inside the dbmed daemon under the `_dbmed` service account. This
module keeps the import path so `scripts/hooks/calendar_poller.py` and other
callers work unchanged — but the object they get back is an RPC proxy, and
operations are checked against the allowlist on the far side.

Deliberate behaviour change that will surface as a loud error: `CalendarManager(
db_path)` raises. A caller-chosen database path is the arbitrary-path bypass the
boundary exists to prevent; the path comes from the root-owned registry now.
Tests provision a synthetic fixture through the daemon instead.
"""

from __future__ import annotations

from typing import Any
from pathlib import Path

from dbmed.client import RemoteDatabaseManager
from dbmed.errors import DbmedError


class CalendarManager:
    """A stand-in for the old in-process `CalendarManager`.

    Method names are unchanged so `scripts/hooks/calendar_poller.py` and other
    callers work unchanged. The calls now cross the boundary with a
    `calendar_` prefix in the operation name (matching the ALLOWLIST entries).
    """

    _PROJECT = "project-tracker"

    def __init__(self, db_path: Any = None) -> None:
        if db_path is not None:
            raise DbmedError(
                "CalendarManager no longer accepts a db_path. The database path is "
                "resolved by the dbmed registry, not by the caller — a caller-chosen "
                "path is the arbitrary-path bypass the boundary exists to prevent. "
                "For tests, provision a fixture through the daemon."
            )
        self._mgr = RemoteDatabaseManager()

    def __getattr__(self, name: str) -> Any:
        """Proxy methods to the remote manager with calendar_ prefix."""
        if name.startswith("_"):
            raise AttributeError(
                f"{name!r} is private to the dbmed backend and is not reachable from a "
                "client."
            )

        def _invoke(*args: Any, **params: Any) -> Any:
            # Map method name to wire operation name with calendar_ prefix
            op_name = f"calendar_{name}"
            
            # Forward positional args the same way RemoteDatabaseManager does
            if args:
                order = self._mgr._order(op_name)
                if len(args) > len(order):
                    raise DbmedError(
                        f"{name}() takes at most {len(order)} positional arguments "
                        f"({', '.join(order) or 'none'}), got {len(args)}"
                    )
                for key, value in zip(order, args):
                    if key in params:
                        raise DbmedError(f"{name}() got multiple values for {key!r}")
                    params[key] = value
            
            return self._mgr.call(op_name, **params)

        _invoke.__name__ = name
        return _invoke

    # Convenience methods that forward directly
    def ensure_tables(self) -> None:
        """Create calendar tables if they don't exist. Handled by dbmed backend."""
        # This is handled automatically by dbmed_ops.ProjectTrackerOps.__init__
        pass
