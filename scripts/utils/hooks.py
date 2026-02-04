"""Hooks system for project tracker events."""

import subprocess
import os
from pathlib import Path
from typing import Dict, Any
from logger import get_logger

logger = get_logger(__name__)

def trigger_review_agent(task_id: int, project_id: str, task_text: str, done_criteria: str):
    """Spawn a reviewer agent for the given task."""
    logger.info(f"Triggering review agent for task #{task_id} in project {project_id}")
    
    # Resolve project path
    from db.manager import DatabaseManager
    db = DatabaseManager()
    project = db.get_project(project_id)
    if not project:
        logger.error(f"Project {project_id} not found")
        return

    project_path = project['path']
    
    # Prepare the review command
    # We'll use a script that performs the review. 
    # For now, we'll call a placeholder script or use a generic agent prompt.
    review_script = Path(os.getenv("PROJECTS_ROOT", "")) / "project-scaffolding" / "scaffold_cli.py"
    
    if not review_script.exists():
        logger.error(f"Review script not found at {review_script}")
        return

    # Example command: scaffold review --type code --input <diff_file>
    # This needs more thought on how to pass the context.
    # For now, let's log the intent.
    logger.info(f"Review agent would be spawned here for {project_id}")

def handle_status_change(task_id: int, old_status: str, new_status: str):
    """Handle task status transitions."""
    if new_status == "Review":
        from db.manager import DatabaseManager
        db = DatabaseManager()
        
        task = db.get_task(task_id)
        if task:
            # Extract Done Criteria from prompt
            prompt = task.get("prompt") or ""
            done_criteria = ""
            prompt_lower = prompt.lower()
            if "## done criteria" in prompt_lower:
                done_criteria = prompt_lower.split("## done criteria")[1].split("##")[0].strip()
            elif "## acceptance criteria" in prompt_lower:
                done_criteria = prompt_lower.split("## acceptance criteria")[1].split("##")[0].strip()
            
            trigger_review_agent(task_id, task['project_id'], task['text'], done_criteria)
