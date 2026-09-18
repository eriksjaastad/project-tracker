"""Client-side `DatabaseManager`. Talks to dbmed; cannot open a database.

The real implementation now lives in `backend_manager.py`, which only ever runs
inside the dbmed daemon under the `_dbmed` service account. This module keeps
the import path and the method names every caller already uses, so
`scripts/pt.py` and `dashboard/app.py` did not have to be rewritten — but the
object they get back is an RPC proxy, and the parameters they pass are checked
against the operation allowlist on the far side.

Two deliberate behaviour changes, both of which will surface as loud errors
rather than quiet differences:

* `DatabaseManager(db_path)` raises. A caller-chosen database path is the
  arbitrary-path bypass the boundary exists to prevent; the path comes from the
  root-owned registry now. Tests provision a synthetic fixture through the
  daemon instead.
* Methods must be called with keyword arguments. The proxy names parameters on
  the wire and no longer holds a copy of the backend signature, so mapping
  positional arguments would mean guessing — and a wrong guess after someone
  reorders a backend parameter is a silent data bug.

`_USE_TURSO` stays here, and is still read from `~/projects/.turso-config.json`.
It is display and command-gating only: `pt` uses it to label the backend and to
decide whether the sync subcommands apply. Which backend actually gets opened
is the daemon's decision, made from the registry. Reading a non-secret local
config file to decide what to print is not database access.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dbmed.client import RemoteDatabaseManager as DatabaseManager

__all__ = ["DatabaseManager", "_USE_TURSO"]

_TURSO_CONFIG_PATH = Path.home() / "projects" / ".turso-config.json"


def _check_turso_enabled() -> bool:
    """Mirror of the backend's switch, for labelling only.

    Kept byte-for-byte compatible with the previous behaviour in
    `backend_manager._check_turso_enabled` so `pt` prints the same thing it
    always did.
    """
    try:
        with _TURSO_CONFIG_PATH.open() as handle:
            return bool(json.load(handle).get("turso_enabled", False))
    except (OSError, json.JSONDecodeError, AttributeError):
        return bool(os.getenv("TURSO_KANBAN_URL") and os.getenv("TURSO_KANBAN_TOKEN"))


_USE_TURSO: bool = _check_turso_enabled()
