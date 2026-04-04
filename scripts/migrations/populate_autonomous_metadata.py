#!/usr/bin/env python3
"""Populate autonomous loop metadata for existing projects.

This script assigns tier levels, healthcheck commands, and other autonomous loop
metadata to existing projects in the database.

Tier 1 (Hourly): project-tracker, project-scaffolding
Tier 2 (Daily): All other projects
"""

import sqlite3
import sys
import json
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.config import DATABASE_PATH, PROJECTS_BASE_DIR


def populate_metadata():
    """Populate autonomous loop metadata for all projects."""
    db_path = DATABASE_PATH
    projects_root = Path(PROJECTS_BASE_DIR)
    
    print(f"📊 Populating autonomous loop metadata...")
    print(f"   Database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all projects
    cursor.execute("SELECT id, name FROM projects")
    projects = cursor.fetchall()
    
    print(f"   Found {len(projects)} projects")
    
    # Define Tier 1 projects (critical infrastructure)
    tier1_projects = {"project-tracker", "project-scaffolding"}
    
    tier1_count = 0
    tier2_count = 0
    
    for project in projects:
        project_id = project["id"]
        project_name = project["name"]
        
        # Determine tier
        if project_id in tier1_projects:
            tier = 1
            tier1_count += 1
        else:
            tier = 2
            tier2_count += 1
        
        # Determine healthcheck command based on project
        # (Simple heuristic - can be customized per project later)
        healthcheck_cmd = "pytest tests/" if (projects_root / project_id / "tests").exists() else "echo 'No tests configured'"
        
        # Set default values
        autonomy_level = "report"  # Safe default - only create cards, no auto-fixes
        drift_status = "clean"  # Will be updated by Librarian loop
        commands_to_run = json.dumps([])  # Empty array
        cron_jobs_config = json.dumps({})  # Empty object
        
        # Update project
        cursor.execute("""
            UPDATE projects
            SET tier = ?,
                healthcheck_cmd = ?,
                commands_to_run = ?,
                cron_jobs_config = ?,
                autonomy_level = ?,
                drift_status = ?
            WHERE id = ?
        """, (tier, healthcheck_cmd, commands_to_run, cron_jobs_config, autonomy_level, drift_status, project_id))
        
        tier_label = "Tier 1 (Hourly)" if tier == 1 else "Tier 2 (Daily)"
        print(f"   ✓ {project_name}: {tier_label}, autonomy={autonomy_level}")
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ Metadata populated successfully!")
    print(f"   Tier 1 (Hourly):  {tier1_count} projects")
    print(f"   Tier 2 (Daily):   {tier2_count} projects")
    print(f"   Total:            {len(projects)} projects")


if __name__ == "__main__":
    populate_metadata()
