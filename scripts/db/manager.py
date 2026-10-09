"""Project Tracker database operations, executed locally."""
from .codebase_size import CodebaseSizeMixin
from .jobs import JobsMixin
from .operations import ProjectTrackerOps
from .outreach import OutreachMixin

class DatabaseManager(JobsMixin, OutreachMixin, CodebaseSizeMixin, ProjectTrackerOps):
    """The shared CLI/dashboard interface for the local database."""

__all__ = ["DatabaseManager"]
