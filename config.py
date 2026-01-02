"""Configuration for project tracker."""

import os
from pathlib import Path

# Base directory for projects (can be overridden by PT_PROJECTS_DIR env var)
PROJECTS_BASE_DIR = Path(os.getenv("PT_PROJECTS_DIR", "/Users/eriksjaastad/projects"))

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
AUDIT_BIN_PATH = os.getenv("PT_AUDIT_BIN", "audit")

# Ensure data directory exists
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

