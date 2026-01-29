"""Configuration for project tracker."""

import os
from pathlib import Path

# Base directory for projects (can be overridden by PT_PROJECTS_DIR or PROJECTS_ROOT env vars)
_projects_root_env = os.getenv("PROJECTS_ROOT", "").strip()
if _projects_root_env:
    # Environment variable is set and non-empty
    PROJECTS_BASE_DIR = Path(_projects_root_env).resolve()
else:
    # Environment variable is unset or empty - use default
    PROJECTS_BASE_DIR = Path(__file__).resolve().parent.parent

# Validate that PROJECTS_ROOT exists
if not PROJECTS_BASE_DIR.exists():
    raise ValueError(
        f"PROJECTS_ROOT path does not exist: {PROJECTS_BASE_DIR}\n"
        f"Please set PROJECTS_ROOT environment variable to a valid directory path."
    )

# Database location (can be overridden by PT_DB_PATH env var)
DATABASE_PATH = Path(os.getenv("PT_DB_PATH", Path(__file__).parent / "data" / "tracker.db"))

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

# Ensure data directory exists
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

