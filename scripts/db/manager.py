"""Project Tracker database operations, executed locally."""
from .backend_manager import _USE_TURSO
from .operations import ProjectTrackerOps

class DatabaseManager(ProjectTrackerOps):
    """The shared CLI/dashboard interface for the local database."""

__all__ = ["DatabaseManager", "_USE_TURSO"]
