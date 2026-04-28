"""Logging configuration for project tracker."""

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Create logs directory when available. Sandboxed agents may have read access to
# project-tracker without write access to its logs directory.
LOGS_DIR = PROJECT_ROOT / "logs"
handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
try:
    LOGS_DIR.mkdir(exist_ok=True)
    handlers.insert(0, logging.FileHandler(LOGS_DIR / 'project_tracker.log'))
except OSError as err:
    print(f"project-tracker: file logging unavailable: {err}", file=sys.stderr)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=handlers
)

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a module."""
    return logging.getLogger(name)
