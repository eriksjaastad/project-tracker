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

# Base directory for projects (can be overridden by PT_PROJECTS_DIR or PROJECTS_ROOT env vars)
_projects_root_env = os.getenv("PROJECTS_ROOT")
if _projects_root_env and _projects_root_env.strip():
    # Environment variable is set and non-empty
    PROJECTS_BASE_DIR = Path(_projects_root_env).resolve()
else:
    # Environment variable is unset or empty - use default
    PROJECTS_BASE_DIR = PROJECT_ROOT.parent

# Validate that PROJECTS_ROOT exists
if not PROJECTS_BASE_DIR.exists():
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
EXTERNAL_BACKUP_DIR = Path.home() / ".project-tracker" / "backups"

# External resources file (can be overridden by PT_RESOURCES_FILE env var)
EXTERNAL_RESOURCES_FILE = Path(
    os.getenv(
        "PT_RESOURCES_FILE",
        PROJECTS_BASE_DIR / "project-scaffolding" / "EXTERNAL_RESOURCES.yaml"
    )
)

# Project reindex script path
REINDEX_SCRIPT_PATH = PROJECTS_BASE_DIR / "project-scaffolding" / "scripts" / "reindex_projects.py"

# Audit Agent (Go CLI) binary path
_default_audit_bin = PROJECTS_BASE_DIR / "audit-agent" / "audit"
AUDIT_BIN_PATH = os.getenv("PT_AUDIT_BIN", str(_default_audit_bin) if _default_audit_bin.exists() else "audit")

# --- Review Agent Configuration ---
# Default model for code reviews (can be overridden by PT_REVIEW_MODEL)
# Preferred local model for logic: deepseek-r1:32b
DEFAULT_REVIEW_MODEL = os.getenv("PT_REVIEW_MODEL", "deepseek-r1:32b")

# Ensure data directory exists
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

