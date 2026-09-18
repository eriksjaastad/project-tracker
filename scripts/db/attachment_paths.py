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


def delete_attachment_files(attachments: list[dict]) -> None:
    """Send each attachment's file to the Trash, and tidy the empty directory.

    Lives here rather than on `DatabaseManager` because it touches files, not
    rows, and both sides of the dbmed boundary call it: the dashboard when a
    single attachment is removed, the backend when a task delete cascades.

    Never unlinks. This is user-uploaded content, and a misclick in the
    dashboard used to destroy it outright (#6905). Failures are logged and the
    loop continues — one unreadable file must not abandon the rest.
    """
    import logging

    from send2trash import send2trash

    logger = logging.getLogger(__name__)

    for attachment in attachments or []:
        task_id = attachment.get("task_id")
        stored_name = attachment.get("stored_name")
        if task_id is None or not stored_name:
            continue

        attachment_dir = attachments_dir(int(task_id), create=False)
        file_path = attachment_dir / str(stored_name)
        try:
            if file_path.exists():
                send2trash(str(file_path))
            # The now-empty per-task directory is our own bookkeeping, not
            # user content, so removing it outright is fine — but only when
            # it is genuinely empty.
            if attachment_dir.exists() and not any(attachment_dir.iterdir()):
                attachment_dir.rmdir()  # governance: allow-delete DS001: our own bookkeeping dir, proven empty by the guard above; the user content in it went to the Trash
        except OSError as exc:
            logger.warning(
                "Failed to clean attachment file for task %s (%s): %s",
                task_id,
                stored_name,
                exc,
            )
