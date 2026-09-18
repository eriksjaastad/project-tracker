"""Where a task's attachment files live on disk.

Pure path arithmetic, no database. It sits in its own module because both
sides of the dbmed boundary legitimately need it and neither should reach
across for it: the dashboard writes and serves the files, and the backend
trashes them when a task or attachment is deleted.

Attachments are ordinary files under the user's home, not database contents,
so they are deliberately *not* behind the boundary. The rows that describe
them are.
"""

from __future__ import annotations

from pathlib import Path

ATTACHMENTS_ROOT = Path.home() / ".project-tracker" / "attachments"


def attachments_dir(task_id: int, *, create: bool = True) -> Path:
    """Return (and by default create) the storage directory for a task."""
    base = ATTACHMENTS_ROOT / str(int(task_id))
    if create:
        base.mkdir(parents=True, exist_ok=True)
    return base
