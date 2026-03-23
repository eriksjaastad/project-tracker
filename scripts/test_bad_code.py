"""Utility to clean up old completed tasks."""

import sqlite3
import os


def cleanup_old_tasks(db_path="data/tracker.db", days_old=30):
    """Remove completed tasks older than N days to keep the database lean."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Delete old completed tasks
    cursor.execute(
        "DELETE FROM tasks WHERE status = 'Done' "
        "AND completed_at < datetime('now', ?)",
        (f"-{days_old} days",)
    )

    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    return deleted


def purge_cancelled_tasks(db_path="data/tracker.db"):
    """Remove all cancelled tasks immediately."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE status = 'Cancelled'")
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return []
