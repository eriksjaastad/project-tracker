"""Project checkouts: which machine a project is being developed on (#8339).

A project checked out to one machine is not developed on the other. Cards
can still be added to it, and the board stays the way to reach the floor
manager working it. `pt project checkout|checkin|checkouts` and the
dashboard's project list share these methods.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

# Keys are the machine qualifiers agent-chat/identity.py uses.
MACHINE_LABELS = {"laptop": "MacBook", "mini": "Mac Mini"}


class ProjectCheckedOut(Exception):
    """A checkout was refused because the project is already out."""

    def __init__(self, checkout: dict[str, Any]):
        self.checkout = checkout
        super().__init__(
            f"{checkout['project_id']} is already checked out to "
            f"{MACHINE_LABELS[checkout['machine']]} by {checkout['holder']} "
            f"since {checkout['checked_out_at'][:10]}"
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _required(text: str, field: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        raise ValueError(f"{field} is required")
    return cleaned


class CheckoutsMixin:
    """Checkout operations exposed through the shared DatabaseManager."""

    def get_open_checkouts(self) -> dict[str, dict[str, Any]]:
        """Every project's open checkout, keyed by project id."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM project_checkouts WHERE checked_in_at IS NULL"
            ).fetchall()
        return {row["project_id"]: dict(row) for row in rows}

    def checkout_project(
        self, project_id: str, machine: str, holder: str, note: str | None = None
    ) -> dict[str, Any]:
        """Open a checkout; raises ProjectCheckedOut naming the current holder."""
        if machine not in MACHINE_LABELS:
            raise ValueError(f"machine must be one of {', '.join(MACHINE_LABELS)}")
        holder = _required(holder, "holder")
        note = (note or "").strip() or None
        with self._get_conn() as conn:
            if conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
                raise ValueError(f"no project {project_id!r}")
            try:
                cursor = conn.execute(
                    "INSERT INTO project_checkouts "
                    "(project_id, machine, holder, note, checked_out_at) VALUES (?, ?, ?, ?, ?)",
                    (project_id, machine, holder, note, _utc_now()),
                )
            except sqlite3.IntegrityError:
                # The open-checkout unique index refused it: report who has it.
                held = conn.execute(
                    "SELECT * FROM project_checkouts WHERE project_id = ? AND checked_in_at IS NULL",
                    (project_id,),
                ).fetchone()
                raise ProjectCheckedOut(dict(held)) from None
            row = conn.execute(
                "SELECT * FROM project_checkouts WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            conn.commit()
            return dict(row)

    def checkin_project(self, project_id: str, by: str) -> dict[str, Any] | None:
        """Close the open checkout, recording who and when; None if none is open."""
        by = _required(by, "by")
        with self._get_conn() as conn:
            row = conn.execute(
                "UPDATE project_checkouts SET checked_in_at = ?, checked_in_by = ? "
                "WHERE project_id = ? AND checked_in_at IS NULL RETURNING *",
                (_utc_now(), by, project_id),
            ).fetchone()
            conn.commit()
        return dict(row) if row else None
