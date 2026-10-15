"""Project Tracker database operations, executed locally."""
from .codebase_size import CodebaseSizeMixin
from .jobs import JobsMixin
from .operations import ProjectTrackerOps
from .outreach import OutreachMixin
from .reminders import RemindersMixin

class DatabaseManager(
    JobsMixin, OutreachMixin, RemindersMixin, CodebaseSizeMixin, ProjectTrackerOps
):
    """The shared CLI/dashboard interface for the local database: one class.

    The SQL core (backend_manager), cross-table operations and recovery
    snapshots (operations), and the jobs, outreach, reminders and
    codebase-size domains (mixins) are all methods of this object.
    """

__all__ = ["DatabaseManager"]
