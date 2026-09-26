"""Configuration for project tracker.

SAFETY NOTES:
- Database location should ALWAYS be data/tracker.db (the canonical path)
- PT_DB_PATH override is allowed but triggers loud warnings
- See Task #4692 for the history of database location confusion
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def projects_root() -> Path:
    """Return the portfolio projects root.

    Honours ``PROJECTS_ROOT`` when it is set and non-empty; otherwise falls
    back to ``~/projects``. This is deliberately env-first so a git worktree
    (whose ``Path(__file__)``-relative idioms resolve inside ``.claude/``)
    still finds the real portfolio root.
    """
    env_root = os.environ.get("PROJECTS_ROOT")
    if env_root and env_root.strip():
        return Path(env_root)
    return Path.home() / "projects"


# Base directory for projects (can be overridden by PROJECTS_ROOT env var)
PROJECTS_BASE_DIR = projects_root()

# Validate an explicit PROJECTS_ROOT override: pointing it at a missing
# directory is a configuration error. The default ~/projects may legitimately
# not exist yet (CI runners, fresh checkouts), so it is allowed to be absent.
if os.environ.get("PROJECTS_ROOT", "").strip() and not PROJECTS_BASE_DIR.exists():
    raise ValueError(
        f"PROJECTS_ROOT path does not exist: {PROJECTS_BASE_DIR}\n"
        f"Please set PROJECTS_ROOT environment variable to a valid directory path."
    )

# CANONICAL database location - this is the ONLY correct path
_CANONICAL_DB_PATH = PROJECT_ROOT / "data" / "tracker.db"

# Database location (can be overridden by PT_DB_PATH env var - but we warn loudly!)
_db_path_override = os.getenv("PT_DB_PATH")
if _db_path_override:
    DATABASE_PATH = Path(_db_path_override)
    # LOUD WARNING: Non-canonical database path
    if DATABASE_PATH.resolve() != _CANONICAL_DB_PATH.resolve():
        print(f"⚠️  WARNING: PT_DB_PATH is set to non-canonical location!", file=sys.stderr)
        print(f"   Current:   {DATABASE_PATH}", file=sys.stderr)
        print(f"   Canonical: {_CANONICAL_DB_PATH}", file=sys.stderr)
        print(f"   This can cause data to be written to the wrong database!", file=sys.stderr)
        print(f"   To fix: unset PT_DB_PATH or set it to the canonical path.", file=sys.stderr)
else:
    DATABASE_PATH = _CANONICAL_DB_PATH

# Database fingerprint file - used to detect database replacement
DB_FINGERPRINT_PATH = DATABASE_PATH.parent / ".db-fingerprint"

# External backup directory - survives project directory accidents
# Can be overridden for sandboxed environments (like Codex)
_external_backup_env = os.getenv("PT_EXTERNAL_BACKUP_DIR")
if _external_backup_env:
    EXTERNAL_BACKUP_DIR = Path(_external_backup_env)
else:
    EXTERNAL_BACKUP_DIR = Path.home() / ".project-tracker" / "backups"

# External resources file (can be overridden by PT_RESOURCES_FILE env var)
EXTERNAL_RESOURCES_FILE = Path(
    os.getenv(
        "PT_RESOURCES_FILE",
        PROJECT_ROOT / "EXTERNAL_RESOURCES.yaml"
    )
)

# Project reindex script path
REINDEX_SCRIPT_PATH = Path(
    os.getenv(
        "PT_REINDEX_SCRIPT",
        PROJECT_ROOT / "scripts" / "reindex_projects.py"
    )
)

# Ensure data directory exists
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
