"""
Local-only sync state for the cr-sqlite daemon (Phase 2.1b).

Before cr-sqlite actually ships, ``pt sync status/pause/resume`` needs
somewhere to persist the "is the data plane paused?" bit, the pause
scope, and the last successful sync timestamp. We reuse the existing
``_metadata`` table (LOCAL_ONLY per the CRR manifest — per-machine
sync state that must never replicate) with namespaced keys so we don't
have to ship a new table in a new migration every time the daemon
grows a field.

Keys owned by this module (all stored in ``_metadata.key``):

- ``sync.paused``           — ``"1"`` when the data plane is halted, absent
                               otherwise.
- ``sync.pause_scope``      — ``"data_plane"`` (default — control plane
                               keeps running so migration announcements
                               still cross machines) or ``"all"`` (halt
                               everything; rare, for full-stop
                               maintenance).
- ``sync.last_successful_sync`` — ISO8601 timestamp of the last time the
                               daemon completed a sync round. Absent
                               until the daemon ships (PR #3c).

``sync.paused`` is *only* about the data plane even when the value is
``"1"`` with scope ``"data_plane"``; the control plane (migration
announcements) must keep running so ``pt sync resume`` can unblock.
See MAC_MINI_SYNC_PLAN.md §2.1b and §2.3.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Literal, Optional

PauseScope = Literal["data_plane", "all"]


_KEY_PAUSED = "sync.paused"
_KEY_SCOPE = "sync.pause_scope"
_KEY_LAST_SYNC = "sync.last_successful_sync"


def _get(conn: sqlite3.Connection, key: str) -> Optional[str]:
    try:
        row = conn.execute(
            "SELECT value FROM _metadata WHERE key = ?", (key,)
        ).fetchone()
    except sqlite3.OperationalError as err:
        if "no such table" in str(err).lower():
            return None
        raise
    return row[0] if row else None


def _set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO _metadata (key, value, created_at) "
        "VALUES (?, ?, ?)",
        (key, value, datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )


def _delete(conn: sqlite3.Connection, key: str) -> None:
    conn.execute("DELETE FROM _metadata WHERE key = ?", (key,))


def is_paused(conn: sqlite3.Connection) -> bool:
    """True when the data plane is currently halted."""
    return _get(conn, _KEY_PAUSED) == "1"


def pause_scope(conn: sqlite3.Connection) -> Optional[PauseScope]:
    """Current pause scope, or None if not paused.

    Unexpected values (manual edits, future-daemon changes) are
    coerced to ``"data_plane"`` — the conservative default that
    keeps the control plane running.
    """
    if not is_paused(conn):
        return None
    raw = _get(conn, _KEY_SCOPE)
    if raw == "all":
        return "all"
    return "data_plane"


def set_paused(conn: sqlite3.Connection, scope: PauseScope = "data_plane") -> None:
    """Mark the sync data plane as paused.

    The ``scope`` argument distinguishes the normal "pause data,
    keep announcements crossing" case from the rare "pause
    everything" case. The stored values are the caller's
    responsibility to honor at daemon boot; this module only
    persists intent. Writes are committed by the caller.
    """
    if scope not in ("data_plane", "all"):
        raise ValueError(
            f"pause scope must be 'data_plane' or 'all', not {scope!r}"
        )
    _set(conn, _KEY_PAUSED, "1")
    _set(conn, _KEY_SCOPE, scope)


def clear_paused(conn: sqlite3.Connection) -> None:
    """Remove the paused flag and scope — used by ``pt sync resume``."""
    _delete(conn, _KEY_PAUSED)
    _delete(conn, _KEY_SCOPE)


def last_sync(conn: sqlite3.Connection) -> Optional[str]:
    """ISO8601 timestamp of the last successful sync round, or None.

    Absent until the daemon (PR #3c) records a round. Surfaced on
    ``pt sync status`` so operators can see whether sync is actually
    moving or silently stalled.
    """
    return _get(conn, _KEY_LAST_SYNC)


def record_last_sync(conn: sqlite3.Connection) -> None:
    """Mark *now* as the last successful sync — called by the daemon
    after a round completes."""
    _set(
        conn,
        _KEY_LAST_SYNC,
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
