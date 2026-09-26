"""Project Tracker database operations, executed locally."""
from .backend_manager import _USE_TURSO
from .jobs import JobsMixin
from .operations import ProjectTrackerOps
from .outreach import OutreachMixin

class DatabaseManager(JobsMixin, OutreachMixin, ProjectTrackerOps):
    """The shared CLI/dashboard interface for the local database."""

__all__ = ["DatabaseManager", "_USE_TURSO"]
